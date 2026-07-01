"""Adversarial (Tier-3) security summary artifact.

Renders the DEFENDED/BREACHED outcome of every adversarial probe into a
persistent markdown + JSON artifact, distinct from docs/defects-caught.md
(which documents the seeded-defect *design* catalog). This artifact reflects
an actual test run's measured security posture: how many probes per attack
category were defended vs. breached.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from verity.adversarial import AdversarialProbe

_DEFAULT_MD_PATH = Path("reports/security/summary.md")
_DEFAULT_JSON_PATH = Path("reports/security/summary.json")


@dataclass(frozen=True)
class CategoryTally:
    category: str
    defended: int
    breached: int

    @property
    def total(self) -> int:
        return self.defended + self.breached


@dataclass(frozen=True)
class SecuritySummary:
    total: int
    defended: int
    breached: int
    by_category: list[CategoryTally]
    probe_outcomes: dict[str, str]  # probe_id -> "DEFENDED" | "BREACHED"


def build_security_summary(
    vulnerability_results: dict[str, tuple[str, str]],
    probes: list[AdversarialProbe],
) -> SecuritySummary:
    """Build a SecuritySummary from per-probe (outcome, detail) results."""
    probes_by_id = {p.id: p for p in probes}
    by_category: dict[str, list[int]] = {}  # category -> [defended, breached]

    for probe_id, (outcome, _detail) in vulnerability_results.items():
        probe = probes_by_id.get(probe_id)
        category = probe.category if probe else "unknown"
        tally = by_category.setdefault(category, [0, 0])
        if outcome == "DEFENDED":
            tally[0] += 1
        else:
            tally[1] += 1

    category_tallies = [
        CategoryTally(category=cat, defended=d, breached=b)
        for cat, (d, b) in sorted(by_category.items())
    ]
    defended = sum(1 for o, _ in vulnerability_results.values() if o == "DEFENDED")
    breached = sum(1 for o, _ in vulnerability_results.values() if o == "BREACHED")

    return SecuritySummary(
        total=len(vulnerability_results),
        defended=defended,
        breached=breached,
        by_category=category_tallies,
        probe_outcomes={pid: outcome for pid, (outcome, _) in vulnerability_results.items()},
    )


def render_security_summary_markdown(summary: SecuritySummary) -> str:
    """Render a SecuritySummary as a markdown report."""
    lines = [
        "# Adversarial Security Summary",
        "",
        f"**Total probes:** {summary.total}  ",
        f"**Defended:** {summary.defended}  ",
        f"**Breached:** {summary.breached}",
        "",
        "## By Attack Category",
        "",
        "| Category | Defended | Breached | Total |",
        "|----------|---------:|---------:|------:|",
    ]
    for tally in summary.by_category:
        lines.append(f"| {tally.category} | {tally.defended} | {tally.breached} | {tally.total} |")
    lines += ["", "## Per-Probe Outcomes", "", "| Probe ID | Outcome |", "|----------|---------|"]
    for probe_id, outcome in sorted(summary.probe_outcomes.items()):
        marker = "✓ DEFENDED" if outcome == "DEFENDED" else "✗ BREACHED"
        lines.append(f"| `{probe_id}` | {marker} |")
    lines.append("")
    return "\n".join(lines)


def write_security_summary(
    summary: SecuritySummary,
    md_path: Path | None = None,
    json_path: Path | None = None,
) -> tuple[Path, Path]:
    """Write both markdown and JSON forms of a SecuritySummary to disk."""
    md_out = md_path or _DEFAULT_MD_PATH
    json_out = json_path or _DEFAULT_JSON_PATH
    md_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.parent.mkdir(parents=True, exist_ok=True)
    md_out.write_text(render_security_summary_markdown(summary), encoding="utf-8")
    json_out.write_text(json.dumps(asdict(summary), indent=2), encoding="utf-8")
    return md_out, json_out
