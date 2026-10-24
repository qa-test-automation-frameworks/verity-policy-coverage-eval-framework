"""Unit tests for the mutation gate checker."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.check_mutation_results import main

STATS = {
    "killed": 3,
    "survived": 0,
    "total": 3,
    "no_tests": 0,
    "skipped": 0,
    "suspicious": 0,
    "timeout": 0,
    "check_was_interrupted_by_user": 0,
    "segfault": 0,
}


def run(
    tmp_path: Path,
    stats: dict[str, int],
    results: str,
    allowlist: list[dict[str, str]] | None = None,
) -> int:
    (tmp_path / "stats.json").write_text(json.dumps(stats))
    (tmp_path / "results.txt").write_text(results)
    (tmp_path / "allow.json").write_text(json.dumps(allowlist or []))
    return main(
        [
            "--stats",
            str(tmp_path / "stats.json"),
            "--results",
            str(tmp_path / "results.txt"),
            "--allowlist",
            str(tmp_path / "allow.json"),
            "--today",
            "2026-10-24",
        ]
    )


SURVIVOR = {**STATS, "killed": 2, "survived": 1}
ENTRY = {
    "mutant": "toy.x_add__mutmut_1",
    "status": "survived",
    "reason": "equivalent mutant",
    "reviewedOn": "2026-10-01",
    "expiresOn": "2026-12-01",
}


def test_all_killed_passes(tmp_path: Path) -> None:
    assert run(tmp_path, STATS, "") == 0


def test_survivor_fails_and_is_named(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(tmp_path, SURVIVOR, "    toy.x_add__mutmut_1: survived\n") == 1
    assert "toy.x_add__mutmut_1: survived" in capsys.readouterr().out


def test_interrupted_run_fails(tmp_path: Path) -> None:
    assert run(tmp_path, {**STATS, "check_was_interrupted_by_user": 1}, "") == 1


def test_zero_mutants_fails(tmp_path: Path) -> None:
    assert run(tmp_path, {**STATS, "killed": 0, "total": 0}, "") == 1


def test_unexpired_allowlist_passes_and_prints(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(tmp_path, SURVIVOR, "toy.x_add__mutmut_1: survived\n", [ENTRY]) == 0
    assert "allowlisted: toy.x_add__mutmut_1" in capsys.readouterr().out


def test_expired_allowlist_fails(tmp_path: Path) -> None:
    expired = {**ENTRY, "expiresOn": "2026-10-20"}
    assert run(tmp_path, SURVIVOR, "toy.x_add__mutmut_1: survived\n", [expired]) == 1


def test_stale_allowlist_entry_fails(tmp_path: Path) -> None:
    assert run(tmp_path, STATS, "", [ENTRY]) == 1


def test_count_mismatch_is_a_format_error(tmp_path: Path) -> None:
    assert run(tmp_path, SURVIVOR, "") == 2


def test_unknown_status_is_a_format_error(tmp_path: Path) -> None:
    assert run(tmp_path, STATS, "toy.x_add__mutmut_1: exploded\n") == 2


def test_missing_stats_key_is_a_format_error(tmp_path: Path) -> None:
    stats = {key: value for key, value in STATS.items() if key != "segfault"}
    assert run(tmp_path, stats, "") == 2
