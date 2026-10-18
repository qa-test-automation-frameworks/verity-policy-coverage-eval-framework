"""Gemini free-project gating, real adapter routing and bounded smoke controls."""

from __future__ import annotations

import json
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import litellm.exceptions
import pytest
import yaml
from scripts.run_free_hosted_calibration import (
    DEFAULT_MODEL,
    build_settings,
    heldout_prompts,
    main,
    require_supported_model,
    run_smoke,
)

from verity.calibration import CALIBRATION_METRICS, load_heldout_calibration
from verity.cost import RunAccumulator, Usage
from verity.providers import CompletionResult, LLMProvider


def test_settings_isolate_paid_ambient_configuration(monkeypatch):
    for name, value in {
        "VERITY_PROVIDER": "openrouter",
        "VERITY_MODEL": "paid/model",
        "VERITY_GOOGLE_API_BASE": "https://attacker.invalid",
        "VERITY_OPENROUTER_API_KEY_2": "another-key",
        "VERITY_RETRIES": "9",
        "VERITY_JUDGE_MODEL": "paid/judge",
        "VERITY_CASSETTE_MODE": "replay",
    }.items():
        monkeypatch.setenv(name, value)
    settings = build_settings("test-key", DEFAULT_MODEL)
    assert settings.provider.value == "google"
    assert settings.model == DEFAULT_MODEL
    assert settings.judge.model == DEFAULT_MODEL
    assert settings.google_api_base is None
    assert settings.openrouter_api_key_2 is None
    assert settings.retries == 0
    assert settings.timeout == 45
    assert settings.cassette_mode == "off"
    assert settings.resolved_provider() == (f"gemini/{DEFAULT_MODEL}", "", "test-key")


def test_actual_gemini_http_body_has_generation_bounds_and_no_paid_tools(monkeypatch):
    sent = []

    def send(client, request, **kwargs):
        assert request.url.host == "generativelanguage.googleapis.com"
        assert request.url.path.endswith(f"/{DEFAULT_MODEL}:generateContent")
        sent.append(json.loads(request.content))
        return httpx.Response(
            200,
            request=request,
            json={
                "candidates": [
                    {
                        "content": {"role": "model", "parts": [{"text": "Score: 8"}]},
                        "finishReason": "STOP",
                        "index": 0,
                    }
                ],
                "usageMetadata": {
                    "promptTokenCount": 5,
                    "candidatesTokenCount": 3,
                    "totalTokenCount": 8,
                },
                "modelVersion": DEFAULT_MODEL,
                "responseId": "free-test",
            },
        )

    monkeypatch.setattr(httpx.Client, "send", send)
    result = LLMProvider(build_settings("test-key", DEFAULT_MODEL)).complete(
        [{"role": "user", "content": "public synthetic test"}],
        max_tokens=100,
    )
    assert result.content == "Score: 8"
    assert len(sent) == 1
    config = sent[0]["generationConfig"]
    assert config.get("maxOutputTokens", config.get("max_output_tokens")) == 100, config
    assert sent[0]["generationConfig"]["temperature"] == 0
    assert "tools" not in sent[0]
    assert "cachedContent" not in sent[0]


def test_actual_http_429_is_not_retried(monkeypatch):
    sent = []

    def send(client, request, **kwargs):
        sent.append(request)
        return httpx.Response(
            429,
            request=request,
            json={
                "error": {
                    "code": 429,
                    "message": "Free quota exhausted",
                    "status": "RESOURCE_EXHAUSTED",
                }
            },
        )

    monkeypatch.setattr(httpx.Client, "send", send)
    with pytest.raises(litellm.exceptions.RateLimitError):
        LLMProvider(build_settings("test-key", DEFAULT_MODEL)).complete(
            [{"role": "user", "content": "public"}],
        )
    assert len(sent) == 1


@pytest.mark.parametrize("model_id", ["gemini-4-argon", "gemini-flash-latest", "paid/model"])
def test_unreviewed_or_mutable_models_are_rejected(model_id):
    with pytest.raises(ValueError, match="allowlist"):
        build_settings("test-key", model_id)


