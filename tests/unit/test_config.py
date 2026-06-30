"""Unit tests for Pydantic config and provider routing."""

from __future__ import annotations

import pytest

from verity.config import Provider, Settings, resolve_provider


class TestResolveProvider:
    def test_zai_default(self) -> None:
        model, base = resolve_provider(Provider.zai, "glm-5.2")
        assert model == "openai/glm-5.2"
        assert "z.ai" in base

    def test_openrouter(self) -> None:
        model, base = resolve_provider(Provider.openrouter, "glm-5.2")
        assert "openrouter" in model
        assert "openrouter.ai" in base

    def test_together(self) -> None:
        model, base = resolve_provider(Provider.together, "glm-5.2")
        assert "together_ai" in model
        assert "together.xyz" in base

    def test_api_base_override(self) -> None:
        _, base = resolve_provider(Provider.zai, "glm-5.2", api_base_override="https://custom.host/v1")
        assert base == "https://custom.host/v1"


class TestSettings:
    def test_defaults_do_not_raise(self) -> None:
        # No .env present; should load with warnings but not crash
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            s = Settings()
        assert s.provider == Provider.zai
        assert s.model == "glm-5.2"
        assert s.temperature == 0.0

    def test_invalid_temperature_raises(self) -> None:
        with pytest.raises(ValueError):
            Settings(temperature=3.0)

    def test_resolved_provider_returns_tuple(self) -> None:
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            s = Settings(provider=Provider.zai)
        litellm_model, api_base, key = s.resolved_provider()
        assert litellm_model.startswith("openai/")
        assert isinstance(api_base, str)
        assert key is None  # no key set in test env
