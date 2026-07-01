"""Latency budgets for LLM calls, checked per tier.

Cassette replay (deterministic/adversarial tiers) should be near-instant —
a budget violation there signals something unexpected (e.g. accidental
network I/O sneaking into a "hermetic" test path), not model slowness.
Live tiers (semantic) have a real, higher budget reflecting actual
provider round-trip time.
"""

from __future__ import annotations

from dataclasses import dataclass

from verity.cost import CallRecord, RunAccumulator

# Budgets in milliseconds. Deterministic replay does no network I/O, so even
# a generous budget here is a meaningful tripwire; live calls get a much
# larger budget to allow for real provider latency.
DETERMINISTIC_BUDGET_MS = 50.0
LIVE_BUDGET_MS = 30_000.0


@dataclass(frozen=True)
class LatencyViolation:
    label: str
    latency_ms: float
    budget_ms: float


@dataclass(frozen=True)
class LatencyReport:
    n: int
    budget_ms: float
    p50_ms: float
    p95_ms: float
    max_ms: float
    violations: list[LatencyViolation]

    @property
    def passed(self) -> bool:
        return not self.violations


def _percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    idx = min(len(sorted_values) - 1, round(pct / 100 * (len(sorted_values) - 1)))
    return sorted_values[idx]


def check_latency_budget(accumulator: RunAccumulator, budget_ms: float) -> LatencyReport:
    """Check every recorded call's latency against a fixed budget."""
    records: list[CallRecord] = accumulator.records
    latencies = sorted(r.latency_ms for r in records)
    violations = [
        LatencyViolation(label=r.label or "unlabeled", latency_ms=r.latency_ms, budget_ms=budget_ms)
        for r in records
        if r.latency_ms > budget_ms
    ]
    return LatencyReport(
        n=len(records),
        budget_ms=budget_ms,
        p50_ms=_percentile(latencies, 50),
        p95_ms=_percentile(latencies, 95),
        max_ms=max(latencies) if latencies else 0.0,
        violations=violations,
    )
