"""Unit tests for token/cost accounting."""

from __future__ import annotations

import pytest

from verity.cost import Cost, RunAccumulator, Usage, estimate_cost


class TestEstimateCost:
    def test_priced_model_computes_nonzero_cost(self) -> None:
        usage = Usage(prompt_tokens=1_000_000, completion_tokens=1_000_000, total_tokens=2_000_000)
        cost = estimate_cost(usage, "glm-4.5")
        assert cost.prompt_usd == pytest.approx(0.60)
        assert cost.completion_usd == pytest.approx(2.20)
        assert cost.total_usd == pytest.approx(2.80)
        assert cost.priced is True

    def test_unknown_model_zero_cost(self) -> None:
        usage = Usage(prompt_tokens=1000, completion_tokens=500, total_tokens=1500)
        cost = estimate_cost(usage, "unknown-model-xyz")
        assert cost.total_usd == 0.0

    def test_unknown_model_flagged_as_unpriced(self) -> None:
        usage = Usage(prompt_tokens=1000, completion_tokens=500, total_tokens=1500)
        cost = estimate_cost(usage, "unknown-model-xyz")
        assert cost.priced is False

    def test_unknown_model_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        import logging

        usage = Usage(prompt_tokens=1000, completion_tokens=500, total_tokens=1500)
        with caplog.at_level(logging.WARNING, logger="verity.cost"):
            estimate_cost(usage, "unknown-model-xyz")
        assert "unknown-model-xyz" in caplog.text
        assert "No price entry" in caplog.text

    def test_str_flags_unpriced_model_distinctly(self) -> None:
        usage = Usage(prompt_tokens=1000, completion_tokens=500, total_tokens=1500)
        cost = estimate_cost(usage, "unknown-model-xyz")
        assert "UNPRICED MODEL" in str(cost)

    def test_str_does_not_flag_priced_model(self) -> None:
        usage = Usage(prompt_tokens=1000, completion_tokens=500, total_tokens=1500)
        cost = estimate_cost(usage, "glm-4.5")
        assert "UNPRICED" not in str(cost)

    def test_litellm_prefixed_model_strips_provider_for_pricing(self) -> None:
        usage = Usage(prompt_tokens=1_000_000, completion_tokens=0, total_tokens=1_000_000)
        cost = estimate_cost(usage, "openai/glm-4.5")
        assert cost.total_usd == 0.60

    def test_zero_tokens_zero_cost(self) -> None:
        usage = Usage(prompt_tokens=0, completion_tokens=0, total_tokens=0)
        cost = estimate_cost(usage, "glm-4.5")
        assert cost.total_usd == 0.0


class TestRunAccumulator:
    def test_empty_accumulator(self) -> None:
        acc = RunAccumulator()
        assert acc.total_cost.total_usd == 0.0
        assert acc.total_tokens.total_tokens == 0
        assert len(acc.records) == 0

    def test_single_log_call(self) -> None:
        acc = RunAccumulator()
        record = acc.log_call("glm-4.5", Usage(1000, 200, 1200), latency_ms=450.0, label="test")
        assert record.model == "glm-4.5"
        assert record.usage.total_tokens == 1200
        assert record.latency_ms == 450.0
        assert record.label == "test"

    def test_accumulation_across_calls(self) -> None:
        acc = RunAccumulator()
        acc.log_call("glm-4.5", Usage(1000, 200, 1200), latency_ms=100.0)
        acc.log_call("glm-4.5", Usage(500, 100, 600), latency_ms=80.0)
        totals = acc.total_tokens
        assert totals.prompt_tokens == 1500
        assert totals.completion_tokens == 300
        assert totals.total_tokens == 1800

    def test_summary_string(self) -> None:
        acc = RunAccumulator()
        acc.log_call("glm-4.5", Usage(100, 50, 150), latency_ms=200.0)
        summary = acc.summary()
        assert "Calls: 1" in summary
        assert "Tokens:" in summary
        assert "Cost:" in summary

    def test_cost_str(self) -> None:
        c = Cost(prompt_usd=0.001, completion_usd=0.002, total_usd=0.003)
        assert "$0.003000" in str(c)

    def test_unpriced_models_empty_when_all_priced(self) -> None:
        acc = RunAccumulator()
        acc.log_call("glm-4.5", Usage(100, 50, 150), latency_ms=200.0)
        assert acc.unpriced_models == []
        assert acc.total_cost.priced is True

    def test_unpriced_models_lists_distinct_unpriced_model(self) -> None:
        acc = RunAccumulator()
        acc.log_call("glm-4.5", Usage(100, 50, 150), latency_ms=200.0)
        acc.log_call("mystery-model", Usage(100, 50, 150), latency_ms=200.0)
        acc.log_call("mystery-model", Usage(100, 50, 150), latency_ms=200.0)
        assert acc.unpriced_models == ["mystery-model"]
        assert acc.total_cost.priced is False

    def test_summary_warns_when_unpriced_model_present(self) -> None:
        acc = RunAccumulator()
        acc.log_call("mystery-model", Usage(100, 50, 150), latency_ms=200.0)
        summary = acc.summary()
        assert "WARNING" in summary
        assert "mystery-model" in summary

    def test_summary_no_warning_when_all_priced(self) -> None:
        acc = RunAccumulator()
        acc.log_call("glm-4.5", Usage(100, 50, 150), latency_ms=200.0)
        summary = acc.summary()
        assert "WARNING" not in summary

    def test_usage_and_cost_since_zero_returns_full_totals(self) -> None:
        acc = RunAccumulator()
        acc.log_call("glm-4.5", Usage(100, 50, 150), latency_ms=10.0)
        acc.log_call("glm-4.5", Usage(200, 100, 300), latency_ms=10.0)
        usage, cost = acc.usage_and_cost_since(0)
        assert usage.total_tokens == 450
        assert cost.total_usd == pytest.approx(acc.total_cost.total_usd)

    def test_usage_and_cost_since_excludes_prior_calls(self) -> None:
        acc = RunAccumulator()
        acc.log_call("glm-4.5", Usage(1000, 500, 1500), latency_ms=10.0)
        start_index = len(acc.records)
        acc.log_call("glm-4.5", Usage(100, 50, 150), latency_ms=10.0)
        usage, cost = acc.usage_and_cost_since(start_index)
        assert usage.total_tokens == 150
        assert usage.prompt_tokens == 100
        assert cost.total_usd < acc.total_cost.total_usd

    def test_usage_and_cost_since_end_returns_zero(self) -> None:
        acc = RunAccumulator()
        acc.log_call("glm-4.5", Usage(100, 50, 150), latency_ms=10.0)
        usage, cost = acc.usage_and_cost_since(len(acc.records))
        assert usage.total_tokens == 0
        assert cost.total_usd == 0.0
