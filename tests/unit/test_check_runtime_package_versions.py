"""Regression tests for the Tier-1 image package metadata gate."""

from __future__ import annotations

import pytest
from scripts import check_runtime_package_versions


def _metadata(site_packages, name: str, version: str, filename: str | None = None) -> None:
    directory = site_packages / (filename or f"{name}-{version}.dist-info")
    directory.mkdir(parents=True)
    (directory / "METADATA").write_text(f"Name: {name}\nVersion: {version}\n", encoding="utf-8")


def test_fixed_unique_runtime_versions_pass(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name, version in (("msgpack", "1.2.1"), ("setuptools", "83.0.0"), ("urllib3", "2.8.0")):
        _metadata(tmp_path, name, version)
    monkeypatch.setattr(
        check_runtime_package_versions.sysconfig,
        "get_path",
        lambda _: str(tmp_path),
    )

    check_runtime_package_versions.main()


def test_vulnerable_nested_metadata_fails_closed(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    _metadata(tmp_path, "msgpack", "1.2.1")
    _metadata(tmp_path, "setuptools", "83.0.0")
    _metadata(tmp_path, "urllib3", "2.7.0", "nested/urllib3-2.7.0.egg-info")
    monkeypatch.setattr(
        check_runtime_package_versions.sysconfig,
        "get_path",
        lambda _: str(tmp_path),
    )

    with pytest.raises(SystemExit, match="Vulnerable or duplicate runtime package metadata"):
        check_runtime_package_versions.main()


def test_duplicate_nested_metadata_fails_closed(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    _metadata(tmp_path, "msgpack", "1.2.1")
    _metadata(tmp_path, "setuptools", "83.0.0")
    _metadata(tmp_path, "urllib3", "2.8.0")
    _metadata(tmp_path, "urllib3", "2.7.0", "nested/urllib3-2.7.0.dist-info")
    monkeypatch.setattr(
        check_runtime_package_versions.sysconfig,
        "get_path",
        lambda _: str(tmp_path),
    )

    with pytest.raises(SystemExit, match="Vulnerable or duplicate runtime package metadata"):
        check_runtime_package_versions.main()
