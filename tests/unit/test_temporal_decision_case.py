"""No-key authored controls for the temporal decision case."""

import json
from pathlib import Path

from scripts.temporal_decision_case import build_report

_ROOT = Path(__file__).resolve().parents[2]


def test_authored_controls_separate_literal_grounding_from_temporal_truth() -> None:
    report = build_report(_ROOT)
    controls = {item["control"]: item for item in report["controls"]}

    assert controls["stale"]["grounding"]["all_answer_amounts_appear_in_evidence"] is True
    assert controls["stale"]["temporal"]["status"] == "FAIL"
    assert controls["stale"]["decision"] == "quarantine"
    assert controls["current"]["grounding"]["all_answer_amounts_appear_in_evidence"] is True
    assert controls["current"]["temporal"]["status"] == "PASS"
    assert controls["current"]["decision"] == "ship"
    assert report["decision"] == "quarantine"
    assert report["source_kind"] == "authored_control"
    assert report["sampling"]["provider_requests"] == 0
    assert report["sampling"]["cost_usd"] is None


def test_replacing_the_seeded_stale_answer_reverses_the_control_decision() -> None:
    report = build_report(
        _ROOT,
        control="stale",
        answer="The current Silver plan monthly premium is $445 effective 2024-07-01.",
        evidence="src/sut/corpus/amendments.md",
    )

    assert report["controls"][0]["temporal"]["status"] == "PASS"
    assert report["controls"][0]["decision"] == "ship"


def test_checked_in_artifact_matches_the_reproducible_report() -> None:
    artifact = _ROOT / "reports/case-studies/temporal-regression-decision.json"

    assert json.loads(artifact.read_text(encoding="utf-8")) == build_report(_ROOT)
