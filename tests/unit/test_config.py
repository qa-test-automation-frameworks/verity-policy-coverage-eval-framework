"""Unit tests for Pydantic config and provider routing."""

from __future__ import annotations

import pytest

from verity.config import Provider, Settings, resolve_provider


class TestResolveProvider:
    def test_zai_default(self) -> None:
        model, base = resolve_provider(Provider.zai, "glm-4-plus")
        assert model == "openai/glm-4-plus"
        assert "bigmodel.cn" in base

    def test_openrouter(self) -> None:
        model, base = resolve_provider(Provider.openrouter, "glm-4-plus")
        assert "openrouter" in model
        assert "openrouter.ai" in base

    def test_together(self) -> None:
        model, base = resolve_provider(Provider.together, "glm-4-plus")
        assert "together_ai" in model
        assert "together.xyz" in base

    def test_api_base_override(self) -> None:
        _, base = resolve_provider(
            Provider.zai, "glm-4-plus", api_base_override="https://custom.host/v1"
        )
        assert base == "https://custom.host/v1"


class TestSettings:
    def test_defaults_do_not_raise(self) -> None:
        # No .env present; should load with warnings but not crash
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            s = Settings()
        assert s.provider == Provider.zai
        assert s.model == "glm-4-plus"
        assert s.temperature == 0.0
        assert s.semantic_samples == 1

    def test_invalid_temperature_raises(self) -> None:
        with pytest.raises(ValueError):
            Settings(temperature=3.0)

    def test_invalid_semantic_samples_raises(self) -> None:
        with pytest.raises(ValueError):
            Settings(semantic_samples=0)

    def test_semantic_samples_env_is_loaded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import warnings

        monkeypatch.setenv("VERITY_SEMANTIC_SAMPLES", "3")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            s = Settings(_env_file=None)
        assert s.semantic_samples == 3

    def test_resolved_provider_returns_tuple(self) -> None:
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            s = Settings(provider=Provider.zai)
        litellm_model, api_base, key = s.resolved_provider()
        assert litellm_model.startswith("openai/")
        assert isinstance(api_base, str)
        assert key is None  # no key set in test env

    def test_prefixed_provider_key_env_is_loaded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import warnings

        monkeypatch.setenv("VERITY_ZAI_API_KEY", "prefixed-key")
        with warnings.catch_warnings(record=True) as warnings_seen:
            warnings.simplefilter("always")
            s = Settings(_env_file=None)
        assert s.resolved_provider()[2] == "prefixed-key"
        assert warnings_seen == []

    def test_legacy_provider_key_env_is_loaded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import warnings

        monkeypatch.delenv("VERITY_ZAI_API_KEY", raising=False)
        monkeypatch.setenv("ZAI_API_KEY", "legacy-key")
        with warnings.catch_warnings(record=True) as warnings_seen:
            warnings.simplefilter("always")
            s = Settings(_env_file=None)
        assert s.resolved_provider()[2] == "legacy-key"
        assert warnings_seen == []

    def test_prefixed_provider_base_env_is_loaded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import warnings

        monkeypatch.setenv("VERITY_ZAI_API_BASE", "https://runtime.example/v1")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            s = Settings(_env_file=None)
        assert s.resolved_provider()[1] == "https://runtime.example/v1"
