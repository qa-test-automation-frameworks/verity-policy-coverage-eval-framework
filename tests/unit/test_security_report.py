"""Unit tests for the adversarial security summary artifact."""

from __future__ import annotations

import json
from pathlib import Path

from verity.adversarial import AdversarialProbe
from verity.security_report import (
    build_security_summary,
    render_security_summary_markdown,
    write_security_summary,
)


def _probe(pid: str, category: str) -> AdversarialProbe:
    return AdversarialProbe(
        id=pid,
        category=category,  # type: ignore[arg-type]
        prompt="test",
        defense="no_pii",
        expected_outcome="defended",
    )


class TestBuildSecuritySummary:
    def test_counts_defended_and_breached(self) -> None:
        results = {
            "p1": ("DEFENDED", ""),
            "p2": ("BREACHED", "leak"),
            "p3": ("DEFENDED", ""),
        }
        probes = [
            _probe("p1", "pii_extraction"),
            _probe("p2", "injection"),
            _probe("p3", "jailbreak"),
        ]
        summary = build_security_summary(results, probes)
        assert summary.total == 3
        assert summary.defended == 2
        assert summary.breached == 1

    def test_category_breakdown(self) -> None:
        results = {"p1": ("DEFENDED", ""), "p2": ("BREACHED", ""), "p3": ("DEFENDED", "")}
        probes = [
            _probe("p1", "pii_extraction"),
            _probe("p2", "pii_extraction"),
            _probe("p3", "jailbreak"),
        ]
        summary = build_security_summary(results, probes)
        by_cat = {t.category: t for t in summary.by_category}
        assert by_cat["pii_extraction"].defended == 1
        assert by_cat["pii_extraction"].breached == 1
        assert by_cat["jailbreak"].defended == 1
        assert by_cat["jailbreak"].breached == 0

    def test_probe_outcomes_preserved(self) -> None:
        results = {"p1": ("DEFENDED", "detail")}
        probes = [_probe("p1", "tool_abuse")]
        summary = build_security_summary(results, probes)
        assert summary.probe_outcomes == {"p1": "DEFENDED"}

    def test_unknown_probe_id_falls_back_to_unknown_category(self) -> None:
        results = {"ghost": ("DEFENDED", "")}
        summary = build_security_summary(results, [])
        assert summary.by_category[0].category == "unknown"


class TestRenderMarkdown:
    def test_markdown_contains_totals(self) -> None:
        results = {"p1": ("DEFENDED", ""), "p2": ("BREACHED", "")}
        probes = [_probe("p1", "injection"), _probe("p2", "injection")]
        summary = build_security_summary(results, probes)
        md = render_security_summary_markdown(summary)
        assert "**Total probes:** 2" in md
        assert "**Defended:** 1" in md
        assert "**Breached:** 1" in md
        assert "p1" in md
        assert "p2" in md


class TestWriteSecuritySummary:
    def test_writes_markdown_and_json(self, tmp_path: Path) -> None:
        results = {"p1": ("DEFENDED", "")}
        probes = [_probe("p1", "injection")]
        summary = build_security_summary(results, probes)

        md_path = tmp_path / "summary.md"
        json_path = tmp_path / "summary.json"
        write_security_summary(summary, md_path=md_path, json_path=json_path)

        assert md_path.exists()
        assert json_path.exists()
        data = json.loads(json_path.read_text())
        assert data["total"] == 1
        assert data["defended"] == 1
