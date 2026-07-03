"""Rank zero-price hosted open-weight models from the OpenRouter registry."""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.request import urlopen

_REGISTRY_URL = "https://openrouter.ai/api/v1/models"
_DEFAULT_LIMIT = 5
_REQUIRED_PARAMETERS = {"tools"}

_SRC = Path(__file__).parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from verity.config import Provider, Settings  # noqa: E402


def _require_openrouter_key() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        settings = Settings(provider=Provider.openrouter)
    _, _, key = settings.resolved_provider()
    if key is None:
        raise SystemExit("OpenRouter model selection requires VERITY_OPENROUTER_API_KEY.")


@dataclass(frozen=True)
class CandidateModel:
    rank: int
    model_id: str
    name: str
    hugging_face_id: str
    context_length: int
    intelligence_index: float | None
    coding_index: float | None
    agentic_index: float | None
    supports_tools: bool


def _metric(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_zero_price(model: dict[str, Any]) -> bool:
    pricing = model.get("pricing") or {}
    return pricing.get("prompt") == "0" and pricing.get("completion") == "0"


def _has_text_io(model: dict[str, Any]) -> bool:
    architecture = model.get("architecture") or {}
    input_modalities = architecture.get("input_modalities") or []
    output_modalities = architecture.get("output_modalities") or []
    return "text" in input_modalities and "text" in output_modalities


def _supports_required_parameters(model: dict[str, Any]) -> bool:
    supported = set(model.get("supported_parameters") or [])
    return _REQUIRED_PARAMETERS.issubset(supported)


def _benchmarks(model: dict[str, Any]) -> dict[str, Any]:
    return (model.get("benchmarks") or {}).get("artificial_analysis") or {}


def select_candidates(
    models: list[dict[str, Any]],
    limit: int = _DEFAULT_LIMIT,
) -> list[CandidateModel]:
    """Return ranked zero-price hosted open-weight models suitable for live checks."""
    filtered: list[dict[str, Any]] = []
    for model in models:
        if not _is_zero_price(model):
            continue
        if not str(model.get("id", "")).endswith(":free"):
            continue
        if not model.get("hugging_face_id"):
            continue
        if not _has_text_io(model):
            continue
        if not _supports_required_parameters(model):
            continue
        filtered.append(model)

    def sort_key(model: dict[str, Any]) -> tuple[float, float, float, int, str]:
        benchmark = _benchmarks(model)
        intelligence = _metric(benchmark.get("intelligence_index"))
        coding = _metric(benchmark.get("coding_index"))
        agentic = _metric(benchmark.get("agentic_index"))
        context = int(model.get("context_length") or 0)
        return (
            intelligence if intelligence is not None else -1.0,
            coding if coding is not None else -1.0,
            agentic if agentic is not None else -1.0,
            context,
            str(model.get("id", "")),
        )

    ranked = sorted(filtered, key=sort_key, reverse=True)[:limit]
    candidates: list[CandidateModel] = []
    for index, model in enumerate(ranked, start=1):
        benchmark = _benchmarks(model)
        candidates.append(
            CandidateModel(
                rank=index,
                model_id=str(model["id"]),
                name=str(model.get("name") or model["id"]),
                hugging_face_id=str(model["hugging_face_id"]),
                context_length=int(model.get("context_length") or 0),
                intelligence_index=_metric(benchmark.get("intelligence_index")),
                coding_index=_metric(benchmark.get("coding_index")),
                agentic_index=_metric(benchmark.get("agentic_index")),
                supports_tools="tools" in set(model.get("supported_parameters") or []),
            )
        )
    return candidates


def _load_models(path: Path | None) -> list[dict[str, Any]]:
    if path is not None:
        raw = json.loads(path.read_text(encoding="utf-8"))
    else:
        with urlopen(_REGISTRY_URL, timeout=20) as response:
            raw = json.load(response)
    data = raw.get("data") if isinstance(raw, dict) else raw
    if not isinstance(data, list):
        raise ValueError("model registry payload must contain a list")
    return [item for item in data if isinstance(item, dict)]


def _format_metric(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1f}"


def render_table(candidates: list[CandidateModel]) -> str:
    """Render candidates as a markdown table."""
    lines = [
        "| Rank | Model | Weights | Intelligence | Coding | Agentic | Context | Tools |",
        "|---:|---|---|---:|---:|---:|---:|---|",
    ]
    for candidate in candidates:
        lines.append(
            "| "
            f"{candidate.rank} | `{candidate.model_id}` | `{candidate.hugging_face_id}` | "
            f"{_format_metric(candidate.intelligence_index)} | "
            f"{_format_metric(candidate.coding_index)} | "
            f"{_format_metric(candidate.agentic_index)} | "
            f"{candidate.context_length} | {'yes' if candidate.supports_tools else 'no'} |"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, help="Read registry JSON from a local file")
    parser.add_argument("--limit", type=int, default=_DEFAULT_LIMIT, help="Number of rows to print")
    args = parser.parse_args()

    if args.fixture is None:
        _require_openrouter_key()
    models = _load_models(args.fixture)
    candidates = select_candidates(models, limit=args.limit)
    print(render_table(candidates))


if __name__ == "__main__":
    main()
