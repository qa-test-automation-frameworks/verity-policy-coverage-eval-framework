"""Per-module coverage gates for critical areas of the codebase.

The global `--cov-fail-under=80` gate in pr-gate.yml can pass even while a
specific critical module (the agent loop, retrieval, metric adapters,
tracing, reporting) quietly drops well below that average, as long as other
well-tested modules pull the total back up. This script reads coverage.py's
JSON report and enforces a minimum per-module, so a regression in any one
critical area fails the gate on its own.

Usage:
    uv run coverage json -o reports/coverage.json
    uv run python scripts/check_module_coverage.py reports/coverage.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Module path substring -> minimum required statement coverage percent.
# Thresholds are set a few points below the coverage measured when this gate
# was introduced, so they catch real regressions without being so tight that
# routine refactors trip them.
_CRITICAL_MODULE_THRESHOLDS: dict[str, float] = {
    "src/sut/agent.py": 78.0,
    "src/sut/retriever.py": 90.0,
    "src/verity/metrics/ragas_metrics.py": 75.0,
    "src/verity/metrics/deepeval_metrics.py": 65.0,
    "src/verity/tracing.py": 80.0,
    "src/verity/reporting.py": 95.0,
}


def check_module_coverage(coverage_json_path: Path) -> list[str]:
    """Return a list of failure messages (empty if every critical module passes)."""
    data = json.loads(coverage_json_path.read_text())
    files = data.get("files", {})

    failures: list[str] = []
    for module_path, min_pct in _CRITICAL_MODULE_THRESHOLDS.items():
        entry = files.get(module_path)
        if entry is None:
            failures.append(f"{module_path}: not found in coverage report (0 statements executed?)")
            continue
        actual_pct = entry["summary"]["percent_covered"]
        if actual_pct < min_pct:
            failures.append(
                f"{module_path}: {actual_pct:.1f}% coverage, below required {min_pct:.1f}%"
            )
    return failures


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: check_module_coverage.py <coverage.json>", file=sys.stderr)
        raise SystemExit(2)

    coverage_json_path = Path(sys.argv[1])
    failures = check_module_coverage(coverage_json_path)

    if failures:
        print("Module-sensitive coverage gate FAILED:")
        for f in failures:
            print(f"  - {f}")
        raise SystemExit(1)

    print("Module-sensitive coverage gate passed for all critical modules.")


if __name__ == "__main__":
    main()
