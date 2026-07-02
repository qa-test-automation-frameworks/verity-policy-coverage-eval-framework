"""Historical trend storage for pass rate, latency, and cost across test runs.

Each test-suite run appends one JSON line to reports/trends/<tier>.jsonl so
pass-rate/latency/cost drift can be tracked over time. reports/ is a CI/local
artifact directory (gitignored) — this is not committed history, it's a
rolling local/CI log a report-site step can chart.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from verity.cost import RunAccumulator
from verity.latency import LatencyReport, check_latency_budget

_TRENDS_DIR = Path("reports/trends")


def _current_git_sha() -> str:
    """Best-effort git SHA for the current checkout, so a trend record can be
    traced back to the exact commit that produced it. CI sets GITHUB_SHA;
    local runs fall back to `git rev-parse HEAD`; either failing yields
    "unknown" rather than raising, since trend recording must not fail a
    test run over a missing git binary."""
    env_sha = os.environ.get("GITHUB_SHA")
    if env_sha:
        return env_sha
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5, check=True
        )
        return result.stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return "unknown"


@dataclass(frozen=True)
class TrendRecord:
    tier: str
    timestamp: float
    total: int
    passed: int
    failed: int
    pass_rate: float
    latency_p50_ms: float
    latency_p95_ms: float
    total_tokens: int
    total_cost_usd: float
    retrieval_quality: float | None = None
    extra: dict[str, float] = field(default_factory=dict)
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    git_sha: str = field(default_factory=_current_git_sha)


def compute_trend_record(
    tier: str,
    node_results: dict[str, str],
    accumulator: RunAccumulator,
    latency_budget_ms: float,
    retrieval_quality: float | None = None,
) -> TrendRecord:
    """Build a TrendRecord from a completed test session's results and cost accumulator."""
    total = len(node_results)
    passed = sum(1 for outcome in node_results.values() if outcome == "passed")
    failed = total - passed
    pass_rate = passed / total if total else 1.0

    latency: LatencyReport = check_latency_budget(accumulator, latency_budget_ms)
    totals = accumulator.total_tokens
    cost = accumulator.total_cost

    return TrendRecord(
        tier=tier,
        timestamp=time.time(),
        total=total,
        passed=passed,
        failed=failed,
        pass_rate=pass_rate,
        latency_p50_ms=latency.p50_ms,
        latency_p95_ms=latency.p95_ms,
        total_tokens=totals.total_tokens,
        total_cost_usd=cost.total_usd,
        retrieval_quality=retrieval_quality,
    )


def append_trend(record: TrendRecord, trends_dir: Path | None = None) -> Path:
    """Append a trend record as one JSON line to reports/trends/<tier>.jsonl."""
    d = trends_dir or _TRENDS_DIR
    d.mkdir(parents=True, exist_ok=True)
    out = d / f"{record.tier}.jsonl"
    with out.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(record)) + "\n")
    return out


def load_trend_history(tier: str, trends_dir: Path | None = None) -> list[TrendRecord]:
    """Load all historical trend records for a tier, oldest first."""
    d = trends_dir or _TRENDS_DIR
    path = d / f"{tier}.jsonl"
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        records.append(TrendRecord(**json.loads(line)))
    return records
