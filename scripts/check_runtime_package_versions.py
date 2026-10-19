"""Fail if fixed runtime dependencies are missing, vulnerable, or duplicated."""

from __future__ import annotations

from importlib.metadata import distributions

MINIMUM_VERSIONS = {
    "msgpack": (1, 2, 1),
    "setuptools": (78, 1, 1),
    "urllib3": (2, 8, 0),
}


def main() -> None:
    installed: dict[str, list[tuple[int, ...]]] = {}
    for distribution in distributions():
        name = distribution.metadata.get("Name", "").lower().replace("_", "-")
        if name in MINIMUM_VERSIONS:
            version = tuple(int(part) for part in distribution.version.split("."))
            installed.setdefault(name, []).append(version)

    invalid = {
        name: versions
        for name, minimum in MINIMUM_VERSIONS.items()
        if len(versions := installed.get(name, [])) != 1 or versions[0] < minimum
    }
    if invalid:
        raise SystemExit(f"Vulnerable or duplicate runtime package metadata: {invalid}")

    print(f"Verified unique fixed package metadata: {installed}")


if __name__ == "__main__":
    main()
