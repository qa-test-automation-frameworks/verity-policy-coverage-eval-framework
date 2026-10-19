"""Fail if a dependency exception no longer matches the locked vulnerable package."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

# Keep this allowlist deliberately explicit. When upstream fixes or removes a
# package, this gate forces maintainers to remove the now-stale ignored ID.
EXCEPTION_SCOPE: dict[str, tuple[str, tuple[int, ...] | None, tuple[int, ...]]] = {
    "PYSEC-2026-2447": ("diskcache", None, (5, 6, 3)),
    "PYSEC-2026-3046": ("ragas", (0, 2, 3), (0, 4, 3)),
}
_VERSION_RE = re.compile(r"\d+(?:\.\d+)*")


def _version_tuple(value: str) -> tuple[int, ...]:
    match = _VERSION_RE.match(value)
    if not match or match.group() != value:
        raise ValueError(f"unsupported package version {value!r}")
    return tuple(int(part) for part in value.split("."))


def _read_ids(path: Path) -> set[str]:
    return {
        line.strip()
        for line in path.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def check_exception_scope(ignore_paths: list[Path], lock_path: Path) -> list[str]:
    failures: list[str] = []
    active_ids: set[str] = set()
    for path in ignore_paths:
        if not path.is_file():
            failures.append(f"{path}: required exception file is missing")
            continue
        active_ids.update(_read_ids(path))

    unknown = active_ids - EXCEPTION_SCOPE.keys()
    if unknown:
        failures.append(f"unmapped vulnerability exception IDs: {', '.join(sorted(unknown))}")

    try:
        lock_data = tomllib.loads(lock_path.read_text())
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return [*failures, f"cannot read dependency lock {lock_path}: {exc}"]

    packages: dict[str, list[str]] = {}
    for package in lock_data.get("package", []):
        packages.setdefault(package["name"], []).append(package["version"])

    for vuln_id in sorted(active_ids & EXCEPTION_SCOPE.keys()):
        package_name, lower, upper = EXCEPTION_SCOPE[vuln_id]
        locked_versions = packages.get(package_name, [])
        if not locked_versions:
            failures.append(
                f"{vuln_id}: {package_name} is absent from {lock_path}; remove the exception"
            )
            continue
        vulnerable_versions = []
        for raw_version in locked_versions:
            try:
                version = _version_tuple(raw_version)
            except ValueError as exc:
                failures.append(f"{vuln_id}: {exc}")
                continue
            if (lower is None or version >= lower) and version <= upper:
                vulnerable_versions.append(raw_version)
        if not vulnerable_versions:
            failures.append(
                f"{vuln_id}: locked {package_name} versions {locked_versions} are outside "
                "the reviewed affected range; remove or re-review this exception"
            )
    return failures


def main() -> None:
    failures = check_exception_scope(
        [Path(".pip-audit-ignore"), Path(".trivyignore")], Path("uv.lock")
    )
    if failures:
        print("Vulnerability exception scope check FAILED:")
        for failure in failures:
            print(f"  - {failure}")
        raise SystemExit(1)
    print("Every active vulnerability exception matches an affected locked package.")


if __name__ == "__main__":
    main()
