"""Unit tests for Pydantic config and provider routing."""

from __future__ import annotations

from pathlib import Path

import pytest

from verity.config import Provider, Settings, get_settings, reset_settings, resolve_provider


class TestResolveProvider:
    def test_zai_default(self) -> None:
        model, base = resolve_provider(Provider.zai, "glm-4.5")
        assert model == "openai/glm-4.5"
        assert "z.ai" in base

    def test_openrouter(self) -> None:
        model, base = resolve_provider(Provider.openrouter, "glm-4.5")
        assert "openrouter" in model
        assert "openrouter.ai" in base

    def test_together(self) -> None:
        model, base = resolve_provider(Provider.together, "glm-4.5")
        assert "together_ai" in model
        assert "together.xyz" in base

    def test_openrouter_custom_model(self) -> None:
        model, base = resolve_provider(
            Provider.openrouter,
            "nvidia/nemotron-3-ultra-550b-a55b:free",
        )
        assert model == "openrouter/nvidia/nemotron-3-ultra-550b-a55b:free"
        assert "openrouter.ai" in base

    def test_together_custom_model(self) -> None:
        model, base = resolve_provider(Provider.together, "zai-org/GLM-4.5")
        assert model == "together_ai/zai-org/GLM-4.5"
        assert "together.xyz" in base

    def test_api_base_override(self) -> None:
        _, base = resolve_provider(
            Provider.zai, "glm-4.5", api_base_override="https://custom.host/v1"
        )
        assert base == "https://custom.host/v1"

    def test_default_settings_provider_model_pairing(self) -> None:
        # Documents the actual resolved pairing for the framework-wide
        # default: Settings.provider/model do not have to match a
        # provider's own canonical_model — resolve_provider() falls back to
        # prefix + model for any model that isn't that provider's shortcut.
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            s = Settings(_env_file=None)
        model, base = resolve_provider(s.provider, s.model)
        assert model == "openrouter/openai/gpt-4o-mini"
        assert "openrouter.ai" in base


class TestSettings:
    def test_defaults_do_not_raise(self) -> None:
        # Isolated from any local .env — verifies the hardcoded defaults, not
        # whatever a developer happens to have configured on disk.
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            s = Settings(_env_file=None)
        assert s.provider == Provider.openrouter
        assert s.model == "openai/gpt-4o-mini"
        assert s.temperature == 0.0
        assert s.semantic_samples == 1
        assert s.retrieval.chunk_size == 160
        assert s.retrieval.chunk_overlap == 30
        assert s.retrieval.top_k == 3

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

    def test_dataset_paths_can_be_overridden(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import warnings

        monkeypatch.setenv("VERITY_DATASETS_DIR", "alternate-datasets")
        monkeypatch.setenv("VERITY_GOLDEN_DIR", "alternate-golden")
        monkeypatch.setenv("VERITY_CORPUS_DIR", "alternate-corpus")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            s = Settings(_env_file=None)
        assert s.datasets_dir == Path("alternate-datasets")
        assert s.resolved_golden_dir == Path("alternate-golden")
        assert s.retrieval.corpus_dir == Path("alternate-corpus")

    def test_golden_dir_defaults_under_datasets_dir(self) -> None:
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            s = Settings(_env_file=None, datasets_dir=Path("policy-v2"))
        assert s.resolved_golden_dir == Path("policy-v2/golden")

    def test_retrieval_config_env_file_is_loaded(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import warnings

        env_file = tmp_path / ".env"
        env_file.write_text("VERITY_TOP_K=5\nVERITY_CHUNK_SIZE=120\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            s = Settings(_env_file=None)
        assert s.retrieval.top_k == 5
        assert s.retrieval.chunk_size == 120

    def test_resolved_provider_returns_tuple(self) -> None:
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            # zai_api_key is pinned explicitly (not left to env/.env lookup):
            # constructor kwargs take precedence over any real key a
            # developer's environment or .env may happen to provide.
            s = Settings(_env_file=None, provider=Provider.zai, zai_api_key=None)
        litellm_model, api_base, key = s.resolved_provider()
        assert litellm_model.startswith("openai/")
        assert isinstance(api_base, str)
        assert key is None  # explicitly pinned to no key, regardless of ambient env

    def test_prefixed_provider_key_env_is_loaded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import warnings

        monkeypatch.setenv("VERITY_ZAI_API_KEY", "prefixed-key")
        with warnings.catch_warnings(record=True) as warnings_seen:
            warnings.simplefilter("always")
            s = Settings(_env_file=None, provider=Provider.zai)
        assert s.resolved_provider()[2] == "prefixed-key"
        assert warnings_seen == []

    def test_legacy_provider_key_env_is_loaded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import warnings

        monkeypatch.delenv("VERITY_ZAI_API_KEY", raising=False)
        monkeypatch.setenv("ZAI_API_KEY", "legacy-key")
        with warnings.catch_warnings(record=True) as warnings_seen:
            warnings.simplefilter("always")
            s = Settings(_env_file=None, provider=Provider.zai)
        assert s.resolved_provider()[2] == "legacy-key"
        assert warnings_seen == []

    def test_prefixed_provider_base_env_is_loaded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import warnings

        monkeypatch.setenv("VERITY_ZAI_API_BASE", "https://runtime.example/v1")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            s = Settings(_env_file=None, provider=Provider.zai)
        assert s.resolved_provider()[1] == "https://runtime.example/v1"

    def test_resolved_fallback_api_key_for_openrouter(self) -> None:
        s = Settings(
            _env_file=None,
            provider=Provider.openrouter,
            openrouter_api_key="primary-key",
            openrouter_api_key_2="fallback-key",
        )
        assert s.resolved_fallback_api_key() == "fallback-key"

    def test_resolved_fallback_api_key_absent_when_unset(self) -> None:
        with pytest.warns(UserWarning, match="No API key found"):
            s = Settings(_env_file=None, provider=Provider.openrouter, openrouter_api_key=None)
        assert s.resolved_fallback_api_key() is None

    def test_resolved_fallback_api_key_unsupported_provider_returns_none(self) -> None:
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            s = Settings(_env_file=None, provider=Provider.zai, zai_api_key="only-key")
        assert s.resolved_fallback_api_key() is None


class TestSettingsSingleton:
    def test_reset_settings_reloads_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        reset_settings()
        monkeypatch.setenv("VERITY_MODEL", "first-model")
        assert get_settings().model == "first-model"

        monkeypatch.setenv("VERITY_MODEL", "second-model")
        assert get_settings().model == "first-model"

        reset_settings()
        assert get_settings().model == "second-model"
        reset_settings()
