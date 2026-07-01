"""Tests for hosted model selection."""

from __future__ import annotations

from scripts.select_openrouter_free_models import render_table, select_candidates


def _model(
    model_id: str,
    *,
    prompt: str = "0",
    completion: str = "0",
    hf: str | None = "org/model",
    params: list[str] | None = None,
    intelligence: float | None = None,
    coding: float | None = None,
    agentic: float | None = None,
    context: int = 128000,
    input_modalities: list[str] | None = None,
    output_modalities: list[str] | None = None,
) -> dict:
    benchmark = {}
    if intelligence is not None:
        benchmark["intelligence_index"] = intelligence
    if coding is not None:
        benchmark["coding_index"] = coding
    if agentic is not None:
        benchmark["agentic_index"] = agentic
    return {
        "id": model_id,
        "name": model_id,
        "hugging_face_id": hf,
        "context_length": context,
        "pricing": {"prompt": prompt, "completion": completion},
        "supported_parameters": params if params is not None else ["tools", "temperature"],
        "architecture": {
            "input_modalities": input_modalities if input_modalities is not None else ["text"],
            "output_modalities": output_modalities if output_modalities is not None else ["text"],
        },
        "benchmarks": {"artificial_analysis": benchmark},
    }


def test_select_candidates_ranks_by_intelligence() -> None:
    models = [
        _model("vendor/second:free", intelligence=20.0, coding=50.0, agentic=10.0),
        _model("vendor/first:free", intelligence=30.0, coding=10.0, agentic=5.0),
    ]
    candidates = select_candidates(models)
    assert [candidate.model_id for candidate in candidates] == [
        "vendor/first:free",
        "vendor/second:free",
    ]


def test_select_candidates_filters_unsuitable_models() -> None:
    models = [
        _model("vendor/usable:free", intelligence=10.0),
        _model("vendor/priced:free", prompt="0.1", intelligence=99.0),
        _model("vendor/not-free", intelligence=99.0),
        _model("vendor/no-weights:free", hf=None, intelligence=99.0),
        _model("vendor/no-tools:free", params=["temperature"], intelligence=99.0),
        _model("vendor/image-only:free", input_modalities=["image"], intelligence=99.0),
    ]
    candidates = select_candidates(models)
    assert [candidate.model_id for candidate in candidates] == ["vendor/usable:free"]


def test_select_candidates_uses_context_as_tiebreaker() -> None:
    models = [
        _model("vendor/short:free", intelligence=20.0, context=1000),
        _model("vendor/long:free", intelligence=20.0, context=2000),
    ]
    candidates = select_candidates(models)
    assert candidates[0].model_id == "vendor/long:free"


def test_render_table_includes_core_fields() -> None:
    candidate = select_candidates(
        [_model("vendor/model:free", hf="vendor/model", intelligence=12.3, coding=4.5, agentic=6.7)]
    )[0]
    table = render_table([candidate])
    assert "vendor/model:free" in table
    assert "vendor/model" in table
    assert "12.3" in table
    assert "yes" in table
