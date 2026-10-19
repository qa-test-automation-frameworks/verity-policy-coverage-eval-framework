"""Regression tests for the Tier-1 image package metadata gate."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from scripts import check_runtime_package_versions


def _distribution(name: str, version: str) -> SimpleNamespace:
    return SimpleNamespace(metadata={"Name": name}, version=version)


def test_fixed_unique_runtime_versions_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        check_runtime_package_versions,
        "distributions",
        lambda: [
            _distribution("msgpack", "1.2.1"),
            _distribution("setuptools", "83.0.0"),
            _distribution("urllib3", "2.8.0"),
        ],
    )

    check_runtime_package_versions.main()


@pytest.mark.parametrize(
    "distributions",
    [
        [
            _distribution("msgpack", "1.1.2"),
            _distribution("setuptools", "83.0.0"),
            _distribution("urllib3", "2.8.0"),
        ],
        [
            _distribution("msgpack", "1.2.1"),
            _distribution("setuptools", "83.0.0"),
            _distribution("urllib3", "2.8.0"),
            _distribution("urllib3", "2.7.0"),
        ],
    ],
    ids=["vulnerable-version", "duplicate-stale-metadata"],
)
def test_vulnerable_or_duplicate_metadata_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    distributions: list[SimpleNamespace],
) -> None:
    monkeypatch.setattr(check_runtime_package_versions, "distributions", lambda: distributions)

    with pytest.raises(SystemExit, match="Vulnerable or duplicate runtime package metadata"):
        check_runtime_package_versions.main()
