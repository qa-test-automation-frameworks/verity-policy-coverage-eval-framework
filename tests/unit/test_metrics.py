"""Unit tests for metric factory functions — construction only, no live calls."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from verity.judges import ProviderJudge
from verity.metrics.deepeval_metrics import (
    THRESHOLD_ANSWER_RELEVANCY,
    THRESHOLD_COMPLETENESS,
    THRESHOLD_DISAMBIGUATION,
    THRESHOLD_HALLUCINATION,
    THRESHOLD_INJECTION_COMPLIANCE,
    THRESHOLD_PII_LEAKAGE,
    THRESHOLD_REFUSAL,
    THRESHOLD_TOOL_CORRECTNESS,
    make_answer_relevancy,
    make_completeness,
    make_disambiguation,
    make_hallucination,
    make_injection_compliance,
    make_pii_leakage,
    make_refusal_geval,
    make_tool_correctness,
)
from verity.metrics.ragas_metrics import (
    THRESHOLD_CONTEXT_RECALL,
    THRESHOLD_FAITHFULNESS,
    ensure_ragas_compat,
    make_context_precision,
    make_context_recall,
    make_faithfulness,
    make_ragas_answer_relevancy,
)
from verity.metrics.rubrics import (
    COMPLETENESS_RUBRIC,
    DISAMBIGUATION_RUBRIC,
    INJECTION_COMPLIANCE_RUBRIC,
    PII_LEAKAGE_RUBRIC,
    REFUSAL_RUBRIC,
)


def _mock_judge() -> ProviderJudge:
    judge = MagicMock(spec=ProviderJudge)
    judge.model_name = "mock-model"
    judge.generate.return_value = "score: 0.9"
    return judge


# ---------------------------------------------------------------------------
# Rubrics
# ---------------------------------------------------------------------------


class TestRubrics:
    def test_completeness_rubric_non_empty(self) -> None:
        assert len(COMPLETENESS_RUBRIC) > 50

    def test_disambiguation_rubric_non_empty(self) -> None:
        assert len(DISAMBIGUATION_RUBRIC) > 50

    def test_refusal_rubric_non_empty(self) -> None:
        assert len(REFUSAL_RUBRIC) > 50

    def test_rubrics_are_strings(self) -> None:
        assert isinstance(COMPLETENESS_RUBRIC, str)
        assert isinstance(DISAMBIGUATION_RUBRIC, str)
        assert isinstance(REFUSAL_RUBRIC, str)

    def test_pii_leakage_rubric_non_empty(self) -> None:
        assert len(PII_LEAKAGE_RUBRIC) > 50

    def test_injection_compliance_rubric_non_empty(self) -> None:
        assert len(INJECTION_COMPLIANCE_RUBRIC) > 50


# ---------------------------------------------------------------------------
# Threshold constants
# ---------------------------------------------------------------------------


class TestThresholds:
    def test_thresholds_in_range(self) -> None:
        for name, value in [
            ("THRESHOLD_HALLUCINATION", THRESHOLD_HALLUCINATION),
            ("THRESHOLD_ANSWER_RELEVANCY", THRESHOLD_ANSWER_RELEVANCY),
            ("THRESHOLD_COMPLETENESS", THRESHOLD_COMPLETENESS),
            ("THRESHOLD_DISAMBIGUATION", THRESHOLD_DISAMBIGUATION),
            ("THRESHOLD_REFUSAL", THRESHOLD_REFUSAL),
            ("THRESHOLD_TOOL_CORRECTNESS", THRESHOLD_TOOL_CORRECTNESS),
            ("THRESHOLD_FAITHFULNESS", THRESHOLD_FAITHFULNESS),
            ("THRESHOLD_CONTEXT_RECALL", THRESHOLD_CONTEXT_RECALL),
            ("THRESHOLD_PII_LEAKAGE", THRESHOLD_PII_LEAKAGE),
            ("THRESHOLD_INJECTION_COMPLIANCE", THRESHOLD_INJECTION_COMPLIANCE),
        ]:
            assert 0.0 <= value <= 1.0, f"{name} = {value} out of [0, 1]"


# ---------------------------------------------------------------------------
# DeepEval metric construction
# ---------------------------------------------------------------------------


class TestDeepEvalMetricConstruction:
    def test_make_hallucination_returns_object(self) -> None:
        m = make_hallucination(_mock_judge())
        assert m is not None

    def test_make_answer_relevancy_returns_object(self) -> None:
        m = make_answer_relevancy(_mock_judge())
        assert m is not None

    def test_make_completeness_returns_object(self) -> None:
        m = make_completeness(_mock_judge())
        assert m is not None

    def test_make_disambiguation_returns_object(self) -> None:
        m = make_disambiguation(_mock_judge())
        assert m is not None

    def test_make_refusal_geval_returns_object(self) -> None:
        m = make_refusal_geval(_mock_judge())
        assert m is not None

    def test_make_tool_correctness_returns_object(self) -> None:
        import os

        if not os.environ.get("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set — ToolCorrectnessMetric requires OpenAI")
        m = make_tool_correctness(_mock_judge())
        assert m is not None

    def test_custom_threshold_applied(self) -> None:
        m = make_hallucination(_mock_judge(), threshold=0.3)
        assert m.threshold == 0.3

    def test_completeness_has_correct_name(self) -> None:
        m = make_completeness(_mock_judge())
        assert m.name == "Completeness"

    def test_disambiguation_has_correct_name(self) -> None:
        m = make_disambiguation(_mock_judge())
        assert m.name == "Disambiguation"

    def test_refusal_has_correct_name(self) -> None:
        m = make_refusal_geval(_mock_judge())
        assert m.name == "RefusalBoundary"

    def test_make_pii_leakage_returns_object(self) -> None:
        m = make_pii_leakage(_mock_judge())
        assert m is not None

    def test_pii_leakage_has_correct_name(self) -> None:
        m = make_pii_leakage(_mock_judge())
        assert m.name == "PIILeakage"

    def test_make_injection_compliance_returns_object(self) -> None:
        m = make_injection_compliance(_mock_judge())
        assert m is not None

    def test_injection_compliance_has_correct_name(self) -> None:
        m = make_injection_compliance(_mock_judge())
        assert m.name == "InjectionCompliance"


# ---------------------------------------------------------------------------
# RAGAS metric construction
# ---------------------------------------------------------------------------


class TestRagasMetricConstruction:
    def test_ragas_metric_import_smoke(self) -> None:
        from verity.metrics.ragas_metrics import _import_ragas_metric_class

        ensure_ragas_compat()
        faithfulness_cls = _import_ragas_metric_class("Faithfulness")

        assert faithfulness_cls is not None

    def test_make_faithfulness_returns_object(self) -> None:
        try:
            m = make_faithfulness(_mock_judge())
            assert m is not None
        except ImportError:
            pytest.skip("ragas not available")

    def test_make_context_precision_returns_object(self) -> None:
        try:
            m = make_context_precision(_mock_judge())
            assert m is not None
        except ImportError:
            pytest.skip("ragas not available")

    def test_make_context_recall_returns_object(self) -> None:
        try:
            m = make_context_recall(_mock_judge())
            assert m is not None
        except ImportError:
            pytest.skip("ragas not available")

    def test_make_ragas_answer_relevancy_returns_object(self) -> None:
        try:
            m = make_ragas_answer_relevancy(_mock_judge())
            assert m is not None
        except ImportError:
            pytest.skip("ragas not available")
