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
    nvidia = "nvidia"
    google = "google"


# ---------------------------------------------------------------------------
# Per-provider routing table: default model slug, litellm model prefix, the
# exact litellm model string for that default (which may not simply be
# prefix + default_model — e.g. openrouter's default routes through the
# "z-ai/" org namespace), and default api_base.
# ---------------------------------------------------------------------------
# api_base is "" for providers whose litellm handler resolves its own endpoint
# natively (e.g. gemini/*) and should not receive a custom api_base unless
# explicitly overridden.
_PROVIDER_DEFAULTS: dict[Provider, dict[str, str]] = {
    Provider.zai: {
        "default_model": "glm-4.5",
        "litellm_prefix": "openai/",
        "litellm_model": "openai/glm-4.5",
        "api_base": "https://api.z.ai/v1",
    },
    Provider.openrouter: {
        "default_model": "glm-4.5",
        "litellm_prefix": "openrouter/",
        "litellm_model": "openrouter/z-ai/glm-4.5",
        "api_base": "https://openrouter.ai/api/v1",
    },
    Provider.together: {
        "default_model": "glm-4.5",
        "litellm_prefix": "together_ai/",
        "litellm_model": "together_ai/zai-org/GLM-4.5",
        "api_base": "https://api.together.xyz/v1",
    },
    Provider.nvidia: {
        "default_model": "nvidia/nemotron-3-ultra-550b-a55b",
        "litellm_prefix": "nvidia_nim/",
        "litellm_model": "nvidia_nim/nvidia/nemotron-3-ultra-550b-a55b",
        "api_base": "https://integrate.api.nvidia.com/v1",
    },
    Provider.google: {
        "default_model": "gemini-3-flash",
        "litellm_prefix": "gemini/",
        "litellm_model": "gemini/gemini-3-flash",
        "api_base": "",
    },
}


def resolve_provider(
    provider: Provider,
    model: str,
    api_base_override: str | None = None,
) -> tuple[str, str]:
    """Return (litellm_model_string, api_base) for a given provider + model."""
    defaults = _PROVIDER_DEFAULTS[provider]
    if model == defaults["default_model"]:
        litellm_model = defaults["litellm_model"]
    else:
        litellm_model = f"{defaults['litellm_prefix']}{model}"
    api_base = api_base_override or defaults["api_base"]
    return litellm_model, api_base


class JudgeConfig(BaseSettings):
    """Configuration for the LLM-as-judge (swappable, pinned, temp=0)."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", env_prefix="VERITY_JUDGE_", extra="ignore"
    )

    model: str = "openai/gpt-4o-mini"
    temperature: float = 0.0
    max_tokens: int = 1024
    # Optional: run the judge on a different provider than the SUT model.
    # Defaults to the SUT's provider when unset, so single-provider setups
    # keep working unchanged; set this to avoid sharing one provider's rate
    # limit between SUT calls and judge calls (e.g. RAGAS metrics).
    provider: Provider | None = None


class RetrievalConfig(BaseSettings):
    """Configuration for the SUT RAG retriever."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", env_prefix="VERITY_", extra="ignore"
    )

    corpus_dir: Path = Path("src/sut/corpus")
    chunk_size: int = 160
    chunk_overlap: int = 30
    top_k: int = 3
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

    # Provider / model — defaults to the only provider/model pairing with a
    # verified, reproducible live run committed in this repo (see the ADR-0001
    # amendment and README Limitations). zai/glm-4.5 remains fully supported
    # and is what the hermetic Tier-1/Tier-3 suites pin internally regardless
    # of this setting.
    provider: Provider = Provider.openrouter
    model: str = "openai/gpt-4o-mini"

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
    nvidia_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("VERITY_NVIDIA_API_KEY", "NVIDIA_API_KEY"),
    )
    google_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("VERITY_GOOGLE_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY"),
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
    nvidia_api_base: str | None = Field(
        default=None,
        validation_alias=AliasChoices("VERITY_NVIDIA_API_BASE", "NVIDIA_API_BASE"),
    )
    google_api_base: str | None = Field(
        default=None,
        validation_alias=AliasChoices("VERITY_GOOGLE_API_BASE", "GOOGLE_API_BASE"),
    )

    # Generation defaults
    temperature: float = 0.0
    max_tokens: int = 2048
    timeout: int = 60
    retries: int = 3
    semantic_samples: int = 1

    # Optional member-scoped request token enforcement for demos that need
    # a lightweight cross-member access boundary. Disabled by default.
    member_auth_required: bool = False
    member_tokens_json: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("VERITY_MEMBER_TOKENS"),
    )

    # SUT profile: "clean" (default) runs the hardened agent variant, so a
    # fresh `make demo` run behaves safely out of the box. "seeded" preserves
    # the intentionally-defective behavior (ambiguous tool-arg guidance,
    # unredacted PII logging) that the eval suite's defect-detection cases are
    # built around; the deterministic and semantic test fixtures pin it
    # explicitly since their cassettes were recorded against that profile.
    sut_profile: Literal["seeded", "clean"] = "clean"

    # Nested configs. Constructed via default_factory so each Settings()
    # call reads the environment fresh at instantiation time — a bare
    # `JudgeConfig()` class-level default would be evaluated exactly once,
    # at module-import time, permanently freezing whatever .env/environment
    # happened to be present the first time this module was imported.
    judge: JudgeConfig = Field(default_factory=JudgeConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)

    # Paths
    datasets_dir: Path = Path("datasets")
    golden_dir: Path | None = None
    reports_dir: Path = Path("reports")

    @property
    def resolved_golden_dir(self) -> Path:
        return self.golden_dir or self.datasets_dir / "golden"

    # Cassette record/replay
    cassette_mode: Literal["off", "replay", "record"] = "off"
    cassette_dir: Path = Path("datasets/cassettes")

    @field_validator("temperature")
    @classmethod
    def _clamp_temperature(cls, v: float) -> float:
        if not (0.0 <= v <= 2.0):
            raise ValueError("temperature must be in [0.0, 2.0]")
        return v

    @field_validator("semantic_samples")
    @classmethod
    def _validate_semantic_samples(cls, v: int) -> int:
        if v < 1:
            raise ValueError("semantic_samples must be >= 1")
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
            Provider.nvidia: self.nvidia_api_key,
            Provider.google: self.google_api_key,
        }
        return mapping[self.provider]

    def _active_api_base_override(self) -> str | None:
        mapping: dict[Provider, str | None] = {
            Provider.zai: self.zai_api_base,
            Provider.openrouter: self.openrouter_api_base,
            Provider.together: self.together_api_base,
            Provider.nvidia: self.nvidia_api_base,
            Provider.google: self.google_api_base,
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


def reset_settings() -> None:
    """Clear the cached Settings instance after environment changes."""
    global _settings
    _settings = None
