"""Judge calibration schema, statistics, and scoring harness.

Calibration measures how well the configured LLM judge agrees with human
annotations, and quantifies self-preference bias (inflated scores when the
judge evaluates outputs from its own model family).

Key exports:
    CalibrationCase   - typed schema for a single labeled item
    load_calibration  - loader for datasets/calibration/labeled.yaml
    AgreementReport   - raw %, Cohen's kappa, MAE vs human labels
    SelfBiasReport    - self_preference_delta = E[delta | glm] - E[delta | other]
    compute_agreement - compute AgreementReport from labels + judge scores
    compute_self_bias - compute SelfBiasReport from labels + judge scores
    build_scoring_prompt - deterministic rubric-based scoring prompt
    parse_judge_score - extract normalized 0-1 score from judge text
    score_case        - run one calibration case through the judge
    score_all         - run all cases, returning a list of scores
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


class CalibrationCase(BaseModel):
    """A single human-annotated example for judge calibration."""

    id: str
    metric: Literal["completeness", "disambiguation", "refusal", "faithfulness"]
    query: str
    context: list[str] = Field(default_factory=list)
    candidate_output: str
    output_family: Literal["glm", "other"]
    human_score: float  # 0.0 - 1.0
    human_pass: bool
    rationale: str = ""


def load_calibration(path: Path) -> list[CalibrationCase]:
    """Load all calibration cases from a YAML file."""
    with path.open() as fh:
        raw: Any = yaml.safe_load(fh)
    if not isinstance(raw, dict):
        return []
    return [CalibrationCase.model_validate(item) for item in raw.get("cases", [])]


# ---------------------------------------------------------------------------
# Agreement statistics
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AgreementReport:
    """Summary of judge-vs-human agreement across all calibration cases."""

    n: int
    raw_agreement: float  # fraction where judge_pass == human_pass
    cohen_kappa: float
    mae: float  # mean |judge_score - human_score|
    per_metric: dict[str, dict[str, float]]  # metric -> {raw_agreement, mae, n}

    def __str__(self) -> str:
        lines = [
            f"Agreement Report (n={self.n})",
            f"  Raw agreement : {self.raw_agreement:.1%}",
            f"  Cohen's kappa : {self.cohen_kappa:.3f}",
            f"  MAE (0-1)     : {self.mae:.3f}",
            "  Per metric:",
        ]
        for metric, stats in sorted(self.per_metric.items()):
            lines.append(
                f"    {metric:<20} n={int(stats['n'])}  "
                f"agree={stats['raw_agreement']:.0%}  "
                f"mae={stats['mae']:.3f}"
            )
        return "\n".join(lines)


@dataclass(frozen=True)
class SelfBiasReport:
    """Quantifies self-preference: does the judge inflate scores for its own family?

    self_preference_delta > 0 means the judge is more lenient on GLM-family outputs.
    """

    self_preference_delta: float  # mean_delta_own - mean_delta_other
    mean_delta_own_family: float  # mean(judge - human) for output_family="glm"
    mean_delta_other_family: float  # mean(judge - human) for output_family="other"
    n_own: int
    n_other: int

    def __str__(self) -> str:
        sign = "+" if self.self_preference_delta >= 0 else ""
        return (
            f"Self-Bias Report\n"
            f"  GLM-family outputs   (n={self.n_own}): "
            f"mean delta = {self.mean_delta_own_family:+.3f}\n"
            f"  Other-family outputs (n={self.n_other}): "
            f"mean delta = {self.mean_delta_other_family:+.3f}\n"
            f"  Self-preference delta: {sign}{self.self_preference_delta:.3f}"
        )


def compute_agreement(
    cases: list[CalibrationCase],
    judge_scores: list[float],
    judge_threshold: float = 0.5,
) -> AgreementReport:
    """Compute judge-vs-human agreement statistics.

    Parameters
    ----------
    cases:
        Human-labeled calibration cases.
    judge_scores:
        Float scores in [0, 1] from the judge, one per case (same order).
    judge_threshold:
        Threshold for converting judge float score -> binary pass/fail.
    """
    n = len(cases)
    if n == 0:
        raise ValueError("Cannot compute agreement over zero cases")
    if len(judge_scores) != n:
        raise ValueError(
            f"cases ({n}) and judge_scores ({len(judge_scores)}) must have the same length"
        )

    judge_passes = [s >= judge_threshold for s in judge_scores]

    # Raw agreement
    agree_count = sum(jp == c.human_pass for jp, c in zip(judge_passes, cases, strict=True))
    raw_agreement = agree_count / n

    # Cohen's kappa (binary classification)
    p_o = raw_agreement
    p_human_pass = sum(c.human_pass for c in cases) / n
    p_judge_pass = sum(judge_passes) / n
    p_e = p_human_pass * p_judge_pass + (1 - p_human_pass) * (1 - p_judge_pass)
    cohen_kappa = (p_o - p_e) / (1 - p_e) if (1 - p_e) > 1e-9 else 0.0

    # Mean Absolute Error
    mae = sum(abs(js - c.human_score) for js, c in zip(judge_scores, cases, strict=True)) / n

    # Per-metric breakdown
    metrics = sorted({c.metric for c in cases})
    per_metric: dict[str, dict[str, float]] = {}
    for metric in metrics:
        idxs = [i for i, c in enumerate(cases) if c.metric == metric]
        if not idxs:
            continue
        m_agree = sum(judge_passes[i] == cases[i].human_pass for i in idxs) / len(idxs)
        m_mae = sum(abs(judge_scores[i] - cases[i].human_score) for i in idxs) / len(idxs)
        per_metric[metric] = {"raw_agreement": m_agree, "mae": m_mae, "n": float(len(idxs))}

    return AgreementReport(
        n=n,
        raw_agreement=raw_agreement,
        cohen_kappa=cohen_kappa,
        mae=mae,
        per_metric=per_metric,
    )


def compute_self_bias(
    cases: list[CalibrationCase],
    judge_scores: list[float],
) -> SelfBiasReport:
    """Quantify self-preference bias.

    delta = judge_score - human_score per case.
    self_preference_delta = mean(delta on glm outputs) - mean(delta on other outputs).
    A positive delta means the judge is more lenient on its own family's outputs.
    """
    if len(cases) != len(judge_scores):
        raise ValueError("cases and judge_scores must have the same length")

    own = [(c, s) for c, s in zip(cases, judge_scores, strict=True) if c.output_family == "glm"]
    other = [(c, s) for c, s in zip(cases, judge_scores, strict=True) if c.output_family == "other"]

    def _mean_delta(pairs: list[tuple[CalibrationCase, float]]) -> float:
        if not pairs:
            return 0.0
        return sum(s - c.human_score for c, s in pairs) / len(pairs)

    mean_own = _mean_delta(own)
    mean_other = _mean_delta(other)

    return SelfBiasReport(
        self_preference_delta=mean_own - mean_other,
        mean_delta_own_family=mean_own,
        mean_delta_other_family=mean_other,
        n_own=len(own),
        n_other=len(other),
    )


# ---------------------------------------------------------------------------
# Scoring functions (live judge calls)
# ---------------------------------------------------------------------------

_METRIC_RUBRIC_MAP: dict[str, str] = {}  # populated lazily from rubrics.py


def _get_rubric(metric: str) -> str:
    if not _METRIC_RUBRIC_MAP:
        from verity.metrics.rubrics import (
            COMPLETENESS_RUBRIC,
            DISAMBIGUATION_RUBRIC,
            FAITHFULNESS_RUBRIC,
            REFUSAL_RUBRIC,
        )

        _METRIC_RUBRIC_MAP.update(
            {
                "completeness": COMPLETENESS_RUBRIC,
                "disambiguation": DISAMBIGUATION_RUBRIC,
                "refusal": REFUSAL_RUBRIC,
                "faithfulness": FAITHFULNESS_RUBRIC,
            }
        )
    return _METRIC_RUBRIC_MAP[metric]


def build_scoring_prompt(case: CalibrationCase) -> str:
    """Build the deterministic scoring prompt sent to the judge.

    The prompt is deterministic (depends only on the case fields), making the
    cassette key stable and the replay hermetic.
    """
    rubric = _get_rubric(case.metric)
    context_block = "\n".join(f"{i + 1}. {c}" for i, c in enumerate(case.context))
    return (
        f"{rubric}\n"
        f"Query: {case.query}\n"
        f"---\n"
        f"Retrieved context:\n{context_block or '(none)'}\n"
        f"---\n"
        f"Candidate response:\n{case.candidate_output}\n"
        f"---\n"
        "Respond with ONLY the score using this exact format:\n"
        "Score: N\n"
        "where N is an integer from 0 to 10."
    )


_SCORE_PATTERN = re.compile(r"[Ss]core[:\s]+(\d+(?:\.\d+)?)")


def parse_judge_score(text: str) -> float:
    """Extract a 0-1 normalized score from strict `Score: N` judge text."""
    m = _SCORE_PATTERN.search(text)
    if not m:
        return 0.0
    raw = float(m.group(1))
    return min(max(raw / 10.0, 0.0), 1.0)


def score_case(case: CalibrationCase, judge: Any) -> float:
    """Score a single calibration case using the judge.

    Parameters
    ----------
    case:
        A CalibrationCase with the rubric-appropriate fields.
    judge:
        A ProviderJudge (or any object with a .generate(prompt: str) -> str method).
    """
    prompt = build_scoring_prompt(case)
    response = judge.generate(prompt)
    return parse_judge_score(response)


def score_all(cases: list[CalibrationCase], judge: Any) -> list[float]:
    """Score all calibration cases and return a list of 0-1 scores."""
    return [score_case(c, judge) for c in cases]