def test_model_availability_does_not_silently_substitute():
    with pytest.raises(ValueError, match="no substitution"):
        require_supported_model({"name": "models/a-different-model"}, DEFAULT_MODEL)
    with pytest.raises(ValueError, match="generateContent"):
        require_supported_model({"name": f"models/{DEFAULT_MODEL}"}, DEFAULT_MODEL)


def result(content="Score: 8", *, cost=None, tokens=3):
    record = RunAccumulator().log_call(DEFAULT_MODEL, Usage(5, tokens, 5 + tokens), 1)
    raw = SimpleNamespace(
        id="test",
        model=DEFAULT_MODEL,
        provider="google",
        usage=SimpleNamespace(cost=cost),
        choices=[SimpleNamespace(finish_reason="stop")],
    )
    return CompletionResult(content=content, call_record=record, raw_response=raw)


@pytest.mark.parametrize(
    "response", [result("Score: 99"), result(""), result(cost=0.1), result(tokens=20)]
)
def test_invalid_or_nonzero_cost_attempt_is_retained_and_stops(tmp_path, response):
    provider = MagicMock()
    provider.complete.return_value = response
    receipt = {"attempts": []}
    path = tmp_path / "receipt.json"
    with pytest.raises(ValueError):
        run_smoke(
            provider,
            [("one", "prompt"), ("two", "prompt")],
            receipt,
            path,
            max_calls=2,
            max_tokens=10,
            total_output_tokens=20,
            interval=0,
        )
    provider.complete.assert_called_once()
    assert json.loads(path.read_text())["attempts"][0]["status"] == "failed"


def test_call_and_total_output_budgets_are_enforced(tmp_path):
    provider = MagicMock()
    provider.complete.return_value = result(tokens=3)
    receipt = {"attempts": []}
    run_smoke(
        provider,
        [("one", "prompt"), ("two", "prompt"), ("three", "prompt")],
        receipt,
        tmp_path / "receipt.json",
        max_calls=2,
        max_tokens=5,
        total_output_tokens=6,
        interval=0,
    )
    assert provider.complete.call_count == 2
    assert provider.complete.call_args_list[0].kwargs["max_tokens"] == 5
    assert provider.complete.call_args_list[1].kwargs["max_tokens"] == 3
    assert all(attempt["status"] == "success" for attempt in receipt["attempts"])
    assert receipt["attempts"][0]["provider_reported_cost_usd"] is None


def test_failure_receipt_does_not_leak_exception_secrets(tmp_path):
    provider = MagicMock()
    provider.complete.side_effect = RuntimeError("Authorization: Bearer SECRET")
    path = tmp_path / "receipt.json"
    with pytest.raises(RuntimeError):
        run_smoke(
            provider,
            [("one", "prompt")],
            {"attempts": []},
            path,
            max_calls=1,
            max_tokens=10,
            total_output_tokens=10,
            interval=0,
        )
    assert "SECRET" not in path.read_text()


def test_catalogue_preflight_makes_no_inference_call(tmp_path, monkeypatch):
    payload = {"name": f"models/{DEFAULT_MODEL}", "supportedGenerationMethods": ["generateContent"]}
    response = httpx.Response(
        200, request=httpx.Request("GET", "https://google.invalid"), json=payload
    )
    monkeypatch.setattr("scripts.run_free_hosted_calibration.httpx.get", lambda *a, **k: response)
    monkeypatch.setenv("VERITY_GOOGLE_API_KEY", "test-key")
    monkeypatch.setattr(sys, "argv", ["free-smoke", "--out", str(tmp_path)])
    with patch("scripts.run_free_hosted_calibration.LLMProvider") as provider:
        assert main() == 0
    provider.assert_not_called()
    receipt = json.loads(next(tmp_path.glob("smoke-*.json")).read_text())
    assert receipt["attempts"] == []
    assert receipt["billing_plan_verified_by_api"] is False
    assert receipt["status"] == "success"


def test_unconfirmed_billing_stops_before_any_network_request(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["free-smoke", "--live", "--out", str(tmp_path)])
    with patch("scripts.run_free_hosted_calibration.httpx.get") as get:
        assert main() == 1
    get.assert_not_called()
    receipt = json.loads(next(tmp_path.glob("smoke-*.json")).read_text())
    assert "confirmation" in receipt["stop_reason"]
    assert receipt["attempts"] == []


