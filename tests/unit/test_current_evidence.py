"""Focused tests for the versioned evidence inventory."""

from __future__ import annotations

from copy import deepcopy

import pytest
from scripts.check_current_evidence import (
    ROOT,
    EvidenceError,
    load_manifest,
    validate_manifest,
)


@pytest.fixture
def current_manifest() -> dict[str, object]:
    manifest_path = ROOT / "portfolio/current-evidence.json"
    if not manifest_path.is_file():
        pytest.skip("current evidence manifest is source-only and is not in the runtime image")
    return load_manifest(manifest_path)


def test_valid_synthetic_record_is_accepted(current_manifest: dict[str, object]) -> None:
    validate_manifest(current_manifest, ROOT)
    modes = current_manifest["evaluationModes"]
    assert isinstance(modes, dict)
    synthetic = modes["synthetic-replay"]
    assert isinstance(synthetic, dict)
    assert synthetic["status"] == "synthetic-demonstration"


def test_wrong_golden_count_is_rejected(current_manifest: dict[str, object]) -> None:
    changed = deepcopy(current_manifest)
    datasets = changed["datasets"]
    assert isinstance(datasets, dict)
    golden = datasets["golden"]
    assert isinstance(golden, dict)
    golden["count"] = golden["count"] + 1

    with pytest.raises(EvidenceError, match=r"datasets\.golden\.count mismatch"):
        validate_manifest(changed, ROOT)


def test_wrong_report_hash_is_rejected(current_manifest: dict[str, object]) -> None:
    changed = deepcopy(current_manifest)
    modes = changed["evaluationModes"]
    assert isinstance(modes, dict)
    synthetic = modes["synthetic-replay"]
    assert isinstance(synthetic, dict)
    report = synthetic["report"]
    assert isinstance(report, dict)
    report["sha256"] = "0" * 64

    with pytest.raises(EvidenceError, match="hash mismatch"):
        validate_manifest(changed, ROOT)


def test_live_measurement_without_run_or_model_is_rejected(
    current_manifest: dict[str, object],
) -> None:
    changed = deepcopy(current_manifest)
    modes = changed["evaluationModes"]
    assert isinstance(modes, dict)
    live = modes["live-runtime-adapter"]
    assert isinstance(live, dict)
    live["status"] = "measured"

    with pytest.raises(EvidenceError, match="requires a run identifier"):
        validate_manifest(changed, ROOT)

    run = live["run"]
    model = live["model"]
    judge = live["judge"]
    assert isinstance(run, dict) and isinstance(model, dict) and isinstance(judge, dict)
    run["id"] = "source-ref:example"
    run["reason"] = None
    model["value"] = None
    model["source"] = None
    model["reason"] = "model identity was removed for this negative control"
    with pytest.raises(EvidenceError, match="requires model identity"):
        validate_manifest(changed, ROOT)


def test_hallucination_polarity_mismatch_is_rejected(
    current_manifest: dict[str, object],
) -> None:
    changed = deepcopy(current_manifest)
    polarity = changed["hallucinationPolarity"]
    assert isinstance(polarity, dict)
    runtime_metric = polarity["runtimeMetric"]
    assert isinstance(runtime_metric, dict)
    runtime_metric["polarity"] = "higher_is_better"

    with pytest.raises(EvidenceError, match="runtime hallucination metric polarity"):
        validate_manifest(changed, ROOT)
