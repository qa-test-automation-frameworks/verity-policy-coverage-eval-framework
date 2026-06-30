"""Pydantic-settings configuration for the Verity evaluation framework."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Provider(StrEnum):
    zai = "zai"
    openrouter = "openrouter"
    together = "together"


# ---------------------------------------------------------------------------
# Per-provider routing table (litellm model string, default api_base)
# ---------------------------------------------------------------------------
_PROVIDER_DEFAULTS: dict[Provider, dict[str, str]] = {
    Provider.zai: {
        "litellm_model": "openai/glm-5.2",
        "api_base": "https://api.z.ai/v1",
    },
    Provider.openrouter: {
        "litellm_model": "openrouter/z-ai/glm-5.2",
        "api_base": "https://openrouter.ai/api/v1",
    },
    Provider.together: {
        "litellm_model": "together_ai/zai-org/GLM-5.2",
        "api_base": "https://api.together.xyz/v1",
    },
}


def resolve_provider(
    provider: Provider,
    model: str,
    api_base_override: str | None = None,
) -> tuple[str, str]:
    """Return (litellm_model_string, api_base) for a given provider + model."""
    defaults = _PROVIDER_DEFAULTS[provider]
    litellm_model = defaults["litellm_model"]
    # For Z.ai/OpenRouter, the model name is embedded in the route above.
    # If caller supplies a non-default model, swap in just the trailing slug.
    if provider == Provider.zai and model != "glm-5.2":
        litellm_model = f"openai/{model}"
    api_base = api_base_override or defaults["api_base"]
    return litellm_model, api_base


class JudgeConfig(BaseSettings):
    """Configuration for the LLM-as-judge (swappable, pinned, temp=0)."""

    model_config = SettingsConfigDict(env_prefix="VERITY_JUDGE_", extra="ignore")

    model: str = "glm-5.2"
    temperature: float = 0.0
    max_tokens: int = 1024


class RetrievalConfig(BaseSettings):
    """Configuration for the SUT RAG retriever."""

    model_config = SettingsConfigDict(env_prefix="VERITY_", extra="ignore")

    corpus_dir: Path = Path("src/sut/corpus")
    chunk_size: int = 500
    chunk_overlap: int = 50
    top_k: int = 5
    embedding_model: str = "all-MiniLM-L6-v2"
    persist_dir: Path = Path(".chroma")


class Settings(BaseSettings):
    """Root settings object; reads from .env or environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="VERITY_",
        extra="ignore",
        populate_by_name=True,
    )

    # Provider / model
    provider: Provider = Provider.zai
    model: str = "glm-5.2"

    # API keys (SecretStr keeps them out of repr/logs)
    zai_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("VERITY_ZAI_API_KEY", "ZAI_API_KEY"),
    )
    openrouter_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("VERITY_OPENROUTER_API_KEY", "OPENROUTER_API_KEY"),
    )
    together_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("VERITY_TOGETHER_API_KEY", "TOGETHER_API_KEY"),
    )

    # API base overrides
    zai_api_base: str | None = Field(
        default=None,
        validation_alias=AliasChoices("VERITY_ZAI_API_BASE", "ZAI_API_BASE"),
    )
    openrouter_api_base: str | None = Field(
        default=None,
        validation_alias=AliasChoices("VERITY_OPENROUTER_API_BASE", "OPENROUTER_API_BASE"),
    )
    together_api_base: str | None = Field(
        default=None,
        validation_alias=AliasChoices("VERITY_TOGETHER_API_BASE", "TOGETHER_API_BASE"),
    )

    # Generation defaults
    temperature: float = 0.0
    max_tokens: int = 2048
    timeout: int = 60
    retries: int = 3

    # Nested configs (instantiated as defaults; env vars still apply)
    judge: JudgeConfig = JudgeConfig()
    retrieval: RetrievalConfig = RetrievalConfig()

    # Paths
    datasets_dir: Path = Path("datasets")
    reports_dir: Path = Path("reports")

    # Cassette record/replay
    cassette_mode: Literal["off", "replay", "record"] = "off"
    cassette_dir: Path = Path("datasets/cassettes")

    @field_validator("temperature")
    @classmethod
    def _clamp_temperature(cls, v: float) -> float:
        if not (0.0 <= v <= 2.0):
            raise ValueError("temperature must be in [0.0, 2.0]")
        return v

    @model_validator(mode="after")
    def _check_api_key_present_for_provider(self) -> Settings:
        """Warn (not error) if the active provider's key is missing — deferred live call."""
        key = self._active_api_key()
        if key is None:
            import warnings

            warnings.warn(
                f"No API key found for provider '{self.provider.value}'. "
                "Live calls will fail. Set the appropriate key in .env or environment.",
                stacklevel=2,
            )
        return self

    def _active_api_key(self) -> SecretStr | None:
        mapping: dict[Provider, SecretStr | None] = {
            Provider.zai: self.zai_api_key,
            Provider.openrouter: self.openrouter_api_key,
            Provider.together: self.together_api_key,
        }
        return mapping[self.provider]

    def _active_api_base_override(self) -> str | None:
        mapping: dict[Provider, str | None] = {
            Provider.zai: self.zai_api_base,
            Provider.openrouter: self.openrouter_api_base,
            Provider.together: self.together_api_base,
        }
        return mapping[self.provider]

    def resolved_provider(self) -> tuple[str, str, str | None]:
        """Return (litellm_model, api_base, api_key_value | None)."""
        litellm_model, api_base = resolve_provider(
            self.provider, self.model, self._active_api_base_override()
        )
        secret = self._active_api_key()
        return litellm_model, api_base, secret.get_secret_value() if secret else None


# Module-level singleton (lazy; tests can override by passing settings explicitly)
_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
