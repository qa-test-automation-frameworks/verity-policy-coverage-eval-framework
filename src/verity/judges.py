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
import logging
import warnings
from typing import Any

from verity.config import Settings
from verity.cost import RunAccumulator
from verity.providers import LLMProvider

logger = logging.getLogger(__name__)


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

    def generate(self, prompt: str) -> str:
        """Synchronous generation — used by DeepEval and RAGAS metrics."""
        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
        result = self._provider.complete(messages=messages, label="judge")
        return result.content

    async def a_generate(self, prompt: str) -> str:
        """Async generation — used by async evaluation paths."""
        return await asyncio.get_running_loop().run_in_executor(None, self.generate, prompt)


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
                "deepeval is required for Tier-2 evaluation. Install with: uv sync --group semantic"
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
                "Install with: uv sync --group semantic"
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
                generations = [Generation(text=await judge.a_generate(text)) for _ in range(n)]
                return LLMResult(generations=[generations])

        return _RagasLLMShim()

    @property
    def adapter(self) -> Any:
        return self._ensure_adapter()
