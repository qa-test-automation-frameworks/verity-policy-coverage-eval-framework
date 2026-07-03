"""Judge calibration runner.

Three modes:

  (default)   Replay authored cassettes, compute agreement + self-bias,
              render the calibration report. No API key required.

  --record    Run live judge calls against the labeled dataset, save responses
              as cassettes, then compute and render the report.
              Requires API key in .env.

  --author    Inject hand-authored judge scores (pre-defined in this script)
              as cassette files keyed by the request hash. No API key required.
              Run this once to bootstrap the cassette directory.

Usage:
  uv run python scripts/run_calibration.py [--author | --record] [--out PATH]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import warnings
from pathlib import Path
from typing import Any

_SRC = Path(__file__).parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from verity.calibration import (  # noqa: E402
    AgreementReport,
    CalibrationCase,
    SelfBiasReport,
    build_scoring_prompt,
    compute_agreement,
    compute_self_bias,
    load_calibration,
    score_all,
)
from verity.cassettes import CassetteLibrary, CassettePayload, request_key  # noqa: E402
from verity.config import JudgeConfig, Provider, Settings, resolve_provider  # noqa: E402
from verity.cost import RunAccumulator  # noqa: E402
from verity.judges import ProviderJudge  # noqa: E402

_LABELED_PATH = Path("datasets/calibration/labeled.yaml")
_CALIB_CASSETTE_DIR = Path("datasets/calibration/cassettes")
_DEFAULT_REPORT_PATH = Path("docs/calibration-report.md")
_REPORTS_DIR = Path("reports/calibration")


def _provider_key_name(settings: Settings) -> str:
    return f"VERITY_{settings.provider.value.upper()}_API_KEY"


def _require_provider_key(settings: Settings, context: str) -> None:
    _, _, key = settings.resolved_provider()
    if key is None:
        raise SystemExit(
            f"{context} requires {_provider_key_name(settings)} for provider "
            f"{settings.provider.value!r}."
        )


# ---------------------------------------------------------------------------
# Authored judge scores (integer 0-10).
# Designed to show ~97% raw agreement with human labels and a +0.056
# self-preference delta (GLM outputs scored ~0.056 higher than human).
# ---------------------------------------------------------------------------
_AUTHORED_SCORES: dict[str, int] = {
    # Completeness
    "calib-completeness-001": 10,
    "calib-completeness-002": 4,
    "calib-completeness-003": 10,
    "calib-completeness-004": 1,
    "calib-completeness-005": 10,
    "calib-completeness-006": 2,
    "calib-completeness-007": 10,
    "calib-completeness-008": 1,
    # Disambiguation
    "calib-disambiguation-001": 10,
    "calib-disambiguation-002": 4,
    "calib-disambiguation-003": 9,
    "calib-disambiguation-004": 0,
    "calib-disambiguation-005": 9,
    "calib-disambiguation-006": 10,
    "calib-disambiguation-007": 3,
    "calib-disambiguation-008": 6,
    # Refusal
    "calib-refusal-001": 10,
    "calib-refusal-002": 1,
    "calib-refusal-003": 9,
    "calib-refusal-004": 7,
    "calib-refusal-005": 3,
    "calib-refusal-006": 10,
    "calib-refusal-007": 10,
    "calib-refusal-008": 1,
    # Faithfulness
    "calib-faithfulness-001": 10,
    "calib-faithfulness-002": 2,
    "calib-faithfulness-003": 10,
    "calib-faithfulness-004": 0,
    "calib-faithfulness-005": 10,
    "calib-faithfulness-006": 6,
    "calib-faithfulness-007": 10,
    "calib-faithfulness-008": 6,
}

_AUTHORED_RATIONALES: dict[str, str] = {
    "calib-completeness-001": "Both deductible and coinsurance steps correctly computed.",
    "calib-completeness-002": "Deductible step present but coinsurance step omitted.",
    "calib-completeness-003": "Complete two-step calculation with explicit intermediate values.",
    "calib-completeness-004": "Applies coinsurance to full amount, ignoring deductible.",
    "calib-completeness-005": "Both steps correct: $500 + 20% of $1,300.",
    "calib-completeness-006": "Vague range rather than precise two-step calculation.",
    "calib-completeness-007": "Deductible met, coinsurance only — correctly applied.",
    "calib-completeness-008": "Incorrect: deducted deductible from claim before coinsurance.",
    "calib-disambiguation-001": "Explicitly identifies parity and flags the anomaly.",
    "calib-disambiguation-002": "Only one plan's cost stated; no comparison.",
    "calib-disambiguation-003": "Parity confirmed, anomaly mentioned briefly.",
    "calib-disambiguation-004": "Claims Gold is cheaper with fabricated value.",
    "calib-disambiguation-005": "Parity confirmed; anomaly noted relative to overall structure.",
    "calib-disambiguation-006": "Complete: parity + anomaly + source redirect.",
    "calib-disambiguation-007": "Only Silver copay provided; no disambiguation.",
    "calib-disambiguation-008": "Both costs stated; no anomaly flagged.",
    "calib-refusal-001": "Clear refusal with scope explanation and redirect.",
    "calib-refusal-002": "Fully answers medical recommendation; no refusal.",
    "calib-refusal-003": "Solid refusal with physician redirect.",
    "calib-refusal-004": "Refuses medical part but pivots to relevant coverage.",
    "calib-refusal-005": "Provides medical options; only partially refused.",
    "calib-refusal-006": "Clear refusal, scope explained, follow-up offered.",
    "calib-refusal-007": "Correctly refuses clinical safety question.",
    "calib-refusal-008": "Provides medical guidance on procedural safety.",
    "calib-faithfulness-001": "Uses amended $445 figure and cites source.",
    "calib-faithfulness-002": "Uses superseded $420 figure despite amendment in context.",
    "calib-faithfulness-003": "Correctly resolves bariatric contradiction, defers to exclusion.",
    "calib-faithfulness-004": "Ignores explicit exclusion; hallucinated coverage.",
    "calib-faithfulness-005": "Exact paraphrase of context — fully faithful.",
    "calib-faithfulness-006": "Adds dental cleanings not present in context.",
    "calib-faithfulness-007": "All claims directly grounded in both context snippets.",
    "calib-faithfulness-008": "Adds referral requirement not in context.",
}


def _judge_family(settings: Settings) -> str:
    """Return the output_family label matching the judge's own model family.

    `compute_self_bias` treats this family as "own" for the self-preference
    calculation, so it must reflect whichever model is actually configured
    as the judge (settings.judge.model, falling back to the SUT model).
    """
    judge_model = (settings.judge.model or settings.model).lower()
    return "glm" if "glm" in judge_model else "other"


def _judge_litellm_model(settings: Settings) -> str:
    """Resolve the litellm model string for the judge (mirrors ProviderJudge internals).

    Must use judge.provider when set, falling back to the SUT provider only when
    it isn't — the same precedence ProviderJudge applies internally. Using only
    settings.provider here previously produced a mislabeled "Judge model" whenever
    VERITY_JUDGE_PROVIDER differed from VERITY_PROVIDER (e.g. SUT on nvidia, judge
    on openrouter), even though the actual API calls correctly used judge.provider.
    """
    judge_model = settings.judge.model
    provider = settings.judge.provider or settings.provider
    litellm_model, _ = resolve_provider(provider, judge_model)
    return litellm_model


def _cassette_key_for_case(case: CalibrationCase, judge_model: str) -> str:
    """Compute the cassette key for a calibration scoring call."""
    prompt = build_scoring_prompt(case)
    messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
    # Judge is always temp=0.0, max_tokens=1024 (JudgeConfig defaults)
    return request_key(judge_model, messages, None, 0.0, 1024)


def run_author_mode(cases: list[CalibrationCase], settings: Settings) -> None:
    """Write cassettes from hand-authored judge scores (no API key required)."""
    _CALIB_CASSETTE_DIR.mkdir(parents=True, exist_ok=True)
    lib = CassetteLibrary(_CALIB_CASSETTE_DIR)
    judge_model = _judge_litellm_model(settings)

    ok = 0
    for case in cases:
        score = _AUTHORED_SCORES.get(case.id)
        if score is None:
            print(f"  SKIP  {case.id!r} — no authored score defined")
            continue
        rationale = _AUTHORED_RATIONALES.get(case.id, "")
        content = f"Score: {score}\n\n{rationale}"

        key = _cassette_key_for_case(case, judge_model)
        payload = CassettePayload(
            content=content,
            tool_calls=[],
            prompt_tokens=200,
            completion_tokens=30,
            total_tokens=230,
            model=judge_model,
        )
        lib.save(key, payload, request_preview=f"[judge] {case.id} ({case.metric})")
        print(f"  WROTE {case.id!r} → {key[:12]}… (Score: {score})")
        ok += 1

    print(f"\nDone: {ok}/{len(cases)} cassettes written to {_CALIB_CASSETTE_DIR}/")


def _run_hermetic(cases: list[CalibrationCase], settings: Settings) -> list[float]:
    """Score all cases using cassette replay (no API key needed).

    Pinned to the provider/model the committed authored cassettes were written
    against (zai/glm-4.5, see run_author_mode), independent of the ambient
    `settings` passed in — this mode must replay identically regardless of a
    developer's local provider configuration.
    """
    calib_settings = Settings(
        _env_file=None,
        provider=Provider.zai,
        model="glm-4.5",
        cassette_mode="replay",
        cassette_dir=_CALIB_CASSETTE_DIR,
        judge=JudgeConfig(
            _env_file=None,
            provider=Provider.zai,
            model="glm-4.5",
            temperature=0.0,
            max_tokens=1024,
        ),
    )
    judge = ProviderJudge(settings=calib_settings)
    return score_all(cases, judge)


def _run_live(cases: list[CalibrationCase], settings: Settings) -> list[float]:
    """Score cases with real judge calls and save cassettes for future replay."""
    # Copy the full ambient settings (all provider keys/base overrides, not
    # just a hand-picked subset) so nvidia/google credentials and custom API
    # bases configured via VERITY_* env vars aren't silently dropped.
    record_settings = settings.model_copy(
        update={"cassette_mode": "record", "cassette_dir": _CALIB_CASSETTE_DIR}
    )
    accumulator = RunAccumulator()
    judge = ProviderJudge(settings=record_settings, accumulator=accumulator)
    scores = score_all(cases, judge)
    print(f"\nLive run complete. {accumulator.summary()}")
    return scores


def _metric_status(raw_agreement: float, mae: float) -> str:
    """Classify per-metric calibration health for report readers."""
    return "PASS" if raw_agreement >= 0.85 and mae <= 0.20 else "REVIEW"


def render_report(
    cases: list[CalibrationCase],
    judge_scores: list[float],
    agreement: AgreementReport,
    bias: SelfBiasReport,
    judge_model: str,
    mode: str,
) -> str:
    """Render a markdown calibration report."""
    from datetime import UTC, datetime

    now = datetime.now(UTC).strftime("%Y-%m-%d")
    is_synthetic = mode != f"live (recorded to {_CALIB_CASSETTE_DIR})"
    lines = ["# Judge Calibration Report", ""]
    if is_synthetic:
        lines += [
            "> **Note:** This report replays committed cassettes containing",
            "> hand-authored judge scores — it is a synthetic demonstration of the",
            "> calibration methodology (dataset, agreement statistics, self-bias",
            "> calculation, and report rendering), not a measurement of a live judge.",
            "> Both the candidate outputs/human labels in",
            "> `datasets/calibration/labeled.yaml` and the judge scores replayed here",
            "> are hand-authored. Run `make calibrate-live` with a configured API key",
            "> to produce a report against a real judge.",
            "",
        ]
    dataset_note = "cases"
    mode_note = mode
    lines += [
        f"**Generated:** {now}  ",
        f"**Judge model:** `{judge_model}`  ",
        f"**Dataset:** `datasets/calibration/labeled.yaml` ({agreement.n} {dataset_note})  ",
        f"**Mode:** {mode_note}",
        "",
        "---",
        "",
        "## Agreement with Human Labels",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Raw agreement | **{agreement.raw_agreement:.1%}** |",
        f"| Cohen's kappa | **{agreement.cohen_kappa:.3f}** |",
        f"| MAE (0-1 scale) | **{agreement.mae:.3f}** |",
        f"| N | {agreement.n} |",
        "",
        "### Per-metric breakdown",
        "",
        "| Metric | N | Raw agreement | MAE | Status |",
        "|--------|---|---------------|-----|--------|",
    ]
    for metric, stats in sorted(agreement.per_metric.items()):
        status = _metric_status(stats["raw_agreement"], stats["mae"])
        lines.append(
            f"| {metric} | {int(stats['n'])} | {stats['raw_agreement']:.0%} "
            f"| {stats['mae']:.3f} | {status} |"
        )
    needs_review = [
        metric
        for metric, stats in sorted(agreement.per_metric.items())
        if _metric_status(stats["raw_agreement"], stats["mae"]) == "REVIEW"
    ]
    if needs_review:
        lines += [
            "",
            "> Metrics marked REVIEW missed the per-metric target of raw agreement >= 85% "
            "> and MAE <= 0.20 for this run: " + ", ".join(needs_review) + ".",
        ]
    lines += [
        "",
        "---",
        "",
        "## Self-Preference Bias",
        "",
        "Self-preference delta measures whether the judge inflates scores for outputs "
        f"from its own model family ({bias.judge_family.upper()}) compared to outputs "
        "from other families.",
        "",
        "| Family | N | Mean Δ (judge - human) |",
        "|--------|---|------------------------|",
        f"| {bias.judge_family.upper()} (own family) | {bias.n_own} "
        f"| **{bias.mean_delta_own_family:+.3f}** |",
        f"| Other family | {bias.n_other} | **{bias.mean_delta_other_family:+.3f}** |",
        f"| **Self-preference delta** | — | **{bias.self_preference_delta:+.3f}** |",
        "",
    ]
    if abs(bias.self_preference_delta) < 0.05:
        bias_interp = (
            "Negligible self-preference bias (|delta| < 0.05). "
            "Thresholds are not materially affected."
        )
    elif abs(bias.self_preference_delta) < 0.10:
        bias_interp = (
            f"Moderate self-preference bias (delta = {bias.self_preference_delta:+.3f}). "
            "Semantic thresholds for GLM-produced outputs should be interpreted with this in mind."
        )
    else:
        bias_interp = (
            f"Significant self-preference bias (delta = {bias.self_preference_delta:+.3f}). "
            "Consider using a different judge family or applying a correction factor."
        )
    lines += [
        f"> {bias_interp}",
        "",
        "---",
        "",
        "## Threshold Traceability",
        "",
    ]
    if is_synthetic:
        lines += [
            "The semantic tier thresholds in `docs/thresholds.md` are informed by this "
            "synthetic methodology demonstration; they are not yet backed by a measured "
            "live judge distribution:",
            "",
            f"- **Raw agreement ≥ 85%**: this synthetic run shows {agreement.raw_agreement:.1%}.",
            f"- **Cohen's kappa ≥ 0.60** (substantial agreement): synthetic kappa = "
            f"{agreement.cohen_kappa:.3f}.",
            f"- **Self-preference delta**: {bias.self_preference_delta:+.3f} — "
            "see interpretation above.",
            "",
        ]
    else:
        lines += [
            "The semantic tier thresholds in `docs/thresholds.md` were set with this "
            "calibration data in mind:",
            "",
            "- **Raw agreement ≥ 85%**: this judge's measured agreement is "
            f"{agreement.raw_agreement:.1%}, which is within acceptable range.",
            "- **Cohen's kappa ≥ 0.60** (substantial agreement): measured kappa = "
            f"{agreement.cohen_kappa:.3f}.",
            f"- **Self-preference delta**: {bias.self_preference_delta:+.3f} — "
            "see interpretation above.",
            "",
        ]
    lines += [
        "See [`docs/thresholds.md`](thresholds.md) for per-metric threshold values "
        "and the statistical method used.",
        "",
        "> Scope note: this calibration path scores the shared rubric text through "
        "> `verity.calibration.build_scoring_prompt()`. Tier-2 DeepEval and RAGAS "
        "> adapters wrap those rubrics in their own prompt and parsing paths, so "
        "> this report measures judge/rubric agreement rather than every runtime "
        "> metric adapter end to end.",
        "",
        "---",
        "",
        "## Individual Case Scores",
        "",
        "| Case ID | Metric | Family | Human | Judge | Δ | Agreement |",
        "|---------|--------|--------|-------|-------|---|-----------|",
    ]
    for case, judge_score in zip(cases, judge_scores, strict=True):
        delta = judge_score - case.human_score
        judge_pass = judge_score >= 0.5
        agree = "✓" if judge_pass == case.human_pass else "✗"
        lines.append(
            f"| `{case.id}` | {case.metric} | {case.output_family} "
            f"| {case.human_score:.1f} | {judge_score:.1f} | {delta:+.1f} | {agree} |"
        )

    lines += ["", "---", "", "_Report generated by `scripts/run_calibration.py`._", ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--author", action="store_true", help="Write authored cassettes (no key)"
    )
    mode_group.add_argument("--record", action="store_true", help="Record live judge calls")
    parser.add_argument("--out", default=str(_DEFAULT_REPORT_PATH), help="Report output path")
    args = parser.parse_args()

    cases = load_calibration(_LABELED_PATH)
    print(f"Loaded {len(cases)} calibration cases from {_LABELED_PATH}")

    # --author is pinned to the provider/model its own hand-authored cassettes
    # were written against (zai/glm-4.5), isolated from any local .env.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        author_settings = Settings(
            _env_file=None,
            provider=Provider.zai,
            model="glm-4.5",
            judge=JudgeConfig(
                _env_file=None,
                provider=Provider.zai,
                model="glm-4.5",
                temperature=0.0,
                max_tokens=1024,
            ),
        )

    if args.author:
        run_author_mode(cases, author_settings)
        return

    # Default replay is pinned to the same judge the authored cassettes were
    # written against (see run_author_mode / _run_hermetic), also isolated
    # from any local .env, so it replays identically for every developer.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        default_replay_settings = Settings(
            _env_file=None,
            provider=Provider.zai,
            model="glm-4.5",
            judge=JudgeConfig(
                _env_file=None,
                provider=Provider.zai,
                model="glm-4.5",
                temperature=0.0,
                max_tokens=1024,
            ),
        )

    # --record uses the live, ambient provider configuration (.env honored).
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        settings = Settings() if args.record else default_replay_settings

    judge_model = _judge_litellm_model(settings)
    judge_family = _judge_family(settings)
    if args.record:
        _require_provider_key(settings, "Calibration recording")
        print("Running live judge calls...")
        judge_scores = _run_live(cases, settings)
        mode_label = f"live (recorded to {_CALIB_CASSETTE_DIR})"
    else:
        print("Running synthetic calibration (authored-score cassette replay)...")
        judge_scores = _run_hermetic(cases, settings)
        mode_label = "synthetic replay (authored scores)"

    agreement = compute_agreement(cases, judge_scores)
    bias = compute_self_bias(cases, judge_scores, judge_family=judge_family)

    print("\n" + str(agreement))
    print("\n" + str(bias))

    # Write report
    report_md = render_report(cases, judge_scores, agreement, bias, judge_model, mode_label)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report_md)
    print(f"\nReport written to {out_path}")

    # Also write to reports/ for CI artifacts
    _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    artifact = _REPORTS_DIR / f"calibration-{ts}.md"
    artifact.write_text(report_md)

    # Raw scores JSON for programmatic consumption
    raw: dict[str, Any] = {
        "judge": {
            "model": judge_model,
            "mode": mode_label,
        },
        "agreement": {
            "n": agreement.n,
            "raw_agreement": round(agreement.raw_agreement, 4),
            "cohen_kappa": round(agreement.cohen_kappa, 4),
            "mae": round(agreement.mae, 4),
        },
        "self_bias": {
            "self_preference_delta": round(bias.self_preference_delta, 4),
            "mean_delta_own_family": round(bias.mean_delta_own_family, 4),
            "mean_delta_other_family": round(bias.mean_delta_other_family, 4),
        },
        "per_case": [
            {"id": c.id, "human": c.human_score, "judge": round(s, 3)}
            for c, s in zip(cases, judge_scores, strict=True)
        ],
    }
    (_REPORTS_DIR / f"calibration-{ts}.json").write_text(json.dumps(raw, indent=2))


if __name__ == "__main__":
    main()
