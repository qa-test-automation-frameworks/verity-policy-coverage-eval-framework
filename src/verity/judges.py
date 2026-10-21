"""Swappable LLM-as-judge adapters.

ProviderJudge wraps the existing LLMProvider so any configured provider/key/model
is used for evaluation — no hard-coded judge vendor.

DeepEvalJudge adapts ProviderJudge to the DeepEvalBaseLLM interface required
by DeepEval metrics.

RagasJudge provides a generate/agenerate callable compatible with RAGAS's llm=
parameter, backed by the same ProviderJudge.
"""

from __future__ import annotations

import asyncio
import contextvars
import json
import logging
import os
import warnings
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from verity.config import Provider, Settings
from verity.cost import RunAccumulator, get_current_test_id
from verity.providers import CompletionResult, LLMProvider
from verity.semantic_reporting import append_case_evidence_event

logger = logging.getLogger(__name__)

_JUDGE_MAX_TOKEN_RETRY_LIMIT = 8192
_JUDGE_MAX_ATTEMPTS = 3


# ---------------------------------------------------------------------------
# Provider-backed judge
# ---------------------------------------------------------------------------


class ProviderJudge:
    """LLM judge backed by the configured provider (same routing as the SUT).

    Parameters
    ----------
    settings:
        Root settings. The judge uses settings.judge for model / temp / max_tokens;
        provider routing uses the same fields as the SUT so everything is plug-and-play.
    accumulator:
        Optional shared RunAccumulator for cross-run cost tracking.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        accumulator: RunAccumulator | None = None,
    ) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self._settings = settings or Settings()

        self._judge_cfg = self._settings.judge
        self._acc = accumulator or RunAccumulator()

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self._judge_settings = Settings(
                provider=self._judge_cfg.provider or self._settings.provider,
                model=self._judge_cfg.model,
                temperature=self._judge_cfg.temperature,
                max_tokens=self._judge_cfg.max_tokens,
                zai_api_key=self._settings.zai_api_key,
                openrouter_api_key=self._settings.openrouter_api_key,
                openrouter_api_key_2=self._settings.openrouter_api_key_2,
                together_api_key=self._settings.together_api_key,
                nvidia_api_key=self._settings.nvidia_api_key,
                google_api_key=self._settings.google_api_key,
                zai_api_base=self._settings.zai_api_base,
                openrouter_api_base=self._settings.openrouter_api_base,
                together_api_base=self._settings.together_api_base,
                nvidia_api_base=self._settings.nvidia_api_base,
                google_api_base=self._settings.google_api_base,
                cassette_mode=self._settings.cassette_mode,
                cassette_dir=self._settings.cassette_dir,
            )
        self._provider = LLMProvider(self._judge_settings, self._acc)

    @property
    def model_name(self) -> str:
        litellm_model, _, _ = self._judge_settings.resolved_provider()
        return litellm_model

    @property
    def accumulator(self) -> RunAccumulator:
        return self._acc

    def generate(self, prompt: str, structured_output: bool = True) -> str:
        """Synchronous generation — used by DeepEval and RAGAS metrics."""
        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
        request_options: dict[str, Any] = {
            "label": "judge",
            "max_tokens": self._judge_settings.max_tokens,
        }
        if structured_output:
            # DeepEval's scoring prompts consume JSON. RAGAS supplies a
            # different Pydantic schema for each prompt, so a generic
            # json_object mode can interfere with its schema-repair prompt.
            request_options["response_format"] = {"type": "json_object"}
        if structured_output and self._judge_settings.provider == Provider.nvidia:
            # Nemotron can spend its token budget on reasoning before emitting
            # JSON; NVIDIA recommends disabling thinking for structured output.
            request_options["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}
        result: CompletionResult | None = None
        finish_reason: str | None = None
        parse_retry_used = False
        token_retry_used = False
        for attempt in range(1, _JUDGE_MAX_ATTEMPTS + 1):
            request_options["messages"] = messages
            result = self._provider.complete(**request_options)
            finish_reason = _finish_reason(result.raw_response)
            self._record_verbose_output(
                result,
                finish_reason,
                attempt=attempt,
                max_tokens=int(request_options["max_tokens"]),
            )

            if finish_reason in {"length", "max_tokens"}:
                retry_budget = min(
                    max(
                        int(request_options["max_tokens"]) * 2,
                        int(request_options["max_tokens"]) + 1,
                    ),
                    _JUDGE_MAX_TOKEN_RETRY_LIMIT,
                )
                if (
                    not token_retry_used
                    and retry_budget > int(request_options["max_tokens"])
                    and attempt < _JUDGE_MAX_ATTEMPTS
                ):
                    logger.warning(
                        "Judge output hit its token limit; retrying once with max_tokens=%d",
                        retry_budget,
                    )
                    request_options["max_tokens"] = retry_budget
                    token_retry_used = True
                    continue
                logger.warning(
                    "Judge output remains truncated at max_tokens=%d; the metric parser "
                    "may reject this result",
                    request_options["max_tokens"],
                )

            # Providers return raw metadata; cassette fixtures and unit stubs
            # without it keep their recorded response unchanged. This repair
            # handles invalid JSON syntax, not missing schema fields: those
            # remain explicit metric failures and are captured for diagnosis.
            if (
                result.raw_response is not None
                and result.content.strip()
                and not _is_json_object(result.content)
                and not parse_retry_used
                and attempt < _JUDGE_MAX_ATTEMPTS
            ):
                logger.warning(
                    "Judge returned invalid JSON; retrying once with a correction instruction"
                )
                messages.extend(
                    [
                        {"role": "assistant", "content": result.content},
                        {
                            "role": "user",
                            "content": (
                                "Your previous response was not a valid JSON object. "
                                "Return a valid JSON object only, following the original "
                                "request's schema. Do not use Markdown fences or extra text."
                            ),
                        },
                    ]
                )
                parse_retry_used = True
                continue
            break

        assert result is not None  # The bounded loop always makes one provider call.
        if not result.content.strip():
            finish_reason = finish_reason or "unknown"
            reasoning_content_present = False
            raw_response = result.raw_response
            try:
                choice = raw_response.choices[0]
                finish_reason = getattr(choice, "finish_reason", None) or "unknown"
                reasoning_content_present = bool(getattr(choice.message, "reasoning_content", None))
            except (AttributeError, IndexError, TypeError):
                pass
            raise ValueError(
                f"Judge {self.model_name} returned empty text "
                f"(finish_reason={finish_reason}, "
                f"reasoning_content_present={reasoning_content_present}). "
                "Check provider output limits and structured-output support."
            )
        return result.content

    def _record_verbose_output(
        self,
        result: CompletionResult,
        finish_reason: str | None,
        *,
        attempt: int,
        max_tokens: int,
    ) -> None:
        """Keep judge text only in the opt-in short-retention semantic artifact."""
        if os.environ.get("VERITY_SEMANTIC_VERBOSITY", "standard") != "verbose":
            return
        call_record = result.call_record
        usage = getattr(call_record, "usage", None)
        try:
            append_case_evidence_event(
                Path(
                    os.environ.get(
                        "VERITY_SEMANTIC_CASE_EVIDENCE_PATH",
                        "reports/semantic/case-evidence.jsonl",
                    )
                ),
                event={
                    "schema_version": 1,
                    "record_type": "judge_response",
                    "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                    "test_id": get_current_test_id(),
                    "judge_model": self.model_name,
                    "attempt": attempt,
                    "finish_reason": finish_reason,
                    "max_tokens": max_tokens,
                    "answer": result.content,
                    "usage": {
                        "prompt_tokens": getattr(usage, "prompt_tokens", None),
                        "completion_tokens": getattr(usage, "completion_tokens", None),
                        "total_tokens": getattr(usage, "total_tokens", None),
                    },
                },
            )
        except Exception:
            logger.exception("Could not persist verbose semantic judge output")

    async def a_generate(self, prompt: str, *, structured_output: bool = True) -> str:
        """Async generation — used by async evaluation paths."""
        # run_in_executor does not copy ContextVars automatically, so carry
        # the active pytest test id into the worker explicitly.
        context = contextvars.copy_context()
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, context.run, self.generate, prompt, structured_output
        )


def _finish_reason(raw_response: Any) -> str | None:
    """Read provider finish metadata without exposing reasoning or response text."""
    try:
        choice = raw_response.choices[0]
        value = getattr(choice, "finish_reason", None)
        return str(value).lower() if value else None
    except (AttributeError, IndexError, TypeError):
        return None


def _is_json_object(content: str) -> bool:
    """Check JSON syntax only; schema validation belongs to the metric parser."""
    try:
        return isinstance(json.loads(content), dict)
    except (json.JSONDecodeError, TypeError):
        return False


# ---------------------------------------------------------------------------
# DeepEval adapter
# ---------------------------------------------------------------------------


class DeepEvalJudge:
    """DeepEval-compatible LLM adapter backed by ProviderJudge.

    Creates a DeepEvalBaseLLM subclass at call time so the deepeval import
    only occurs when the class is instantiated (optional dependency).
    """

    def __init__(self, judge: ProviderJudge) -> None:
        self._adapter = self._build_adapter(judge)

    @staticmethod
    def _build_adapter(judge: ProviderJudge) -> Any:
        try:
            from deepeval.models.base_model import DeepEvalBaseLLM
        except ImportError as exc:
            raise ImportError(
                "deepeval is required for Tier-2 evaluation. Install with: uv sync --extra semantic"
            ) from exc

        class _Adapter(DeepEvalBaseLLM):  # type: ignore[no-untyped-call]
            def get_model_name(self) -> str:
                return judge.model_name

            def load_model(self, *args: Any, **kwargs: Any) -> DeepEvalBaseLLM:
                return self

            def generate(self, prompt: str) -> str:
                return judge.generate(prompt)

            async def a_generate(self, prompt: str) -> str:
                return await judge.a_generate(prompt)

        return _Adapter()

    @property
    def adapter(self) -> Any:
        return self._adapter


# ---------------------------------------------------------------------------
# RAGAS adapter
# ---------------------------------------------------------------------------


class RagasJudge:
    """RAGAS-compatible LLM adapter backed by ProviderJudge.

    RAGAS metrics accept a custom llm= argument. This wraps ProviderJudge
    in a minimal LangChain-style shim so RAGAS can call the judge via its
    standard interface.

    The adapter is lazily constructed to avoid importing ragas/langchain_core at
    module import time (optional dependency).
    """

    def __init__(self, judge: ProviderJudge) -> None:
        self._judge = judge
        self._adapter: Any = None

    def _ensure_adapter(self) -> Any:
        if self._adapter is not None:
            return self._adapter
        self._adapter = self._build_adapter(self._judge)
        return self._adapter

    @staticmethod
    def _build_adapter(judge: ProviderJudge) -> Any:
        """Build the RAGAS-compatible shim at runtime."""
        try:
            from langchain_core.outputs import Generation, LLMResult
        except ImportError as exc:
            raise ImportError(
                "langchain-core is required for RAGAS metrics. "
                "Install with: uv sync --extra semantic"
            ) from exc

        class _RagasLLMShim:
            """Minimal ragas.llms.base.BaseRagasLLM-compatible adapter.

            RAGAS's PydanticPrompt calls `await llm.generate(prompt_value, n=...)`
            and expects an LLMResult with `n` Generations back -- not a LangChain
            chat-messages interface.
            """

            async def generate(
                self,
                prompt: Any,
                n: int = 1,
                temperature: float | None = None,
                stop: list[str] | None = None,
                callbacks: Any = None,
            ) -> Any:
                text = prompt.to_string() if hasattr(prompt, "to_string") else str(prompt)
                # RAGAS emits its own per-prompt Pydantic schema and also uses
                # a StringIO schema when repairing malformed output. A generic
                # JSON-object constraint can cause the repair call to repeat
                # the invalid object instead of returning the required wrapper.
                generations = [
                    Generation(text=await judge.a_generate(text, structured_output=False))
                    for _ in range(n)
                ]
                return LLMResult(generations=[generations])

        return _RagasLLMShim()

    @property
    def adapter(self) -> Any:
        return self._ensure_adapter()
