#!/usr/bin/env python3
"""Plan or run the separately versioned runtime-adapter calibration study.

The default is a no-provider plan. Authored controls require --synthetic-control
and are never reported as measured calibration. A live study requires explicit
consent, a clean source SHA, independent label receipts, adjudication when needed,
and bounded case, request, prompt, and estimated-cost ceilings.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
import threading
import time
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

from verity.cost import RunAccumulator, Usage, estimate_cost  # noqa: E402
from verity.runtime_adapter_calibration import (  # noqa: E402
    ADAPTERS,
    AdapterCase,
    AdapterDataset,
    MeasurementAttempt,
    analyze_adapter_calibration,
    authored_control_labels,
    build_registry,
    load_dataset,
    load_reviewer_labels,
    resolve_heldout_labels,
)

_DEFAULT_DATASET = _ROOT / "datasets/calibration/runtime-adapters/authored-controls-v1.yaml"
_MAX_PROMPT_BYTES = 131_072
_MAX_RESPONSE_TOKENS = 8192
_JUDGE_MAX_ATTEMPTS = 3


class RequestCeilingError(RuntimeError):
    """Raised before submitting a request beyond the explicitly set ceiling."""


class CostCeilingError(RuntimeError):
    """Raised before an estimated request budget would exceed the set ceiling."""


class PromptCeilingError(RuntimeError):
    """Raised when a judge prompt is larger than the bounded live-study plan."""


class RateCeilingError(RuntimeError):
    """Raised before a provider submission exceeds the live per-minute ceiling."""


def _git_identity() -> tuple[str | None, bool]:
    try:
        head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=_ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
        status = subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=_ROOT, text=True, stderr=subprocess.DEVNULL
        )
    except (OSError, subprocess.CalledProcessError):
        return None, False
    return head if re.fullmatch(r"[0-9a-f]{40}", head) else None, not status.strip()


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(_ROOT).as_posix()
    except ValueError:
        return path.name


def _judge_config(settings: Any) -> dict[str, Any]:
    provider = settings.judge.provider or settings.provider
    return {
        "provider": provider.value,
        "model": settings.judge.model,
        "temperature": settings.judge.temperature,
        "max_tokens": settings.judge.max_tokens,
    }


def _check_live_key(settings: Any) -> None:
    provider = settings.judge.provider or settings.provider
    key_fields = {
        "zai": settings.zai_api_key,
        "openrouter": settings.openrouter_api_key,
        "together": settings.together_api_key,
        "nvidia": settings.nvidia_api_key,
        "google": settings.google_api_key,
    }
    secret = key_fields[provider.value]
    if secret is None or not secret.get_secret_value().strip():
        raise ValueError(f"no provider key is configured for judge provider {provider.value!r}")


def _validate_locked_dependencies(adapter_keys: set[str]) -> None:
    from importlib.metadata import PackageNotFoundError, version

    dependencies = {ADAPTERS[key].dependency: ADAPTERS[key].locked_version for key in adapter_keys}
    for package, locked in dependencies.items():
        try:
            installed = version(package)
        except PackageNotFoundError as exc:
            raise ValueError(f"required semantic dependency {package} is not installed") from exc
        if installed != locked:
            raise ValueError(
                f"{package} version {installed} does not match the frozen "
                f"{locked} calibration version"
            )


class RequestBoundAccumulator(RunAccumulator):
    """RunAccumulator with a hard request ceiling enforced before each call."""

    def __init__(self, max_requests: int, max_requests_per_minute: int) -> None:
        super().__init__()
        self.max_requests = max_requests
        self.max_requests_per_minute = max_requests_per_minute
        self._request_times: deque[float] = deque()

    def begin_request(self, *args: Any, **kwargs: Any) -> Any:
        if len(self.requests) >= self.max_requests:
            raise RequestCeilingError("adapter_request_ceiling_reached")
        now = time.monotonic()
        while self._request_times and now - self._request_times[0] >= 60:
            self._request_times.popleft()
        if len(self._request_times) >= self.max_requests_per_minute:
            raise RateCeilingError("adapter_rate_ceiling_reached")
        if not self.total_cost.priced:
            raise CostCeilingError("unpriced_model_budget_refused")
        self._request_times.append(now)
        return super().begin_request(*args, **kwargs)


class BudgetedJudge:
    """ProviderJudge wrapper that reserves a conservative cost bound per call."""

    def __init__(self, settings: Any, accumulator: Any, max_cost_usd: float) -> None:
        from verity.judges import ProviderJudge

        self._estimate_cost = estimate_cost
        self._delegate = ProviderJudge(settings=settings, accumulator=accumulator)
        self._accumulator = accumulator
        self._max_cost_usd = max_cost_usd
        self._reserved_usd = 0.0
        self._lock = threading.Lock()
        self.model_name = self._delegate.model_name
        probe = self._estimate_cost_for_tokens(1, 1)
        if not probe.priced:
            raise ValueError("live adapter calibration requires a model with a known cost estimate")

    def _estimate_cost_for_tokens(self, prompt_tokens: int, completion_tokens: int) -> Any:
        total = prompt_tokens + completion_tokens
        return self._estimate_cost(Usage(prompt_tokens, completion_tokens, total), self.model_name)

    def _reserve(self, prompt: str) -> float:
        encoded_bytes = len(prompt.encode("utf-8"))
        if encoded_bytes > _MAX_PROMPT_BYTES:
            raise PromptCeilingError("adapter_prompt_byte_ceiling_reached")
        # Allow room for one correction prompt and cap each of the judge's
        # bounded retries at its existing 8,192-token ceiling.
        prompt_tokens = _JUDGE_MAX_ATTEMPTS * (encoded_bytes + _MAX_RESPONSE_TOKENS)
        completion_tokens = _JUDGE_MAX_ATTEMPTS * _MAX_RESPONSE_TOKENS
        estimate = self._estimate_cost_for_tokens(prompt_tokens, completion_tokens)
        reserve = estimate.total_usd
        with self._lock:
            current = self._accumulator.total_cost.total_usd
            if current + self._reserved_usd + reserve > self._max_cost_usd:
                raise CostCeilingError("adapter_estimated_cost_ceiling_reached")
            self._reserved_usd += reserve
        return reserve

    def _release(self, reserve: float) -> None:
        with self._lock:
            self._reserved_usd -= reserve

    def generate(self, prompt: str, structured_output: bool = True) -> str:
        request_start = len(self._accumulator.requests)
        reserve = self._reserve(prompt)
        try:
            result = self._delegate.generate(prompt, structured_output=structured_output)
            self._verify_accounting(request_start)
            return result
        finally:
            self._release_if_fully_accounted(request_start, reserve)

    async def a_generate(self, prompt: str, *, structured_output: bool = True) -> str:
        request_start = len(self._accumulator.requests)
        reserve = self._reserve(prompt)
        try:
            result = await self._delegate.a_generate(prompt, structured_output=structured_output)
            self._verify_accounting(request_start)
            return result
        finally:
            self._release_if_fully_accounted(request_start, reserve)

    def _release_if_fully_accounted(self, request_start: int, reserve: float) -> None:
        """Release unused budget only when every submitted call reports usage.

        Failed provider attempts can still be billable even when the provider
        gives no usage metadata. Keep that attempt's conservative reservation
        in the run budget rather than letting a retry spend it twice.
        """
        events = self._accumulator.requests[request_start:]
        if all(event.usage_reported is True for event in events):
            self._release(reserve)

    def _verify_accounting(self, request_start: int) -> None:
        events = self._accumulator.requests[request_start:]
        if any(event.usage_reported is not True for event in events):
            raise CostCeilingError("request_missing_usage_metadata")
        if self._accumulator.total_cost.total_usd > self._max_cost_usd:
            raise CostCeilingError("adapter_actual_estimated_cost_ceiling_reached")


def _native_metric(case: AdapterCase, judge: Any) -> float:
    """Score one case through the same native sample fields used by Tier-2."""
    if case.adapter_key == "faithfulness":
        from ragas import SingleTurnSample

        from verity.metrics.ragas_metrics import make_faithfulness

        metric = make_faithfulness(judge)
        sample = SingleTurnSample(
            user_input=case.input,
            response=case.candidate_output,
            retrieved_contexts=list(case.context),
        )
        return float(metric.single_turn_score(sample))

    from deepeval.test_case import LLMTestCase

    from verity.metrics.deepeval_metrics import (
        make_answer_relevancy,
        make_completeness,
        make_disambiguation,
        make_injection_compliance,
        make_pii_leakage,
        make_refusal_geval,
    )

    factories = {
        "answer_relevancy": make_answer_relevancy,
        "completeness": make_completeness,
        "disambiguation": make_disambiguation,
        "refusal": make_refusal_geval,
        "pii_leakage": make_pii_leakage,
        "injection_compliance": make_injection_compliance,
    }
    metric = factories[case.adapter_key](judge)
    values: dict[str, Any] = {
        "input": case.input,
        "actual_output": case.candidate_output,
    }
    if case.expected_output is not None:
        values["expected_output"] = case.expected_output
    metric.measure(LLMTestCase(**values))
    return float(metric.score)


def _safe_error_code(exc: BaseException) -> str:
    if isinstance(
        exc,
        (
            RequestCeilingError,
            CostCeilingError,
            PromptCeilingError,
            RateCeilingError,
        ),
    ):
        return f"safety_limit:{type(exc).__name__}"
    name = re.sub(r"[^A-Za-z0-9_.-]", "_", type(exc).__name__)[:64] or "Exception"
    return f"adapter_error:{name}"


def _score_live(
    dataset: AdapterDataset,
    judge: BudgetedJudge,
    max_requests: int,
) -> list[MeasurementAttempt]:
    from verity.cost import reset_current_test_id, set_current_test_id

    accumulator = judge._accumulator
    attempts: list[MeasurementAttempt] = []
    stopped = False
    for case in dataset.cases:
        if stopped:
            attempts.append(MeasurementAttempt(case.case_id, "not_attempted"))
            continue
        token = set_current_test_id(case.case_id)
        try:
            score = _native_metric(case, judge)
            if not math.isfinite(score) or not 0 <= score <= 1:
                attempts.append(
                    MeasurementAttempt(
                        case.case_id,
                        "invalid",
                        invalid_reason="adapter_output:score_out_of_range_or_non_finite",
                    )
                )
            else:
                attempts.append(MeasurementAttempt(case.case_id, "completed", raw_score=score))
        except (
            RequestCeilingError,
            CostCeilingError,
            PromptCeilingError,
            RateCeilingError,
        ) as exc:
            attempts.append(
                MeasurementAttempt(case.case_id, "invalid", invalid_reason=_safe_error_code(exc))
            )
            stopped = True
        except Exception as exc:
            attempts.append(
                MeasurementAttempt(case.case_id, "invalid", invalid_reason=_safe_error_code(exc))
            )
            if (
                len(accumulator.requests) >= max_requests
                or accumulator.total_cost.total_usd >= judge._max_cost_usd
            ):
                stopped = True
        finally:
            reset_current_test_id(token)
    return attempts


def _synthetic_attempts(dataset: AdapterDataset) -> list[MeasurementAttempt]:
    """Exercise report plumbing with deterministic, explicitly synthetic scores."""
    attempts: list[MeasurementAttempt] = []
    for case in dataset.cases:
        score = 0.95 if case.control_truth == "good" else 0.05
        attempts.append(MeasurementAttempt(case.case_id, "completed", raw_score=score))
    return attempts


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Runtime-Adapter Calibration Report",
        "",
        f"**Status:** {report['status']}  ",
        f"**Cohort:** `{report['cohort_id']}` ({report['cohort_kind']})  ",
        f"**Source kind:** `{report['source_kind']}`  ",
        f"**Dataset SHA-256:** `{report['dataset']['sha256']}`  ",
        "",
        "A bad decision means the adapter score fell below its frozen runtime threshold. "
        "Invalid and unattempted cases stay visible in completeness and are excluded from "
        "the confusion matrix; they are never converted to zero or a false negative.",
        "",
        "| Adapter | Planned | Attempted | Completed | Invalid | TP | FP | TN | FN | "
        "Sensitivity | Specificity | Raw agreement | 95% lower bounds | Review status |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for key, item in sorted(report["per_adapter"].items()):
        complete = item["completeness"]
        matrix = item["confusion_matrix_valid_measurements_only"]
        sens_ci = item["sensitivity_wilson_95"]["lower"]
        spec_ci = item["specificity_wilson_95"]["lower"]
        sens_ci_text = "n/a" if sens_ci is None else f"{sens_ci:.3f}"
        spec_ci_text = "n/a" if spec_ci is None else f"{spec_ci:.3f}"
        lines.append(
            f"| {key} | {complete['planned']} | {complete['attempted']} | "
            f"{complete['completed']} | {complete['invalid']} | {matrix['tp']} | "
            f"{matrix['fp']} | {matrix['tn']} | {matrix['fn']} | "
            f"{item['sensitivity'] if item['sensitivity'] is not None else 'n/a'} | "
            f"{item['specificity'] if item['specificity'] is not None else 'n/a'} | "
            f"{item['raw_agreement'] if item['raw_agreement'] is not None else 'n/a'} | "
            f"{sens_ci_text} / {spec_ci_text} | {item['promotion_status']} |"
        )
    lines += [
        "",
        "## Case-level raw scores",
        "",
        "| Case | Pair | Adapter | Label | Score | Decision | Status |",
        "|---|---|---|---|---:|---|---|",
    ]
    for key, item in sorted(report["per_adapter"].items()):
        for measurement in item["measurements"]:
            decision = measurement["normalized_bad_decision"]
            decision_text = "bad" if decision is True else "good" if decision is False else "—"
            score = measurement["raw_score"]
            score_text = "—" if score is None else f"{score:.4f}"
            lines.append(
                f"| `{measurement['case_id']}` | `{measurement['pair_id']}` | {key} | "
                f"{measurement['actual_label']} | {score_text} | {decision_text} | "
                f"{measurement['status']} |"
            )
    lines += [
        "",
        "Synthetic-control runs are plumbing demonstrations only and do not establish "
        "measured adapter calibration. A passing held-out result is only eligible for "
        "human review; it never unquarantines a metric automatically.",
        "",
        "_Generated by `scripts/run_adapter_calibration.py`._",
        "",
    ]
    return "\n".join(lines)


def _write_report(report: dict[str, Any], output_prefix: Path) -> tuple[Path, Path]:
    output_prefix.parent.mkdir(parents=True, exist_ok=True)
    json_path = output_prefix.with_suffix(".json")
    markdown_path = output_prefix.with_suffix(".md")
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(_render_markdown(report), encoding="utf-8")
    return json_path, markdown_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Print the no-provider plan")
    mode.add_argument(
        "--synthetic-control", action="store_true", help="Run authored deterministic controls only"
    )
    mode.add_argument("--live", action="store_true", help="Score a labeled held-out cohort")
    parser.add_argument("--dataset", type=Path, default=_DEFAULT_DATASET)
    parser.add_argument("--reviewer-one", type=Path)
    parser.add_argument("--reviewer-two", type=Path)
    parser.add_argument("--adjudication", type=Path)
    parser.add_argument("--confirm-live", action="store_true")
    parser.add_argument("--source-sha")
    parser.add_argument("--max-cases", type=int)
    parser.add_argument("--max-requests", type=int)
    parser.add_argument("--max-requests-per-minute", type=int)
    parser.add_argument("--max-cost-usd", type=float)
    parser.add_argument("--out", type=Path, help="Output prefix; writes JSON and Markdown")
    args = parser.parse_args()

    dataset = load_dataset(args.dataset)
    head_sha, clean = _git_identity()
    live_settings = None
    if args.live:
        if not args.confirm_live:
            parser.error("--live also requires --confirm-live")
        if dataset.cohort_kind != "independently-labeled-heldout":
            parser.error("--live requires an independently-labeled-heldout dataset")
        if not args.reviewer_one or not args.reviewer_two:
            parser.error(
                "--live requires --reviewer-one and --reviewer-two complete label receipts"
            )
        if args.max_cases is None or not len(dataset.cases) <= args.max_cases <= 500:
            parser.error("--live requires --max-cases to cover the cohort and be at most 500")
        if args.max_requests is None or not 1 <= args.max_requests <= 500:
            parser.error("--live requires --max-requests between 1 and 500")
        if args.max_requests_per_minute is None or not 1 <= args.max_requests_per_minute <= 60:
            parser.error("--live requires --max-requests-per-minute between 1 and 60")
        if args.max_cost_usd is None or not 0 < args.max_cost_usd <= 10:
            parser.error("--live requires --max-cost-usd greater than 0 and at most 10")
        if args.source_sha != head_sha or not clean:
            parser.error("--live requires --source-sha equal to HEAD and a clean working tree")
        live_settings_module = __import__("verity.config", fromlist=["Settings"])
        live_settings = live_settings_module.Settings().model_copy(update={"cassette_mode": "off"})
        if not 1 <= live_settings.judge.max_tokens <= _MAX_RESPONSE_TOKENS:
            parser.error(
                f"judge max_tokens must be between 1 and {_MAX_RESPONSE_TOKENS} "
                "for this bounded run"
            )
        _check_live_key(live_settings)
        _validate_locked_dependencies({case.adapter_key for case in dataset.cases})

    judge_config = (
        _judge_config(live_settings)
        if live_settings is not None
        else {"provider": None, "model": None, "temperature": None, "max_tokens": None}
    )
    registry = build_registry(
        source_sha=head_sha,
        working_tree_clean=clean,
        judge_config=judge_config,
    )
    if not args.live and not args.synthetic_control:
        plan = {
            "schema_version": "runtime-adapter-calibration-plan-v1",
            "mode": "dry-run",
            "provider_calls": 0,
            "dataset": {
                "path": _display_path(dataset.path),
                "sha256": dataset.sha256,
                "cohort_id": dataset.cohort_id,
                "cohort_kind": dataset.cohort_kind,
                "planned_cases": len(dataset.cases),
            },
            "source_sha": head_sha,
            "source_working_tree_clean": clean,
            "adapters": registry,
            "live_requirements": [
                "independently reviewed held-out cohort",
                "two distinct complete reviewer CSVs bound to the dataset SHA-256",
                "adjudication CSV for every disagreement before judging",
                "--live --confirm-live --source-sha --max-cases --max-requests "
                "--max-requests-per-minute --max-cost-usd",
                "clean source tree and exact HEAD identity",
            ],
        }
        serialized = json.dumps(plan, indent=2, sort_keys=True) + "\n"
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(serialized, encoding="utf-8")
            print(f"No-provider plan written to {args.out}")
        else:
            print(serialized, end="")
        return

    if args.synthetic_control:
        if dataset.cohort_kind != "authored-control":
            parser.error("--synthetic-control requires an authored-control dataset")
        labels = authored_control_labels(dataset)
        attempts = _synthetic_attempts(dataset)
        mode_name = "synthetic-adapter-control"
    else:
        assert live_settings is not None
        reviewer_one = load_reviewer_labels(args.reviewer_one, dataset)
        reviewer_two = load_reviewer_labels(args.reviewer_two, dataset)
        labels = resolve_heldout_labels(dataset, reviewer_one, reviewer_two, args.adjudication)
        accumulator = RequestBoundAccumulator(args.max_requests, args.max_requests_per_minute)
        judge = BudgetedJudge(live_settings, accumulator, args.max_cost_usd)
        attempts = _score_live(dataset, judge, args.max_requests)
        mode_name = "live-runtime-adapter"

    report = analyze_adapter_calibration(dataset, labels, attempts, registry)
    report.update(
        {
            "run_mode": mode_name,
            "generated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "source_sha": head_sha,
            "source_working_tree_clean": clean,
            "judge_config": judge_config,
            "limits": (
                {
                    "max_cases": args.max_cases,
                    "max_requests": args.max_requests,
                    "max_requests_per_minute": args.max_requests_per_minute,
                    "max_estimated_cost_usd": args.max_cost_usd,
                    "max_prompt_bytes": _MAX_PROMPT_BYTES,
                    "max_response_tokens_per_request": _MAX_RESPONSE_TOKENS,
                }
                if args.live
                else None
            ),
        }
    )
    prefix = args.out or (
        _ROOT
        / "reports/calibration"
        / f"runtime-adapter-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
    )
    json_path, markdown_path = _write_report(report, prefix)
    print(f"Runtime-adapter report written to {markdown_path}")
    print(f"Machine report written to {json_path}")
    if report["status"] == "incomplete":
        raise SystemExit("Runtime-adapter measurements are incomplete; no promotion is available.")


if __name__ == "__main__":
    main()
