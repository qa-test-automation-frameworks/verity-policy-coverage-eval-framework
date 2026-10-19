"""Unit tests for mapping ignored IDs to reviewed locked package ranges."""

from __future__ import annotations

import tomllib
from pathlib import Path

from scripts.check_vuln_exception_scope import check_exception_scope


def _fixture(
    tmp_path: Path, *, diskcache: str | None = "5.6.3", ragas: str | None = "0.4.3"
) -> tuple[list[Path], Path]:
    ignore = tmp_path / ".pip-audit-ignore"
    ignore.write_text("PYSEC-2026-2447\nPYSEC-2026-3046\n")
    trivy = tmp_path / ".trivyignore"
    trivy.write_text("# no active suppressions\n")
    packages = []
    for name, version in (("diskcache", diskcache), ("ragas", ragas)):
        if version:
            packages.append(f'[[package]]\nname = "{name}"\nversion = "{version}"\n')
    lock = tmp_path / "uv.lock"
    lock.write_text("\n".join(packages))
    # Keep fixture syntax valid so failures test scope logic, not TOML parsing.
    tomllib.loads(lock.read_text())
    return [ignore, trivy], lock


def test_active_exceptions_match_reviewed_affected_versions(tmp_path: Path) -> None:
    ignore_paths, lock = _fixture(tmp_path)
    assert check_exception_scope(ignore_paths, lock) == []


def test_exception_fails_after_dependency_is_upgraded(tmp_path: Path) -> None:
    ignore_paths, lock = _fixture(tmp_path, diskcache="5.6.4")
    failures = check_exception_scope(ignore_paths, lock)
    assert any("PYSEC-2026-2447" in failure and "outside" in failure for failure in failures)


def test_exception_fails_after_dependency_is_removed(tmp_path: Path) -> None:
    ignore_paths, lock = _fixture(tmp_path, ragas=None)
    failures = check_exception_scope(ignore_paths, lock)
    assert any("PYSEC-2026-3046" in failure and "absent" in failure for failure in failures)


def test_unmapped_exception_id_fails_closed(tmp_path: Path) -> None:
    ignore_paths, lock = _fixture(tmp_path)
    ignore_paths[0].write_text("CVE-2099-0001\n")
    failures = check_exception_scope(ignore_paths, lock)
    assert any("unmapped" in failure for failure in failures)
