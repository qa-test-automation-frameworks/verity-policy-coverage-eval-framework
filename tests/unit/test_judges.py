"""Unit tests for the judge adapters (mocked provider — no live calls)."""

from __future__ import annotations

import asyncio
import json
import warnings
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
    from verity.config import Settings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        judge._judge_settings = Settings(_env_file=None)
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
        judge._provider.complete.assert_called_once_with(
            messages=[{"role": "user", "content": "some prompt"}],
            label="judge",
            max_tokens=2048,
            response_format={"type": "json_object"},
        )

    def test_generate_retries_once_after_output_token_limit(self) -> None:
        from verity.config import Settings

        judge = _make_provider_judge()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            judge._judge_settings = Settings(_env_file=None, max_tokens=4096)
        truncated = CompletionResult(content='{"partial":')
        truncated.raw_response = MagicMock(
            choices=[MagicMock(finish_reason="length", message=MagicMock())]
        )
        complete = CompletionResult(content='{"score": 1}')
        complete.raw_response = MagicMock(
            choices=[MagicMock(finish_reason="stop", message=MagicMock())]
        )
        judge._provider.complete.side_effect = [truncated, complete]

        assert judge.generate("return JSON") == '{"score": 1}'
        assert [call.kwargs["max_tokens"] for call in judge._provider.complete.call_args_list] == [
            4096,
            8192,
        ]

    def test_generate_retries_once_after_invalid_provider_json(self) -> None:
        judge = _make_provider_judge()
        invalid = CompletionResult(content="```json {not-json}")
        invalid.raw_response = MagicMock(
            choices=[MagicMock(finish_reason="stop", message=MagicMock())]
        )
        corrected = CompletionResult(content='{"score": 0.8}')
        corrected.raw_response = MagicMock(
            choices=[MagicMock(finish_reason="stop", message=MagicMock())]
        )
        judge._provider.complete.side_effect = [invalid, corrected]

        assert judge.generate("return a JSON score") == '{"score": 0.8}'
        assert judge._provider.complete.call_count == 2
        retry_messages = judge._provider.complete.call_args_list[1].kwargs["messages"]
        assert retry_messages[-1]["role"] == "user"
        assert "valid JSON object only" in retry_messages[-1]["content"]

    def test_valid_json_with_missing_fields_is_not_rewritten(self) -> None:
        """Schema errors remain visible to RAGAS instead of inventing verdicts."""
        judge = _make_provider_judge('{"partial": true}')
        judge._provider.complete.return_value.raw_response = MagicMock(
            choices=[MagicMock(finish_reason="stop", message=MagicMock())]
        )

        assert judge.generate("return schema output") == '{"partial": true}'
        judge._provider.complete.assert_called_once()

    def test_verbose_judge_output_is_written_with_current_test_id(
        self, tmp_path, monkeypatch
    ) -> None:
        from verity.cost import reset_current_test_id, set_current_test_id

        path = tmp_path / "case-evidence.jsonl"
        monkeypatch.setenv("VERITY_SEMANTIC_VERBOSITY", "verbose")
        monkeypatch.setenv("VERITY_SEMANTIC_CASE_EVIDENCE_PATH", str(path))
        judge = _make_provider_judge('{"score": 1}')
        token = set_current_test_id("tests/semantic/test_eval.py::test_case")
        try:
            judge.generate("score this")
        finally:
            reset_current_test_id(token)

        event = json.loads(path.read_text(encoding="utf-8"))
        assert event["record_type"] == "judge_response"
        assert event["test_id"] == "tests/semantic/test_eval.py::test_case"
        assert event["answer"] == '{"score": 1}'

    def test_judge_config_defaults_to_longer_structured_output_budget(self) -> None:
        from verity.config import JudgeConfig

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            config = JudgeConfig(_env_file=None)

        assert config.max_tokens == 4096

    def test_nvidia_judge_disables_reasoning_for_json_output(self) -> None:
        from verity.config import Provider, Settings

        judge = _make_provider_judge()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            judge._judge_settings = Settings(_env_file=None, provider=Provider.nvidia)

        judge.generate("some prompt")

        assert judge._provider.complete.call_args.kwargs["response_format"] == {
            "type": "json_object"
        }
        assert judge._provider.complete.call_args.kwargs["extra_body"] == {
            "chat_template_kwargs": {"enable_thinking": False}
        }

    def test_empty_judge_text_has_actionable_diagnostic(self) -> None:
        judge = _make_provider_judge("")
        judge._provider.complete.return_value.raw_response = MagicMock(
            choices=[
                MagicMock(
                    finish_reason="length",
                    message=MagicMock(reasoning_content="private reasoning"),
                )
            ]
        )
        from verity.config import Settings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            judge._judge_settings = Settings(_env_file=None)

        with pytest.raises(ValueError, match="finish_reason=length") as error:
            judge.generate("some prompt")

        assert "reasoning_content_present=True" in str(error.value)
        assert "private reasoning" not in str(error.value)

    def test_a_generate_returns_same_as_generate(self) -> None:
        judge = _make_provider_judge("async response")
        result = asyncio.run(judge.a_generate("prompt"))
        assert result == "async response"

    def test_accumulator_property(self) -> None:
        judge = _make_provider_judge()
        assert isinstance(judge.accumulator, RunAccumulator)

    def test_generate_with_empty_prompt(self) -> None:
        judge = _make_provider_judge("empty response")
        result = judge.generate("")
        assert isinstance(result, str)

    def test_judge_settings_inherit_fallback_key(self) -> None:
        """The judge makes its own Settings copy; every credential field on the
        outer Settings — including the fallback key — must carry over, or the
        judge silently loses fallback coverage while the SUT keeps it."""
        from verity.config import Provider, Settings

        settings = Settings(
            _env_file=None,
            provider=Provider.openrouter,
            openrouter_api_key="primary-key",
            openrouter_api_key_2="fallback-key",
        )
        judge = ProviderJudge(settings)
        assert judge._judge_settings.resolved_fallback_api_key() == "fallback-key"


