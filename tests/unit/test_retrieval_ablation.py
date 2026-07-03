"""Unit tests for the pure retrieval-ablation report renderer."""

from __future__ import annotations

from scripts.retrieval_ablation import render_ablation_report


def test_render_marks_current_default_row() -> None:
    sweeps = {
        "_LEXICAL_WEIGHT": [
            {"value": 0.0, "pass_rate": 0.4, "mean_source_precision": 0.5},
            {"value": 0.5, "pass_rate": 1.0, "mean_source_precision": 0.8},
        ],
    }
    report = render_ablation_report(sweeps, {"_LEXICAL_WEIGHT": 0.5})
    assert "0.50 *(current default)*" in report
    assert "0.00 |" in report


def test_render_includes_every_swept_parameter() -> None:
    sweeps = {
        "_LEXICAL_WEIGHT": [{"value": 0.5, "pass_rate": 1.0, "mean_source_precision": 0.8}],
        "_DISTANCE_MARGIN": [{"value": 0.2, "pass_rate": 1.0, "mean_source_precision": 0.8}],
        "_MAX_RELEVANT_DISTANCE": [{"value": 0.45, "pass_rate": 1.0, "mean_source_precision": 0.8}],
    }
    report = render_ablation_report(sweeps, {})
    assert "Lexical overlap weight" in report
    assert "Distance margin" in report
    assert "No-answer distance ceiling" in report


def test_render_reports_pass_rate_as_percentage() -> None:
    sweeps = {
        "_DISTANCE_MARGIN": [{"value": 0.2, "pass_rate": 0.875, "mean_source_precision": 0.789}],
    }
    report = render_ablation_report(sweeps, {})
    assert "88%" in report
    assert "0.789" in report


def test_render_ends_with_regenerate_hint() -> None:
    report = render_ablation_report({}, {})
    assert "make retrieval-ablation" in report
