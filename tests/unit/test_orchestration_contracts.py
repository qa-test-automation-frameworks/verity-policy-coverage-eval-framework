"""Contract tests for orchestration-level timeout, retry, idempotency, and failure paths.

These tests pin down guarantees that span LLMProvider and CoverageAgent together:
- The configured timeout/retry budget is actually threaded into every litellm call.
- Identical requests hash to identical cassette keys (safe to retry/replay without
  double-billing or divergent behavior).
- Failure paths at every orchestration boundary degrade to a safe structured
  response rather than raising past the agent boundary.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from sut.agent import CoverageAgent
from sut.retriever import FixtureRetriever
from verity.cassettes import ReplayFunction, ReplayToolCall
from verity.config import Provider, Settings
from verity.cost import RunAccumulator
from verity.providers import CompletionResult, LLMProvider

_PATCH = "verity.providers.litellm.completion"


def _mock_response(content: str = "Test response") -> MagicMock:
    mock_usage = MagicMock()
    mock_usage.prompt_tokens = 10
    mock_usage.completion_tokens = 5
    mock_usage.total_tokens = 15

    mock_message = MagicMock()
    mock_message.content = content
    mock_message.tool_calls = []

    mock_choice = MagicMock()
    mock_choice.message = mock_message

    mock_resp = MagicMock()
    mock_resp.usage = mock_usage
    mock_resp.choices = [mock_choice]
    return mock_resp


@pytest.fixture()
def settings_no_key() -> Settings:
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return Settings(provider=Provider.zai, model="glm-4.5", timeout=45, retries=5)


class TestTimeoutAndRetryBudget:
    def test_configured_timeout_passed_to_litellm(self, settings_no_key: Settings) -> None:
        provider = LLMProvider(settings_no_key, RunAccumulator())

        with patch(_PATCH, return_value=_mock_response()) as mock_call:
            provider.complete([{"role": "user", "content": "hi"}])

        assert mock_call.call_args.kwargs["timeout"] == 45

    def test_configured_retries_passed_to_litellm(self, settings_no_key: Settings) -> None:
        provider = LLMProvider(settings_no_key, RunAccumulator())

        with patch(_PATCH, return_value=_mock_response()) as mock_call:
            provider.complete([{"role": "user", "content": "hi"}])

        assert mock_call.call_args.kwargs["num_retries"] == 5

    def test_default_timeout_and_retries_are_nonzero(self) -> None:
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            settings = Settings(provider=Provider.zai, model="glm-4.5")

        assert settings.timeout > 0
        assert settings.retries >= 1


class TestRequestKeyIdempotency:
    """Retrying or replaying an identical request must hash to an identical key."""

    def test_same_request_same_key_across_repeated_calls(self, settings_no_key: Settings) -> None:
        from verity.cassettes import request_key

        messages = [{"role": "user", "content": "What does my plan cover?"}]
        keys = {request_key("glm-4.5", messages, None, 0.0, 512) for _ in range(5)}
        assert len(keys) == 1

    def test_agent_replay_is_idempotent_across_repeated_answers(self) -> None:
        """Calling answer() twice with an identical mocked first-turn result yields
        the same citations/answer/tool invocations both times — no hidden state
        leaks between calls that would make retries unsafe."""
        settings = Settings(cassette_mode="off")
        retriever = FixtureRetriever("ctrl-gold-deductible")

        mock_provider = MagicMock()
        mock_provider.accumulator = RunAccumulator()
        mock_provider.complete.return_value = CompletionResult(
            content="Your plan covers this service.", tool_calls=[]
        )

        agent = CoverageAgent(settings=settings, retriever=retriever, provider=mock_provider)

        first = agent.answer("What does my Gold plan cover for a lab?", member_id="MBR-003")
        second = agent.answer("What does my Gold plan cover for a lab?", member_id="MBR-003")

        assert first.answer == second.answer
        assert first.citations == second.citations
        assert first.refused == second.refused == False  # noqa: E712


class TestFailurePathsDegradeSafely:
    """Every orchestration boundary that can raise must degrade to a safe response."""

    def test_unknown_member_id_raises_before_provider_call(self) -> None:
        settings = Settings(cassette_mode="off")
        retriever = FixtureRetriever("ctrl-gold-deductible")
        mock_provider = MagicMock()
        mock_provider.accumulator = RunAccumulator()

        agent = CoverageAgent(settings=settings, retriever=retriever, provider=mock_provider)

        with pytest.raises(KeyError):
            agent.answer("What does my plan cover?", member_id="MBR-does-not-exist")

        mock_provider.complete.assert_not_called()

    def test_retriever_failure_is_not_swallowed_silently(self) -> None:
        """A retriever exception is a corpus/index problem, not an LLM failure —
        it should propagate rather than being mislabeled as a safe LLM/tool failure."""
        settings = Settings(cassette_mode="off")
        mock_provider = MagicMock()
        mock_provider.accumulator = RunAccumulator()

        mock_retriever = MagicMock()
        mock_retriever.retrieve.side_effect = RuntimeError("index unavailable")

        agent = CoverageAgent(settings=settings, retriever=mock_retriever, provider=mock_provider)

        with pytest.raises(RuntimeError, match="index unavailable"):
            agent.answer("What does my plan cover?", member_id="MBR-003")

    def test_tool_call_then_provider_failure_preserves_prior_tool_invocations(self) -> None:
        """When the second turn fails after a tool ran successfully, the safe
        response still carries the tool invocation that already happened —
        callers must not lose evidence of work already performed."""
        settings = Settings(cassette_mode="off")
        retriever = FixtureRetriever("ctrl-gold-deductible")

        tc = ReplayToolCall(
            id="call_001",
            function=ReplayFunction(
                name="coverage_calculator",
                arguments=(
                    '{"claim_amount": 500.0, "plan_deductible": 750.0, "accrued_deductible": 200.0,'
                    ' "plan_oop_max": 4000.0, "accrued_oop": 0.0, "coinsurance_member": 0.10}'
                ),
            ),
        )
        call_count = [0]

        def _complete(**kwargs: object) -> CompletionResult:
            call_count[0] += 1
            if call_count[0] == 1:
                return CompletionResult(content="", tool_calls=[tc])
            raise TimeoutError("second turn timed out")

        mock_provider = MagicMock()
        mock_provider.accumulator = RunAccumulator()
        mock_provider.complete.side_effect = _complete

        agent = CoverageAgent(settings=settings, retriever=retriever, provider=mock_provider)
        response = agent.answer("What's my lab cost?", member_id="MBR-003")

        assert response.refused
        assert len(response.tool_invocations) == 1
        assert response.tool_invocations[0].tool_name == "coverage_calculator"


class TestPerResponseUsageTracking:
    """A shared accumulator/agent serving multiple requests must report each
    response's own token/cost usage, not the accumulator's running lifetime total."""

    def test_second_response_reports_only_its_own_usage(self) -> None:
        settings = Settings(cassette_mode="off")
        retriever = FixtureRetriever("ctrl-gold-deductible")
        accumulator = RunAccumulator()

        from verity.cost import Usage

        mock_provider = MagicMock()
        mock_provider.accumulator = accumulator

        def _complete(**kwargs: object) -> CompletionResult:
            accumulator.log_call("glm-4.5", Usage(100, 50, 150), latency_ms=10.0)
            return CompletionResult(content="Your plan covers this.", tool_calls=[])

        mock_provider.complete.side_effect = _complete

        agent = CoverageAgent(settings=settings, retriever=retriever, provider=mock_provider)

        first = agent.answer("What does my Gold plan cover for a lab?", member_id="MBR-003")
        second = agent.answer("What does my Gold plan cover for a lab?", member_id="MBR-003")

        # Each response used exactly one LLM call (100+50=150 tokens) — not the
        # lifetime cumulative total across both calls (300 tokens).
        assert first.total_tokens == 150
        assert second.total_tokens == 150
        assert accumulator.total_tokens.total_tokens == 300

    def test_safe_failure_response_reports_only_its_own_usage(self) -> None:
        settings = Settings(cassette_mode="off")
        retriever = FixtureRetriever("ctrl-gold-deductible")
        accumulator = RunAccumulator()

        from verity.cost import Usage

        mock_provider = MagicMock()
        mock_provider.accumulator = accumulator
        # Pre-populate the accumulator as if prior requests already ran through it.
        accumulator.log_call("glm-4.5", Usage(1000, 500, 1500), latency_ms=10.0)

        mock_provider.complete.side_effect = ConnectionError("provider down")

        agent = CoverageAgent(settings=settings, retriever=retriever, provider=mock_provider)
        response = agent.answer("What does my Gold plan cover for a lab?", member_id="MBR-003")

        assert response.refused
        assert response.total_tokens == 0  # this call made no successful LLM calls
