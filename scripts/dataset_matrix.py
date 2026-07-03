"""Golden dataset coverage matrix: cross-tabulates every case in
datasets/golden/*.yaml by plan tier, risk weight, expectation category,
and seeded-defect linkage, so dataset breadth (and gaps) are visible without
reading all 56 cases by hand.

Makes no live model calls. Usage:
  uv run python scripts/dataset_matrix.py [--out PATH]
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

_SRC = Path(__file__).parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from verity.golden import GoldenCase, load_golden  # noqa: E402

_GOLDEN_DIR = Path("datasets/golden")
_DEFAULT_OUT_PATH = Path("docs/dataset-coverage.md")

_PLAN_TAGS = ("bronze", "silver", "gold")
_TOTAL_DEFECTS = 8


def case_plan(case: GoldenCase) -> str:
    """The plan tier a case exercises, inferred from its tags. A case whose
    tags name no single plan tier (e.g. cross-plan or member-agnostic
    queries) is bucketed as "cross-plan"."""
    matched = [tag for tag in _PLAN_TAGS if tag in case.tags]
    return matched[0] if len(matched) == 1 else "cross-plan"


def _count_rows(counter: Counter[str], total: int) -> list[str]:
    return [f"| {key} | {count} | {count / total:.0%} |" for key, count in sorted(counter.items())]


def render_matrix(cases: list[GoldenCase]) -> str:
    """Render the dataset coverage matrix as markdown."""
    n = len(cases)
    plan_counts = Counter(case_plan(c) for c in cases)
    risk_counts = Counter(c.risk_weight for c in cases)
    category_counts: Counter[str] = Counter()
    for c in cases:
        category_counts.update(c.expectation_categories)
    behavior_counts = Counter(c.behavior for c in cases)

    defect_cases: dict[int, list[str]] = {}
    for c in cases:
        if c.defect_id is not None:
            defect_cases.setdefault(c.defect_id, []).append(c.id)
    covered_defects = sorted(defect_cases)
    missing_defects = sorted(set(range(1, _TOTAL_DEFECTS + 1)) - set(covered_defects))

    lines = [
        "# Dataset Coverage Matrix",
        "",
        f"Cross-tabulation of all {n} cases in `datasets/golden/*.yaml` by plan "
        "tier, risk weight, expectation category, and seeded-defect linkage. "
        "Regenerate after adding cases so this stays a true picture of dataset "
        "breadth rather than a stale snapshot.",
        "",
        "## By plan tier",
        "",
        "| Plan | Cases | Share |",
        "|---|---:|---:|",
        *_count_rows(plan_counts, n),
        "",
        "## By risk weight",
        "",
        "| Risk weight | Cases | Share |",
        "|---|---:|---:|",
        *_count_rows(risk_counts, n),
        "",
        "## By behavior",
        "",
        "| Behavior | Cases | Share |",
        "|---|---:|---:|",
        *_count_rows(behavior_counts, n),
        "",
        "## By expectation category",
        "",
        f"A case may declare more than one category, so counts sum to more than {n}.",
        "",
        "| Category | Cases | Share of dataset |",
        "|---|---:|---:|",
        *_count_rows(category_counts, n),
        "",
        "## Seeded-defect linkage",
        "",
        f"{len(covered_defects)}/{_TOTAL_DEFECTS} seeded defects have at least one "
        "golden case with a matching `defect_id` (see `docs/seeded-defects.md` for "
        "the full catalog).",
        "",
        "| Defect | Cases |",
        "|---|---|",
    ]
    for defect_id in covered_defects:
        case_ids = ", ".join(f"`{cid}`" for cid in sorted(defect_cases[defect_id]))
        lines.append(f"| #{defect_id} | {case_ids} |")
    if missing_defects:
        lines.append("")
        lines.append(
            "**Missing:** "
            + ", ".join(f"#{d}" for d in missing_defects)
            + " have no golden case with a matching `defect_id`."
        )
    lines += ["", "_Regenerate: `make dataset-matrix`._", ""]
    return "\n".join(lines)


def run(out_path: Path = _DEFAULT_OUT_PATH) -> str:
    cases = load_golden(_GOLDEN_DIR)
    report = render_matrix(cases)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(_DEFAULT_OUT_PATH), help="Report output path")
    args = parser.parse_args()

    run(Path(args.out))
    print(f"Report written to {args.out}")


if __name__ == "__main__":
    main()
