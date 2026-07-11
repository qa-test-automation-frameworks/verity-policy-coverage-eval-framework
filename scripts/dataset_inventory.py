"""Emit one generated source of truth for dataset and corpus counts."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASE_ID = re.compile(r"^\s*- id:\s*\S+", re.MULTILINE)


def count_cases(directory: Path) -> int:
    return sum(len(CASE_ID.findall(path.read_text(encoding="utf-8"))) for path in sorted(directory.glob("*.yaml")))


def corpus_fingerprint(directory: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(directory.glob("*.md")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def inventory(root: Path = ROOT) -> dict[str, object]:
    return {
        "golden_cases": count_cases(root / "datasets" / "golden"),
        "calibration_cases": count_cases(root / "datasets" / "calibration"),
        "corpus_fingerprint": corpus_fingerprint(root / "src" / "sut" / "corpus"),
    }


if __name__ == "__main__":
    print(json.dumps(inventory(), indent=2, sort_keys=True))
