"""Unit tests for model comparison report rendering."""

from __future__ import annotations

from scripts.model_comparison import CaseComparison, ModelResult, render_report


def _result(
    case_id: str, *, refused: bool = False, citations: int = 1, chars: int = 100, error: str = ""
) -> ModelResult:
    return ModelResult(
        case_id=case_id,
        provider="zai",
        model="glm-4.5",
        answered=not error,
        refused=refused,
        citation_count=citations,
        answer_chars=chars,
        error=error,
    )


def test_render_report_includes_deltas() -> None:
    rows = [
        CaseComparison(
            case_id="case-1",
            query="q",
            behavior="answer",
            left=_result("case-1", refused=False, citations=1, chars=100),
            right=_result("case-1", refused=True, citations=3, chars=130),
            refusal_delta=True,
            citation_delta=2,
            length_delta=30,
        )
    ]
    report = render_report(rows, "left/model", "right/model")
    assert "case-1" in report
    assert "+2" in report
    assert "+30" in report
    assert "Refusal behavior changed: 1" in report


def test_render_report_counts_errors() -> None:
    rows = [
        CaseComparison(
            case_id="case-err",
            query="q",
            behavior="answer",
            left=_result("case-err", error="left failed"),
            right=_result("case-err"),
            refusal_delta=False,
            citation_delta=1,
            length_delta=100,
        )
    ]
    report = render_report(rows, "left/model", "right/model")
    assert "left failed" in report
    assert "Cases with runtime errors: 1" in report