def test_heldout_study_requires_free_project_attestation_before_network(tmp_path, monkeypatch):
    dataset = tmp_path / "heldout.yaml"
    write_heldout_dataset(dataset)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "free-hosted",
            "--live",
            "--heldout-study",
            "--heldout-dataset",
            str(dataset),
            "--out",
            str(tmp_path / "receipts"),
        ],
    )
    with patch("scripts.run_free_hosted_calibration.httpx.get") as get:
        assert main() == 1
    get.assert_not_called()
    receipt = json.loads(next((tmp_path / "receipts").glob("heldout-*.json")).read_text())
    assert receipt["attempts"] == []
    assert "confirmation" in receipt["stop_reason"]


def write_heldout_dataset(path):
    cases = []
    for metric in CALIBRATION_METRICS:
        for index in range(8):
            cases.append(
                {
                    "randomized_case_id": f"blind-{metric}-{index:02d}",
                    "metric": metric,
                    "query": f"Question {index} for {metric}?",
                    "context": [f"Public fictional context for {metric} case {index}."],
                    "candidate_output": f"Fictional response for {metric} case {index}.",
                }
            )
    path.write_text(yaml.safe_dump({"cases": cases}), encoding="utf-8")


def test_heldout_loader_accepts_unlabeled_balanced_set_and_selects_frozen_slice(tmp_path):
    dataset = tmp_path / "heldout.yaml"
    write_heldout_dataset(dataset)

    cases = load_heldout_calibration(dataset)
    prompts = heldout_prompts(dataset, start_index=9, max_calls=3)

    assert len(cases) == 56
    assert [case_id for case_id, _ in prompts] == [
        cases[index].randomized_case_id for index in range(9, 12)
    ]
    assert "Question 1 for completeness?" in prompts[0][1]


def test_heldout_mode_receipt_tracks_hash_and_never_calls_unmocked_provider(tmp_path, monkeypatch):
    dataset = tmp_path / "heldout.yaml"
    write_heldout_dataset(dataset)
    payload = {"name": f"models/{DEFAULT_MODEL}", "supportedGenerationMethods": ["generateContent"]}
    response = httpx.Response(
        200,
        request=httpx.Request("GET", "https://google.invalid"),
        json=payload,
    )
    monkeypatch.setattr("scripts.run_free_hosted_calibration.httpx.get", lambda *a, **k: response)
    monkeypatch.setenv("VERITY_GOOGLE_API_KEY", "test-key")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "free-hosted",
            "--live",
            "--heldout-study",
            "--confirm-free-project",
            "--heldout-dataset",
            str(dataset),
            "--start-index",
            "8",
            "--max-calls",
            "1",
            "--out",
            str(tmp_path / "receipts"),
        ],
    )
    provider = MagicMock()
    provider.complete.return_value = result()
    with patch("scripts.run_free_hosted_calibration.LLMProvider", return_value=provider):
        assert main() == 0

    receipt = json.loads(next((tmp_path / "receipts").glob("heldout-*.json")).read_text())
    assert receipt["purpose"].startswith("bounded live D05 held-out")
    assert receipt["study_plan_id"] == "D05-GEMINI-HELDOUT-2026-10-18-v1"
    assert receipt["selected_case_ids"] == ["blind-completeness-00"]
    assert receipt["dataset_sha256"]
    assert receipt["attempts"][0]["status"] == "success"
    assert provider.complete.call_args.kwargs["label"] == "d05-heldout-calibration"


def test_exhausted_output_budget_stops_before_second_request(tmp_path):
    provider = MagicMock()
    provider.complete.return_value = result(tokens=3)
    path = tmp_path / "receipt.json"
    with pytest.raises(ValueError, match="budget exhausted"):
        run_smoke(
            provider,
            [("one", "prompt"), ("two", "prompt")],
            {"attempts": []},
            path,
            max_calls=2,
            max_tokens=3,
            total_output_tokens=3,
            interval=0,
        )
    provider.complete.assert_called_once()
    assert len(json.loads(path.read_text())["attempts"]) == 1
