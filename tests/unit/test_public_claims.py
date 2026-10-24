"""Tie the last retained live evaluation claim to its committed source."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def public_claim_problems(readme: str, last_live: dict, root: Path) -> list[str]:
    problems = []
    if "semantic-eval.yml/badge.svg" in readme:
        problems.append("A successful skipped workflow must not be a semantic pass badge")
    if f"last retained live evaluation {last_live.get('date')}" not in readme:
        problems.append("README live date differs from the evidence metadata")
    path = root / last_live.get("evidencePath", "missing")
    if not path.is_file():
        problems.append("Live evidence path does not exist")
    return problems


def test_readme_live_claim_matches_retained_evidence() -> None:
    metadata = json.loads((ROOT / "docs/evidence/tier2-last-live.json").read_text())
    assert public_claim_problems((ROOT / "README.md").read_text(), metadata, ROOT) == []
    path = ROOT / metadata["evidencePath"]
    if path.suffix == ".json":
        record = json.loads(path.read_text())
        if record.get("schemaVersion") == 3:
            assert record["execution"]["disposition"] == "passed"
            assert record["execution"]["completedAt"][:10] == metadata["date"]
    else:
        assert metadata["date"] in path.read_text()
        assert metadata["model"] in path.read_text()


def test_badge_missing_evidence_and_date_mismatch_fail(tmp_path: Path) -> None:
    metadata = {"date": "2026-07-02", "evidencePath": "report.md"}
    (tmp_path / "report.md").write_text("retained fixture")
    readme = "last retained live evaluation 2026-07-02"
    assert public_claim_problems(readme, metadata, tmp_path) == []
    assert public_claim_problems(readme + "semantic-eval.yml/badge.svg", metadata, tmp_path)
    assert public_claim_problems("last retained live evaluation 2026-07-03", metadata, tmp_path)
    assert public_claim_problems(readme, {**metadata, "evidencePath": "missing"}, tmp_path)
