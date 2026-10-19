"""Check Gemini availability; --live requires a confirmed free-tier project."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from decimal import Decimal
from importlib.metadata import version
from pathlib import Path
from typing import Any

import httpx
from dotenv import dotenv_values
from pydantic import SecretStr

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "src"))

from verity.calibration import (  # noqa: E402
    build_scoring_prompt,
    load_calibration,
    load_heldout_calibration,
)
from verity.config import JudgeConfig, Provider, Settings  # noqa: E402
from verity.providers import LLMProvider  # noqa: E402

DEFAULT_MODEL = "gemini-3.8-flash"
CATALOGUE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
# Explicit Standard-tier text pricing verified on 2026-10-18. Availability
# checks do NOT reveal the project billing plan. Recheck pricing before studies.
FREE_TIER_MODELS = {"gemini-3.8-flash"}
PRICING_URL = "https://ai.google.dev/gemini-api/docs/pricing"


class FreeHostedError(ValueError):
    """Safe, application-authored stop reason with no provider exception text."""


def source_metadata() -> tuple[str | None, bool | None, str]:
    """Resolve an auditable revision without requiring Git in the runtime image."""
    revision = os.environ.get("VERITY_SOURCE_SHA", "").strip()
    if re.fullmatch(r"[0-9a-f]{40}", revision):
        revision_source = "build_environment"
    else:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=_ROOT,
                capture_output=True,
                text=True,
                check=True,
            )
            candidate = result.stdout.strip()
            revision = candidate if re.fullmatch(r"[0-9a-f]{40}", candidate) else ""
            revision_source = "git" if revision else "unavailable"
        except (OSError, subprocess.CalledProcessError):
            revision = ""
            revision_source = "unavailable"

    try:
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        dirty: bool | None = bool(status.stdout)
    except (OSError, subprocess.CalledProcessError):
        dirty = None
    return revision or None, dirty, revision_source


def require_supported_model(model: dict[str, Any], model_id: str) -> dict[str, Any]:
    """Allow only an explicitly reviewed free-tier text model, with no substitution."""
    if model_id not in FREE_TIER_MODELS:
        raise FreeHostedError("Model is not in the reviewed Gemini free-tier allowlist")
    if model.get("name") != f"models/{model_id}":
        raise FreeHostedError("Google returned a different model; no substitution")
    if "generateContent" not in model.get("supportedGenerationMethods", []):
        raise FreeHostedError("Selected model does not support generateContent")
    return model


def build_settings(key: str, model: str) -> Settings:
    """Isolate generation from paid ambient models, endpoints, keys and retry settings."""
    if model not in FREE_TIER_MODELS:
        raise FreeHostedError("Model is not in the reviewed Gemini free-tier allowlist")
    # pydantic-settings accepts this private init option at runtime; its mypy
    # generated constructor only describes declared fields.
    isolation: dict[str, Any] = {"_env_file": None}
    return Settings(
        **isolation,
        provider=Provider.google,
        model=model,
        google_api_key=SecretStr(key),
        google_api_base=None,
        zai_api_key=None,
        openrouter_api_key=None,
        openrouter_api_key_2=None,
        together_api_key=None,
        nvidia_api_key=None,
        temperature=1.0,
        timeout=45,
        retries=0,
        cassette_mode="off",
        judge=JudgeConfig(**isolation, provider=Provider.google, model=model, temperature=1.0),
    )


def smoke_prompts() -> tuple[Path, list[tuple[str, str]]]:
    """One fixed tuning case per metric; do not use held-out examples for a canary."""
    dataset = _ROOT / "datasets/calibration/labeled.yaml"
    selected: dict[str, tuple[str, str]] = {}
    for case in load_calibration(dataset):
        if case.metric not in selected:
            selected[case.metric] = (case.id, build_scoring_prompt(case))
    return dataset, [selected[metric] for metric in sorted(selected)]


def heldout_prompts(dataset: Path, *, start_index: int, max_calls: int) -> list[tuple[str, str]]:
    """Select one frozen contiguous batch without importing or creating human labels."""
    cases = load_heldout_calibration(dataset)
    prompts = [(case.randomized_case_id, build_scoring_prompt(case)) for case in cases]
    selected = prompts[start_index : start_index + max_calls]
    if not selected:
        raise FreeHostedError("Held-out batch starts outside the frozen dataset")
    return selected


def run_smoke(
    provider: LLMProvider,
    prompts: list[tuple[str, str]],
    receipt: dict[str, Any],
    receipt_path: Path,
    *,
    max_calls: int,
    max_tokens: int,
    total_output_tokens: int,
    interval: float,
    label: str = "free-hosted-tuning-smoke",
) -> None:
    """Save every attempt; never retry, replace invalid scores or promote thresholds."""
    if not prompts:
        raise FreeHostedError("No smoke prompts selected")
    output_used = 0
    for case_id, prompt in prompts[:max_calls]:
        remaining = total_output_tokens - output_used
        if remaining <= 0:
            raise FreeHostedError("Run output-token budget exhausted")
        if len(prompt.encode("utf-8")) > 16000:
            raise FreeHostedError("Smoke prompt exceeds the 16000-byte input cap")
        if receipt["attempts"] and interval:
            time.sleep(interval)
        attempt: dict[str, Any] = {
            "case_id": case_id,
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
            "output_token_limit": min(max_tokens, remaining),
            "started_at": datetime.now(UTC).isoformat(),
            "status": "started",
        }
        receipt["attempts"].append(attempt)
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
        started = time.monotonic()
        try:
            result = provider.complete(
                [{"role": "user", "content": prompt}],
                max_tokens=attempt["output_token_limit"],
                label=label,
                reasoning_effort="low",
            )
            if result.call_record is None:
                raise FreeHostedError("Live response has no usage record")
            usage = result.call_record.usage
            output_used += usage.completion_tokens
            raw = result.raw_response
            # Keep the actual response model/provider. A route slug is not an
            # immutable weights revision and the upstream can change over time.
            attempt.update(
                response=result.content,
                response_id=getattr(raw, "id", None),
                response_model=getattr(raw, "model", None),
                upstream_provider=getattr(raw, "provider", None),
                finish_reason=raw.choices[0].finish_reason,
                usage={
                    "prompt_tokens": usage.prompt_tokens,
                    "completion_tokens": usage.completion_tokens,
                    "total_tokens": usage.total_tokens,
                },
            )
            if usage.total_tokens <= 0 or usage.completion_tokens <= 0:
                raise FreeHostedError("Missing or invalid live usage")
            reported_cost = getattr(getattr(raw, "usage", None), "cost", None)
            attempt["provider_reported_cost_usd"] = reported_cost
            if reported_cost is not None and Decimal(str(reported_cost)) != 0:
                raise FreeHostedError("Provider reported a nonzero cost; stop and investigate")
            if usage.completion_tokens > attempt["output_token_limit"]:
                raise FreeHostedError("Provider exceeded the output-token limit")
            match = re.fullmatch(r"Score: (10|[0-9])\s*", result.content)
            if match is None or raw.choices[0].finish_reason != "stop":
                raise FreeHostedError("Invalid or truncated judge response")
            attempt.update(status="success", score=int(match[1]) / 10)
        except Exception as exc:
            # Provider exception messages can contain credentials or request
            # headers. Persist only type/status; retain already-recorded output.
            attempt.update(
                status="failed",
                error_type=type(exc).__name__,
                http_status=getattr(exc, "status_code", None),
            )
            if isinstance(exc, FreeHostedError):
                attempt["stop_reason"] = str(exc)
            raise
        finally:
            attempt["latency_ms"] = round((time.monotonic() - started) * 1000, 2)
            receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Send at most seven bounded prompts")
    parser.add_argument(
        "--heldout-study",
        action="store_true",
        help="Score a frozen unlabeled held-out set instead of the synthetic tuning smoke",
    )
    parser.add_argument("--heldout-dataset", type=Path, help="frozen 56-case held-out YAML file")
    parser.add_argument("--start-index", type=int, default=0, help="first case index for one batch")
    parser.add_argument(
        "--confirm-free-project",
        action="store_true",
        help="Attest that this key belongs to a Free-tier project with billing disabled",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--env-file", type=Path, default=_ROOT / ".env")
    parser.add_argument("--max-calls", type=int, default=7, choices=range(1, 8))
    parser.add_argument(
        "--max-tokens", type=int, default=2048, help="Output tokens per call, 1..4096"
    )
    parser.add_argument("--total-output-tokens", type=int, default=14336)
    parser.add_argument("--interval", type=float, default=3.1, help="Seconds between calls, >=3")
    parser.add_argument("--out", type=Path, default=_ROOT / "reports/free-hosted")
    args = parser.parse_args()
    if (
        not 1 <= args.max_tokens <= 4096
        or not 1 <= args.total_output_tokens <= 28672
        or not 3 <= args.interval <= 60
    ):
        parser.error("Per-call tokens: 1..4096; total output: 1..28672; interval: 3..60 seconds")
    if args.heldout_study:
        if not args.live or args.heldout_dataset is None:
            parser.error("--heldout-study requires --live and --heldout-dataset")
        if not 0 <= args.start_index < 56:
            parser.error("Held-out --start-index must be between 0 and 55")
    elif args.heldout_dataset is not None or args.start_index != 0:
        parser.error("--heldout-dataset and --start-index require --heldout-study")
    args.out.mkdir(parents=True, exist_ok=True)
    receipt_prefix = "heldout" if args.heldout_study else "smoke"
    receipt_path = args.out / f"{receipt_prefix}-{time.time_ns()}.json"
    source_sha, source_tree_dirty, source_revision_source = source_metadata()
    receipt: dict[str, Any] = {
        "schema_version": 1,
        "purpose": (
            "bounded live D05 held-out scoring; does not label or analyze cases"
            if args.heldout_study
            else "live tuning-set smoke, NOT independent calibration"
            if args.live
            else "catalogue preflight only, no inference"
        ),
        "started_at": datetime.now(UTC).isoformat(),
        "source_sha": source_sha,
        "source_tree_dirty": source_tree_dirty,
        "source_revision_source": source_revision_source,
        "implementation_file_sha256": {
            name: hashlib.sha256((_ROOT / name).read_bytes()).hexdigest()
            for name in (
                "scripts/run_free_hosted_calibration.py",
                "src/verity/config.py",
                "src/verity/providers.py",
            )
        },
        "litellm_version": version("litellm"),
        "requested_model": args.model,
        "free_project_confirmed_by_operator": args.confirm_free_project,
        "billing_plan_verified_by_api": False,
        "pricing_source": PRICING_URL,
        "pricing_reviewed_on": "2026-10-18",
        "catalogue_url": CATALOGUE_URL,
        "limits": {
            "calls": args.max_calls,
            "output_tokens_per_call": args.max_tokens,
            "output_tokens_per_run": args.total_output_tokens,
            "input_bytes_per_call": 16000,
            "interval_seconds": args.interval,
            "retries": 0,
            "spend_usd": 0,
        },
        "generation_config": {"temperature": 1.0, "reasoning_effort": "low"},
        "attempts": [],
        "status": "started",
    }
    try:
        if args.model not in FREE_TIER_MODELS:
            raise FreeHostedError("Model is not in the reviewed Gemini free-tier allowlist")
        if args.live and not args.confirm_free_project:
            raise FreeHostedError(
                "Live inference needs confirmation that this key's project is Free tier "
                "with billing disabled; catalogue access does not prove free billing"
            )
        if args.live and not source_sha:
            raise FreeHostedError(
                "Live inference requires a source commit; run in a Git checkout or set "
                "VERITY_SOURCE_SHA to the 40-character commit baked into the image"
            )
        file_values = dotenv_values(args.env_file)
        key = (
            os.environ.get("VERITY_GOOGLE_API_KEY")
            or os.environ.get("GOOGLE_API_KEY")
            or os.environ.get("GEMINI_API_KEY")
            or file_values.get("VERITY_GOOGLE_API_KEY")
            or file_values.get("GOOGLE_API_KEY")
            or file_values.get("GEMINI_API_KEY")
        )
        if not key or key.startswith("your-"):
            raise FreeHostedError("Configure a Gemini API key locally; never commit it")
        response = httpx.get(
            f"{CATALOGUE_URL}/{args.model}", headers={"x-goog-api-key": key}, timeout=20
        )
        response.raise_for_status()
        model = require_supported_model(response.json(), args.model)
        receipt["catalogue_model"] = model
        receipt["catalogue_checked_at"] = datetime.now(UTC).isoformat()
        if args.live:
            settings = build_settings(key, args.model)
            if args.heldout_study:
                dataset = args.heldout_dataset
                assert dataset is not None
                prompts = heldout_prompts(
                    dataset,
                    start_index=args.start_index,
                    max_calls=args.max_calls,
                )
                receipt["study_plan_id"] = "D05-GEMINI-HELDOUT-2026-10-18-v1"
                receipt["start_index"] = args.start_index
            else:
                dataset, prompts = smoke_prompts()
            receipt["dataset_sha256"] = hashlib.sha256(dataset.read_bytes()).hexdigest()
            receipt["selected_case_ids"] = [case_id for case_id, _ in prompts]
            run_smoke(
                LLMProvider(settings),
                prompts,
                receipt,
                receipt_path,
                max_calls=args.max_calls,
                max_tokens=args.max_tokens,
                total_output_tokens=args.total_output_tokens,
                interval=args.interval,
                label=(
                    "d05-heldout-calibration" if args.heldout_study else "free-hosted-tuning-smoke"
                ),
            )
        receipt["status"] = "success"
    except Exception as exc:
        receipt.update(
            status="failed",
            error_type=type(exc).__name__,
            http_status=getattr(exc, "status_code", None),
        )
        if isinstance(exc, FreeHostedError):
            receipt["stop_reason"] = str(exc)
            print(f"Stopped ({exc}); no retry or paid fallback.", file=sys.stderr)
        else:
            print(f"Stopped ({type(exc).__name__}); no retry or paid fallback.", file=sys.stderr)
    finally:
        receipt["ended_at"] = datetime.now(UTC).isoformat()
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
        print(f"{receipt['status']}: {receipt_path}")
    return 0 if receipt["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