# ---------------------------------------------------------------------------
# DeepEvalJudge
# ---------------------------------------------------------------------------


class TestDeepEvalJudge:
    pytestmark = pytest.mark.semantic

    def test_adapter_is_not_none(self) -> None:
        judge = _make_provider_judge()
        dj = DeepEvalJudge(judge)
        assert dj.adapter is not None

    def test_get_model_name(self) -> None:
        judge = _make_provider_judge()
        # model_name needs _judge_settings; mock it
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            from verity.config import Settings

            judge._judge_settings = Settings()  # type: ignore[attr-defined]
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
        result = asyncio.run(dj.adapter.a_generate("async prompt"))
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
    pytestmark = pytest.mark.semantic

    def test_adapter_is_not_none(self) -> None:
        judge = _make_provider_judge()
        rj = RagasJudge(judge)
        assert rj.adapter is not None

    def test_generate_returns_llm_result(self) -> None:
        """Matches ragas.llms.base.BaseRagasLLM.generate: async, takes a
        PromptValue (or plain string), returns an LLMResult with `n` generations."""
        judge = _make_provider_judge("ragas response text")
        rj = RagasJudge(judge)
        result = asyncio.run(rj.adapter.generate("faithfulness prompt"))
        assert hasattr(result, "generations")
        assert len(result.generations) == 1
        assert result.generations[0][0].text == "ragas response text"

    def test_ragas_generation_leaves_schema_control_to_ragas(self) -> None:
        judge = _make_provider_judge('{"text": "ragas response text"}')
        rj = RagasJudge(judge)

        asyncio.run(rj.adapter.generate("schema-specific RAGAS prompt"))

        kwargs = judge._provider.complete.call_args.kwargs
        assert "response_format" not in kwargs
        assert "extra_body" not in kwargs

    def test_generate_respects_n(self) -> None:
        judge = _make_provider_judge("chat result text")
        rj = RagasJudge(judge)
        result = asyncio.run(rj.adapter.generate("some ragas prompt", n=3))
        assert len(result.generations[0]) == 3
        assert all(g.text == "chat result text" for g in result.generations[0])

    def test_generate_accepts_prompt_value_with_to_string(self) -> None:
        judge = _make_provider_judge("async ragas")
        rj = RagasJudge(judge)
        prompt_value = MagicMock()
        prompt_value.to_string.return_value = "async prompt"
        result = asyncio.run(rj.adapter.generate(prompt_value))
        assert result.generations[0][0].text == "async ragas"

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
