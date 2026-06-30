"""Unit tests for the golden test-case schema and loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from verity.golden import ExpectedTool, GoldenCase, load_golden

_GOLDEN_DIR = Path("datasets/golden")


class TestGoldenCaseSchema:
    def test_minimal_case(self) -> None:
        case = GoldenCase(id="test-001", query="What is my deductible?")
        assert case.id == "test-001"
        assert case.behavior == "answer"
        assert case.expects_defect is False
        assert case.member_id == "MBR-001"
        assert case.tags == []

    def test_expected_tool(self) -> None:
        tool = ExpectedTool(
            name="coverage_calculator",
            required_args=["claim_amount", "plan_deductible"],
            expected_arg_values={"claim_amount": 1000.0},
        )
        assert tool.name == "coverage_calculator"
        assert "claim_amount" in tool.required_args
        assert tool.expected_arg_values["claim_amount"] == 1000.0

    def test_case_with_tool(self) -> None:
        case = GoldenCase(
            id="test-tool",
            query="How much will I pay?",
            expected_tool={"name": "coverage_calculator"},
        )
        assert case.expected_tool is not None
        assert case.expected_tool.name == "coverage_calculator"

    def test_defect_case(self) -> None:
        case = GoldenCase(
            id="defect-test",
            query="Is X covered?",
            expects_defect=True,
            defect_id=1,
            semantic_metrics=["hallucination", "faithfulness"],
        )
        assert case.expects_defect is True
        assert case.defect_id == 1
        assert "hallucination" in case.semantic_metrics

    def test_refuse_behavior(self) -> None:
        case = GoldenCase(id="refuse-test", query="Diagnose me", behavior="refuse")
        assert case.behavior == "refuse"


class TestLoadGolden:
    def test_loads_cases_from_yaml(self) -> None:
        cases = load_golden(_GOLDEN_DIR)
        assert len(cases) >= 12, f"Expected ≥12 cases, got {len(cases)}"

    def test_all_ids_unique(self) -> None:
        cases = load_golden(_GOLDEN_DIR)
        ids = [c.id for c in cases]
        assert len(ids) == len(set(ids)), "Duplicate case IDs found"

    def test_every_defect_represented(self) -> None:
        cases = load_golden(_GOLDEN_DIR)
        defect_ids = {c.defect_id for c in cases if c.expects_defect and c.defect_id is not None}
        for expected in range(1, 9):
            assert expected in defect_ids, f"No golden case for seeded defect #{expected}"

    def test_each_case_has_query(self) -> None:
        for case in load_golden(_GOLDEN_DIR):
            assert case.query.strip(), f"Case {case.id!r} has empty query"

    def test_defect_cases_have_defect_id(self) -> None:
        for case in load_golden(_GOLDEN_DIR):
            if case.expects_defect:
                assert case.defect_id is not None, f"Defect case {case.id!r} missing defect_id"

    def test_missing_directory_returns_empty(self, tmp_path: Path) -> None:
        empty = tmp_path / "no_such_dir"
        result = load_golden(empty)
        assert result == []

    def test_loads_from_custom_path(self, tmp_path: Path) -> None:
        yaml_content = """cases:
  - id: custom-01
    query: "Test question"
    behavior: answer
"""
        (tmp_path / "test_cases.yaml").write_text(yaml_content)
        cases = load_golden(tmp_path)
        assert len(cases) == 1
        assert cases[0].id == "custom-01"

    def test_control_cases_have_no_defect_id(self) -> None:
        for case in load_golden(_GOLDEN_DIR):
            if not case.expects_defect:
                assert case.defect_id is None, (
                    f"Non-defect case {case.id!r} should not have defect_id"
                )

    @pytest.mark.parametrize("defect_id", [1, 2, 3, 4, 5, 6, 7, 8])
    def test_each_defect_has_case(self, defect_id: int) -> None:
        cases = load_golden(_GOLDEN_DIR)
        found = [c for c in cases if c.defect_id == defect_id]
        assert found, f"No case found for defect #{defect_id}"
