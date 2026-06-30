"""Unit tests for the judge adapters (mocked provider — no live calls)."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from verity.cost import RunAccumulator
from verity.judges import DeepEvalJudge, ProviderJudge, RagasJudge
from verity.providers import CompletionResult

# ---------------------------------------------------------------------------
# Shared stub
# ---------------------------------------------------------------------------


def _make_mock_provider(response_text: str = "judge response") -> MagicMock:
    mock = MagicMock()
    mock.complete.return_value = CompletionResult(content=response_text)
    mock.accumulator = RunAccumulator()
    return mock


def _make_provider_judge(response_text: str = "judge says: correct") -> ProviderJudge:
    judge = ProviderJudge.__new__(ProviderJudge)
    judge._acc = RunAccumulator()
    judge._provider = _make_mock_provider(response_text)
    return judge


# ---------------------------------------------------------------------------
# ProviderJudge
# ---------------------------------------------------------------------------


class TestProviderJudge:
    def test_generate_returns_string(self) -> None:
        judge = _make_provider_judge("the answer is 42")
        result = judge.generate("What is 6 * 7?")
        assert result == "the answer is 42"

    def test_generate_calls_provider_complete(self) -> None:
        judge = _make_provider_judge()
        judge.generate("some prompt")
        judge._provider.complete.assert_called_once()

    def test_a_generate_returns_same_as_generate(self) -> None:
        judge = _make_provider_judge("async response")
        result = asyncio.get_event_loop().run_until_complete(judge.a_generate("prompt"))
        assert result == "async response"

    def test_accumulator_property(self) -> None:
        judge = _make_provider_judge()
        assert isinstance(judge.accumulator, RunAccumulator)

    def test_generate_with_empty_prompt(self) -> None:
        judge = _make_provider_judge("empty response")
        result = judge.generate("")
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# DeepEvalJudge
# ---------------------------------------------------------------------------


class TestDeepEvalJudge:
    def test_adapter_is_not_none(self) -> None:
        judge = _make_provider_judge()
        dj = DeepEvalJudge(judge)
        assert dj.adapter is not None

    def test_get_model_name(self) -> None:
        judge = _make_provider_judge()
        # model_name needs _settings; mock it
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            from verity.config import Settings

            judge._settings = Settings()  # type: ignore[attr-defined]
        dj = DeepEvalJudge(judge)
        name = dj.adapter.get_model_name()
        assert isinstance(name, str)

    def test_generate_via_adapter(self) -> None:
        judge = _make_provider_judge("faithfulness score: 0.9")
        dj = DeepEvalJudge(judge)
        result = dj.adapter.generate("evaluate this response")
        assert result == "faithfulness score: 0.9"

    def test_a_generate_via_adapter(self) -> None:
        judge = _make_provider_judge("async judge response")
        dj = DeepEvalJudge(judge)
        result = asyncio.get_event_loop().run_until_complete(dj.adapter.a_generate("async prompt"))
        assert result == "async judge response"

    def test_load_model_returns_self(self) -> None:
        judge = _make_provider_judge()
        dj = DeepEvalJudge(judge)
        loaded = dj.adapter.load_model()
        assert loaded is dj.adapter

    def test_import_error_when_deepeval_missing(self) -> None:
        with patch.dict(
            "sys.modules",
            {"deepeval": None, "deepeval.models": None, "deepeval.models.base_model": None},
        ):
            judge = _make_provider_judge()
            with pytest.raises(ImportError, match="deepeval is required"):
                DeepEvalJudge._build_adapter(judge)


# ---------------------------------------------------------------------------
# RagasJudge
# ---------------------------------------------------------------------------


class TestRagasJudge:
    def test_adapter_is_not_none(self) -> None:
        judge = _make_provider_judge()
        rj = RagasJudge(judge)
        assert rj.adapter is not None

    def test_invoke_returns_ai_message(self) -> None:
        judge = _make_provider_judge("ragas response text")
        rj = RagasJudge(judge)
        result = rj.adapter.invoke("faithfulness prompt")
        assert hasattr(result, "content")
        assert result.content == "ragas response text"

    def test_generate_returns_chat_result(self) -> None:
        judge = _make_provider_judge("chat result text")
        rj = RagasJudge(judge)
        result = rj.adapter.generate(["some ragas prompt"])
        assert hasattr(result, "generations")
        assert len(result.generations) >= 1

    def test_ainvoke_returns_ai_message(self) -> None:
        judge = _make_provider_judge("async ragas")
        rj = RagasJudge(judge)
        result = asyncio.get_event_loop().run_until_complete(rj.adapter.ainvoke("async prompt"))
        assert hasattr(result, "content")
        assert result.content == "async ragas"

    def test_adapter_cached_on_second_access(self) -> None:
        judge = _make_provider_judge()
        rj = RagasJudge(judge)
        a1 = rj.adapter
        a2 = rj.adapter
        assert a1 is a2

    def test_import_error_when_langchain_missing(self) -> None:
        with patch.dict(
            "sys.modules",
            {
                "langchain_core": None,
                "langchain_core.messages": None,
                "langchain_core.outputs": None,
            },
        ):
            judge = _make_provider_judge()
            with pytest.raises(ImportError, match="langchain-core is required"):
                RagasJudge._build_adapter(judge)
