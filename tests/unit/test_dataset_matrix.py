"""Unit tests for the dataset coverage matrix renderer."""

from __future__ import annotations

from scripts.dataset_matrix import case_plan, render_matrix

from verity.golden import GoldenCase


def _case(**kwargs: object) -> GoldenCase:
    defaults: dict[str, object] = {"id": "c1", "query": "q"}
    defaults.update(kwargs)
    return GoldenCase.model_validate(defaults)


def test_case_plan_infers_single_plan_tag() -> None:
    assert case_plan(_case(tags=["gold", "deductible"])) == "gold"


def test_case_plan_falls_back_to_cross_plan_when_ambiguous() -> None:
    assert case_plan(_case(tags=["bronze", "gold"])) == "cross-plan"
    assert case_plan(_case(tags=["control"])) == "cross-plan"


def test_render_includes_every_section() -> None:
    cases = [_case(id="c1", risk_weight="high", defect_id=1)]
    report = render_matrix(cases)
    assert "## By plan tier" in report
    assert "## By risk weight" in report
    assert "## By behavior" in report
    assert "## By expectation category" in report
    assert "## Seeded-defect linkage" in report


def test_render_flags_missing_defects() -> None:
    cases = [_case(id="c1", defect_id=1)]
    report = render_matrix(cases)
    assert "1/8 seeded defects" in report
    assert "**Missing:**" in report
    assert "#2" in report


def test_render_reports_full_defect_coverage() -> None:
    cases = [_case(id=f"c{i}", defect_id=i) for i in range(1, 9)]
    report = render_matrix(cases)
    assert "8/8 seeded defects" in report
    assert "**Missing:**" not in report


def test_render_ends_with_regenerate_hint() -> None:
    report = render_matrix([_case()])
    assert "make dataset-matrix" in report
