"""Unit tests for the defects-caught report generator.

Tests cover the pure rendering and aggregation logic only — no cassette
replay, no file I/O.  The run() function itself is tested separately via
the integration test (make defects-report).
"""

from __future__ import annotations

import copy
from pathlib import Path

from scripts.defects_report import (
    DEFECT_CATALOG,
    DefectEntry,
    _load_defect_risk_weights,
    build_json,
    render_markdown,
    run,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _catalog_with_statuses(
    statuses: dict[int, str],
) -> list[DefectEntry]:
    """Return a copy of the catalog with given defect IDs set to given statuses."""
    catalog = copy.deepcopy(DEFECT_CATALOG)
    for entry in catalog:
        if entry.id in statuses:
            entry.status = statuses[entry.id]  # type: ignore[assignment]
    return catalog


# ---------------------------------------------------------------------------
# DEFECT_CATALOG structure
# ---------------------------------------------------------------------------


class TestCatalogStructure:
    def test_has_eight_entries(self) -> None:
        assert len(DEFECT_CATALOG) == 8

    def test_ids_are_one_through_eight(self) -> None:
        assert [e.id for e in DEFECT_CATALOG] == list(range(1, 9))

    def test_all_entries_have_descriptions(self) -> None:
        for e in DEFECT_CATALOG:
            assert e.description, f"Defect #{e.id} has no description"

    def test_defects_5_to_8_have_deterministic_tier(self) -> None:
        for e in DEFECT_CATALOG:
            if e.id >= 5:
                assert any("Deterministic" in t for t in e.catching_tiers), (
                    f"Defect #{e.id} missing Deterministic tier"
                )

    def test_defects_1_to_4_have_only_semantic_tier(self) -> None:
        for e in DEFECT_CATALOG:
            if e.id <= 4:
                assert e.catching_tiers == ["Tier 2 — Semantic"], (
                    f"Defect #{e.id} catching_tiers unexpected: {e.catching_tiers}"
                )

    def test_defects_7_8_have_adversarial_tier(self) -> None:
        for e in DEFECT_CATALOG:
            if e.id in (7, 8):
                assert any("Adversarial" in t for t in e.catching_tiers), (
                    f"Defect #{e.id} missing Adversarial tier"
                )


# ---------------------------------------------------------------------------
# render_markdown
# ---------------------------------------------------------------------------


class TestRenderMarkdown:
    def test_contains_all_eight_defect_rows(self) -> None:
        catalog = _catalog_with_statuses({5: "CAUGHT", 6: "CAUGHT", 7: "CAUGHT", 8: "CAUGHT"})
        md = render_markdown(catalog)
        for i in range(1, 9):
            assert f"| {i} |" in md, f"Row for defect #{i} missing from markdown"

    def test_caught_shows_checkmark(self) -> None:
        catalog = _catalog_with_statuses({5: "CAUGHT"})
        md = render_markdown(catalog)
        assert "✅ CAUGHT" in md

    def test_covered_shows_square(self) -> None:
        catalog = _catalog_with_statuses({1: "COVERED"})
        md = render_markdown(catalog)
        assert "⬜ COVERED" in md

    def test_missed_shows_cross(self) -> None:
        catalog = _catalog_with_statuses({6: "MISSED"})
        md = render_markdown(catalog)
        assert "❌ MISSED" in md

    def test_verified_shows_checkmark(self) -> None:
        catalog = _catalog_with_statuses({2: "VERIFIED"})
        md = render_markdown(catalog)
        assert "✅ VERIFIED" in md

    def test_hermetic_count_in_header(self) -> None:
        catalog = _catalog_with_statuses({5: "CAUGHT", 6: "CAUGHT", 7: "CAUGHT", 8: "CAUGHT"})
        md = render_markdown(catalog)
        assert "4 of 8 defects caught hermetically" in md

    def test_details_appear_in_output(self) -> None:
        catalog = copy.deepcopy(DEFECT_CATALOG)
        catalog[4].status = "CAUGHT"  # defect #5
        catalog[4].details = ["Deterministic: expected arg mismatch"]
        md = render_markdown(catalog)
        assert "expected arg mismatch" in md

    def test_regenerate_line_present(self) -> None:
        catalog = copy.deepcopy(DEFECT_CATALOG)
        md = render_markdown(catalog)
        assert "make defects-report" in md


# ---------------------------------------------------------------------------
# Risk weight breakdown
# ---------------------------------------------------------------------------


class TestRiskWeightBreakdown:
    def _weights(self) -> dict[int, str]:
        # One defect per weight, covering pass, pending, and fail buckets.
        return {1: "high", 5: "medium", 6: "low"}

    def test_breakdown_counts_by_weight(self) -> None:
        from scripts.defects_report import _risk_weight_breakdown

        catalog = _catalog_with_statuses({1: "CAUGHT", 5: "NOT_REPRODUCED", 6: "MISSED"})
        breakdown = _risk_weight_breakdown(catalog, self._weights())
        assert breakdown["high"] == {"pass": 1, "pending": 0, "fail": 0}
        assert breakdown["medium"] == {"pass": 0, "pending": 1, "fail": 0}
        assert breakdown["low"] == {"pass": 0, "pending": 0, "fail": 1}

    def test_defects_without_weight_mapping_are_omitted(self) -> None:
        from scripts.defects_report import _risk_weight_breakdown

        catalog = _catalog_with_statuses({1: "CAUGHT"})
        breakdown = _risk_weight_breakdown(catalog, {})
        empty = {"pass": 0, "pending": 0, "fail": 0}
        assert breakdown == {"high": empty, "medium": dict(empty), "low": dict(empty)}

    def test_section_rendered_when_weights_provided(self) -> None:
        catalog = _catalog_with_statuses({1: "CAUGHT"})
        md = render_markdown(catalog, defect_risk_weights=self._weights())
        assert "## Risk Weight Breakdown" in md
        assert "| high | 1 | 0 | 0 |" in md

    def test_section_omitted_when_no_weights_provided(self) -> None:
        catalog = copy.deepcopy(DEFECT_CATALOG)
        md = render_markdown(catalog)
        assert "## Risk Weight Breakdown" not in md


# ---------------------------------------------------------------------------
# build_json
# ---------------------------------------------------------------------------


class TestBuildJson:
    def test_summary_keys_present(self) -> None:
        catalog = copy.deepcopy(DEFECT_CATALOG)
        data = build_json(catalog)
        assert isinstance(data, dict)
        assert "summary" in data
        summary = data["summary"]
        assert isinstance(summary, dict)
        for key in ("total", "caught", "verified", "not_reproduced", "covered", "missed"):
            assert key in summary, f"Key {key!r} missing from summary"

    def test_summary_total_is_eight(self) -> None:
        catalog = copy.deepcopy(DEFECT_CATALOG)
        data = build_json(catalog)
        summary = data["summary"]
        assert isinstance(summary, dict)
        assert summary["total"] == 8

    def test_defects_list_length(self) -> None:
        catalog = copy.deepcopy(DEFECT_CATALOG)
        data = build_json(catalog)
        defects = data["defects"]
        assert isinstance(defects, list)
        assert len(defects) == 8

    def test_status_counts_sum_to_total(self) -> None:
        catalog = _catalog_with_statuses({5: "CAUGHT", 6: "CAUGHT", 7: "CAUGHT", 8: "CAUGHT"})
        data = build_json(catalog)
        summary = data["summary"]
        assert isinstance(summary, dict)
        total = (
            int(summary["caught"])
            + int(summary["verified"])
            + int(summary["not_reproduced"])
            + int(summary["covered"])
            + int(summary["missed"])
        )
        assert total == 8

    def test_four_caught_reflected_in_json(self) -> None:
        catalog = _catalog_with_statuses({5: "CAUGHT", 6: "CAUGHT", 7: "CAUGHT", 8: "CAUGHT"})
        data = build_json(catalog)
        summary = data["summary"]
        assert isinstance(summary, dict)
        assert summary["caught"] == 4


# ---------------------------------------------------------------------------
# _ingest_semantic_results
# ---------------------------------------------------------------------------


class TestIngestSemanticResults:
    def test_no_semantic_file_leaves_defects_covered(self, tmp_path: Path) -> None:
        import copy
        import os

        from scripts.defects_report import DEFECT_CATALOG, _ingest_semantic_results

        catalog = copy.deepcopy(DEFECT_CATALOG)
        original = os.getcwd()
        os.chdir(tmp_path)
        try:
            _ingest_semantic_results(catalog)
        finally:
            os.chdir(original)

        for entry in catalog:
            if entry.id <= 4:
                assert entry.status == "COVERED"
                assert any("COVERED" in d for d in entry.details)

    def test_semantic_file_with_matching_key_upgrades_to_verified(self, tmp_path: Path) -> None:
        import copy
        import json
        import os

        from scripts.defects_report import DEFECT_CATALOG, _ingest_semantic_results

        sem_dir = tmp_path / "reports" / "semantic"
        sem_dir.mkdir(parents=True)
        (sem_dir / "results.json").write_text(
            json.dumps({"defect-1-hallucination": {"passed": False}}),
            encoding="utf-8",
        )

        catalog = copy.deepcopy(DEFECT_CATALOG)
        original = os.getcwd()
        os.chdir(tmp_path)
        try:
            _ingest_semantic_results(catalog)
        finally:
            os.chdir(original)

        defect_1 = next(e for e in catalog if e.id == 1)
        assert defect_1.status == "VERIFIED"

    def test_semantic_measurement_can_mark_defect_not_reproduced(self, tmp_path: Path) -> None:
        import copy
        import json
        import os

        from scripts.defects_report import DEFECT_CATALOG, _ingest_semantic_results

        sem_dir = tmp_path / "reports" / "semantic"
        sem_dir.mkdir(parents=True)
        (sem_dir / "results.json").write_text(
            json.dumps(
                {
                    "measurements": {
                        "defect-1-hallucination": {
                            "case_id": "defect-1-hallucination",
                            "defect_id": 1,
                            "metric": "faithfulness",
                            "score": 0.91,
                            "threshold": 0.7,
                            "threshold_passed": True,
                            "status": "NOT_REPRODUCED",
                        }
                    }
                }
            ),
            encoding="utf-8",
        )

        catalog = copy.deepcopy(DEFECT_CATALOG)
        original = os.getcwd()
        os.chdir(tmp_path)
        try:
            _ingest_semantic_results(catalog)
        finally:
            os.chdir(original)

        defect_1 = next(e for e in catalog if e.id == 1)
        assert defect_1.status == "NOT_REPRODUCED"
        assert any("faithfulness" in d for d in defect_1.details)

    def test_same_case_multiple_metrics_are_all_rendered(self, tmp_path: Path) -> None:
        import copy
        import json
        import os

        from scripts.defects_report import DEFECT_CATALOG, _ingest_semantic_results

        sem_dir = tmp_path / "reports" / "semantic"
        sem_dir.mkdir(parents=True)
        (sem_dir / "results.json").write_text(
            json.dumps(
                {
                    "measurements": {
                        "defect-1-hallucination::faithfulness": {
                            "case_id": "defect-1-hallucination",
                            "defect_id": 1,
                            "metric": "faithfulness",
                            "score": 0.42,
                            "threshold": 0.7,
                            "status": "VERIFIED",
                        },
                        "defect-1-hallucination::hallucination": {
                            "case_id": "defect-1-hallucination",
                            "defect_id": 1,
                            "metric": "hallucination",
                            "score": 0.21,
                            "threshold": 0.5,
                            "status": "VERIFIED",
                        },
                    }
                }
            ),
            encoding="utf-8",
        )

        catalog = copy.deepcopy(DEFECT_CATALOG)
        original = os.getcwd()
        os.chdir(tmp_path)
        try:
            _ingest_semantic_results(catalog)
        finally:
            os.chdir(original)

        defect_1 = next(e for e in catalog if e.id == 1)
        assert defect_1.status == "VERIFIED"
        assert any("faithfulness" in d for d in defect_1.details)
        assert any("hallucination" in d for d in defect_1.details)

    def test_multiple_variants_all_fixed_marks_defect_not_reproduced(self, tmp_path: Path) -> None:
        import copy
        import json
        import os

        from scripts.defects_report import DEFECT_CATALOG, _ingest_semantic_results

        sem_dir = tmp_path / "reports" / "semantic"
        sem_dir.mkdir(parents=True)
        (sem_dir / "results.json").write_text(
            json.dumps(
                {
                    "measurements": {
                        "defect-1-a": {
                            "case_id": "defect-1-a",
                            "defect_id": 1,
                            "metric": "faithfulness",
                            "score": 0.9,
                            "threshold": 0.7,
                            "status": "NOT_REPRODUCED",
                        },
                        "defect-1-b": {
                            "case_id": "defect-1-b",
                            "defect_id": 1,
                            "metric": "faithfulness",
                            "score": 0.85,
                            "threshold": 0.7,
                            "status": "NOT_REPRODUCED",
                        },
                    }
                }
            ),
            encoding="utf-8",
        )

        catalog = copy.deepcopy(DEFECT_CATALOG)
        original = os.getcwd()
        os.chdir(tmp_path)
        try:
            _ingest_semantic_results(catalog)
        finally:
            os.chdir(original)

        defect_1 = next(e for e in catalog if e.id == 1)
        assert defect_1.status == "NOT_REPRODUCED"
        assert any("defect-1-a" in d for d in defect_1.details)
        assert any("defect-1-b" in d for d in defect_1.details)

    def test_one_variant_still_verified_keeps_defect_verified_not_fixed(
        self, tmp_path: Path
    ) -> None:
        """If even one phrasing still reproduces the defect, the defect as a
        whole must not be reported not reproduced — that would hide a real regression
        behind a passing paraphrase."""
        import copy
        import json
        import os

        from scripts.defects_report import DEFECT_CATALOG, _ingest_semantic_results

        sem_dir = tmp_path / "reports" / "semantic"
        sem_dir.mkdir(parents=True)
        (sem_dir / "results.json").write_text(
            json.dumps(
                {
                    "measurements": {
                        "defect-1-a": {
                            "case_id": "defect-1-a",
                            "defect_id": 1,
                            "metric": "faithfulness",
                            "score": 0.9,
                            "threshold": 0.7,
                            "status": "NOT_REPRODUCED",
                        },
                        "defect-1-b": {
                            "case_id": "defect-1-b",
                            "defect_id": 1,
                            "metric": "faithfulness",
                            "score": 0.4,
                            "threshold": 0.7,
                            "status": "VERIFIED",
                        },
                    }
                }
            ),
            encoding="utf-8",
        )

        catalog = copy.deepcopy(DEFECT_CATALOG)
        original = os.getcwd()
        os.chdir(tmp_path)
        try:
            _ingest_semantic_results(catalog)
        finally:
            os.chdir(original)

        defect_1 = next(e for e in catalog if e.id == 1)
        assert defect_1.status == "VERIFIED"


# ---------------------------------------------------------------------------
# Regeneration consistency — the committed doc must match a fresh run
# ---------------------------------------------------------------------------


class TestRegenerationMatchesCommittedDoc:
    def test_committed_doc_is_byte_identical_to_a_fresh_run(self) -> None:
        """`make defects-report` must reproduce docs/defects-caught.md exactly.

        A hand-edit to the committed doc without a matching generator change
        would otherwise go unnoticed until someone runs the regenerate
        command and finds their improvements silently reverted.
        """
        catalog = run()
        fresh_md = render_markdown(catalog, defect_risk_weights=_load_defect_risk_weights())
        committed_md = Path("docs/defects-caught.md").read_text(encoding="utf-8")
        assert fresh_md == committed_md, (
            "docs/defects-caught.md has drifted from scripts/defects_report.py's output. "
            "Run `make defects-report` and commit the result, or update the generator "
            "to match the intended committed prose."
        )
