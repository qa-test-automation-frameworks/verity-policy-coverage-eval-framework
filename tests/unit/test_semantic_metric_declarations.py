"""Metadata checks for Tier-2 metric declarations."""

from __future__ import annotations

from pathlib import Path

from verity.golden import load_golden

SUPPORTED_SEMANTIC_METRICS = {
    "answer_relevancy",
    "faithfulness",
    "g_eval_completeness",
    "g_eval_disambiguation",
    "g_eval_injection_compliance",
    "g_eval_pii_leakage",
    "g_eval_refusal",
    "task_completion",
}


def test_declared_semantic_metrics_are_exercised() -> None:
    unknown = {
        metric
        for case in load_golden(Path("datasets/golden"))
        for metric in case.semantic_metrics
        if metric not in SUPPORTED_SEMANTIC_METRICS
    }
    assert unknown == set()
