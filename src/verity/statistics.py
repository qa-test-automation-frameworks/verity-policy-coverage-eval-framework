"""Statistical threshold engine for N-sample non-deterministic evaluation.

LLM responses are non-deterministic. Single-sample pass/fail metrics are
unreliable. This module runs N evaluations of the same query and aggregates
the distribution of scores before applying a threshold, reducing false failures
from token-sampling variance.

Typical usage:
    stat = aggregate(scores)
    passed = threshold_pass(stat, threshold=0.7, mode="mean")
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class StatResult:
    """Aggregated statistics over a sample of scores."""

    scores: list[float]
    mean: float
    median: float
    stdev: float
    pass_rate: float   # fraction of scores above the pass threshold
    n: int

    def __str__(self) -> str:
        return (
            f"StatResult(n={self.n}, mean={self.mean:.3f}, median={self.median:.3f}, "
            f"stdev={self.stdev:.3f}, pass_rate={self.pass_rate:.2%})"
        )


def run_n_samples(
    fn: Callable[[], float],
    n: int,
    score_threshold: float = 0.5,
) -> StatResult:
    """Run fn() n times and return aggregated statistics.

    Parameters
    ----------
    fn:
        Callable returning a float score in [0, 1] for a single evaluation run.
    n:
        Number of independent runs. Must be >= 1.
    score_threshold:
        Individual score threshold used to compute pass_rate.

    Returns
    -------
    StatResult
        Aggregated statistics over all n runs.
    """
    if n < 1:
        raise ValueError(f"n must be >= 1, got {n}")
    scores = [fn() for _ in range(n)]
    return aggregate(scores, score_threshold=score_threshold)


def aggregate(
    scores: list[float],
    score_threshold: float = 0.5,
) -> StatResult:
    """Aggregate a list of float scores into a StatResult.

    Parameters
    ----------
    scores:
        List of scores in [0, 1].
    score_threshold:
        Per-sample threshold for computing pass_rate.
    """
    if not scores:
        raise ValueError("scores must be non-empty")
    n = len(scores)
    mean = sum(scores) / n
    median = statistics.median(scores)
    stdev = statistics.stdev(scores) if n > 1 else 0.0
    pass_rate = sum(1 for s in scores if s >= score_threshold) / n
    return StatResult(
        scores=list(scores),
        mean=mean,
        median=median,
        stdev=stdev,
        pass_rate=pass_rate,
        n=n,
    )


def threshold_pass(
    stat: StatResult,
    threshold: float,
    mode: str = "mean",
) -> bool:
    """Return True if the stat result passes the threshold under the given mode.

    Parameters
    ----------
    stat:
        StatResult from aggregate() or run_n_samples().
    threshold:
        Numerical threshold (float in [0, 1]).
    mode:
        One of "mean", "median", "pass_rate", or "all".
        - "mean":      stat.mean >= threshold
        - "median":    stat.median >= threshold
        - "pass_rate": stat.pass_rate >= threshold (fraction of runs that passed)
        - "all":       all three of the above must hold
    """
    valid_modes = ("mean", "median", "pass_rate", "all")
    if mode not in valid_modes:
        raise ValueError(f"mode must be one of {valid_modes}, got {mode!r}")
    if mode == "mean":
        return stat.mean >= threshold
    if mode == "median":
        return stat.median >= threshold
    if mode == "pass_rate":
        return stat.pass_rate >= threshold
    return stat.mean >= threshold and stat.median >= threshold and stat.pass_rate >= threshold
