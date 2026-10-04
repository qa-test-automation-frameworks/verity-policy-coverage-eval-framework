"""Behavioral probes for dated quarantine ownership and exact test references."""

from datetime import date
from pathlib import Path

import pytest
import yaml
from scripts.check_quarantine_policy import check_quarantine_policy

TODAY = date(2026, 10, 4)


def _fixture(tmp_path: Path) -> tuple[Path, dict]:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/known-issues.md").write_text("KI-3: controls remain unproven")
    (tmp_path / "tests/semantic").mkdir(parents=True)
    (tmp_path / "tests/semantic/test_control.py").write_text(
        "import pytest\n@pytest.mark.quarantine\ndef test_control():\n    assert True\n"
    )
    data = {
        "schemaVersion": 1,
        "items": [
            {
                "id": "KI-3",
                "status": "active",
                "ownerRole": "repository-maintainer",
                "reviewedOn": "2026-10-04",
                "reviewDue": "2026-10-18",
                "expires": "2026-11-03",
                "source": "docs/known-issues.md",
                "reason": "Independent live controls unavailable",
                "promotionCriteria": "Reviewed live controls must pass unchanged thresholds",
                "tests": ["tests/semantic/test_control.py::test_control"],
            }
        ],
    }
    return tmp_path / "quarantine.yml", data


def _write(path: Path, data: dict) -> None:
    path.write_text(yaml.safe_dump(data))


def test_current_dated_entry_with_real_marked_test_passes(tmp_path: Path) -> None:
    path, data = _fixture(tmp_path)
    _write(path, data)
    assert check_quarantine_policy(path, tmp_path, TODAY) == []


@pytest.mark.parametrize(
    "field", ["ownerRole", "reason", "promotionCriteria", "reviewDue", "expires"]
)
def test_missing_governance_field_fails(tmp_path: Path, field: str) -> None:
    path, data = _fixture(tmp_path)
    del data["items"][0][field]
    _write(path, data)
    assert check_quarantine_policy(path, tmp_path, TODAY)


@pytest.mark.parametrize(
    "values",
    [
        {"reviewedOn": "2026-09-10", "reviewDue": "2026-09-24", "expires": "2026-10-03"},
        {"reviewedOn": "2026-09-20", "reviewDue": "2026-10-03", "expires": "2026-10-20"},
        {"reviewedOn": "2026-10-05"},
        {"reviewDue": "2026-10-18", "expires": "2026-10-10"},
        {"expires": "2026-02-30"},
        {"reviewDue": "2027-01-01", "expires": "2027-02-01"},
    ],
)
def test_expired_overdue_future_and_unbounded_dates_fail(tmp_path: Path, values: dict) -> None:
    path, data = _fixture(tmp_path)
    data["items"][0].update(values)
    _write(path, data)
    assert check_quarantine_policy(path, tmp_path, TODAY)


@pytest.mark.parametrize(
    "node_id",
    [
        "tests/semantic/test_control.py::test_missing",
        "../escape.py::test_control",
        "tests/missing.py::test_control",
    ],
)
def test_invalid_exact_test_reference_fails(tmp_path: Path, node_id: str) -> None:
    path, data = _fixture(tmp_path)
    data["items"][0]["tests"] = [node_id]
    _write(path, data)
    assert check_quarantine_policy(path, tmp_path, TODAY)


def test_duplicate_quarantine_id_fails(tmp_path: Path) -> None:
    path, data = _fixture(tmp_path)
    data["items"].append(dict(data["items"][0]))
    _write(path, data)
    assert "Quarantine ID is missing or duplicated" in check_quarantine_policy(
        path, tmp_path, TODAY
    )


def test_removing_marker_requires_manifest_reconciliation(tmp_path: Path) -> None:
    path, data = _fixture(tmp_path)
    (tmp_path / "tests/semantic/test_control.py").write_text(
        "def test_control():\n    assert True\n"
    )
    _write(path, data)
    assert any(
        "no quarantine marker" in message
        for message in check_quarantine_policy(path, tmp_path, TODAY)
    )


def test_invalid_yaml_is_failure(tmp_path: Path) -> None:
    path, _ = _fixture(tmp_path)
    path.write_text("items: [")
    assert check_quarantine_policy(path, tmp_path, TODAY)


def test_deleting_manifest_entry_does_not_hide_an_active_marker(tmp_path: Path) -> None:
    path, data = _fixture(tmp_path)
    data["items"] = []
    _write(path, data)
    assert any(
        "Untracked quarantine marker" in message
        for message in check_quarantine_policy(path, tmp_path, TODAY)
    )


def test_arbitrary_source_doc_cannot_replace_the_known_issue_record(tmp_path: Path) -> None:
    path, data = _fixture(tmp_path)
    (tmp_path / "docs/other.md").write_text("KI-3")
    data["items"][0]["source"] = "docs/other.md"
    _write(path, data)
    assert check_quarantine_policy(path, tmp_path, TODAY)
