"""Fail if fixed runtime dependencies are missing, vulnerable, or duplicated."""

from __future__ import annotations

import sysconfig
from email.parser import Parser
from pathlib import Path

MINIMUM_VERSIONS = {
    "msgpack": (1, 2, 1),
    "setuptools": (78, 1, 1),
    "urllib3": (2, 8, 0),
}


def installed_package_metadata(site_packages: Path) -> dict[str, list[tuple[tuple[int, ...], str]]]:
    """Inspect all package metadata files, including nested metadata Trivy can see."""
    installed: dict[str, list[tuple[tuple[int, ...], str]]] = {}
    metadata_files = [*site_packages.rglob("METADATA"), *site_packages.rglob("PKG-INFO")]
    for metadata_path in metadata_files:
        metadata = Parser().parsestr(metadata_path.read_text(encoding="utf-8", errors="replace"))
        name = (metadata.get("Name") or "").lower().replace("_", "-")
        if name in MINIMUM_VERSIONS:
            version = metadata.get("Version")
            if version is None:
                installed.setdefault(name, []).append(((), str(metadata_path)))
                continue
            numeric_version = tuple(int(part) for part in version.split(".") if part.isdigit())
            installed.setdefault(name, []).append((numeric_version, str(metadata_path)))

    return installed


def main() -> None:
    installed = installed_package_metadata(Path(sysconfig.get_path("purelib")))

    invalid = {
        name: versions
        for name, minimum in MINIMUM_VERSIONS.items()
        if len(versions := installed.get(name, [])) != 1 or versions[0][0] < minimum
    }
    if invalid:
        raise SystemExit(f"Vulnerable or duplicate runtime package metadata: {invalid}")

    print(f"Verified unique fixed package metadata: {installed}")


if __name__ == "__main__":
    main()
