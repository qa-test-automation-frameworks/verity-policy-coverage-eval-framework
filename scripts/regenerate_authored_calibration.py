"""Regenerate authored fixture identity, keys, usage, and the source mapping."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from scripts.run_calibration import _cassette_key_for_case, run_author_mode
from verity.calibration import load_calibration
from verity.config import Settings


def main() -> None:
    directory = Path("datasets/calibration/cassettes/authored-score-v2")
    manifest_path = directory.with_name("authored-score-v2-manifest.json")
    manifest = json.loads(manifest_path.read_text())
    cases = load_calibration(Path("datasets/calibration/labeled.yaml"))
    by_id = {case.id: case for case in cases}
    for path in directory.glob("*.json"):
        path.unlink()
    run_author_mode(cases, Settings(_env_file=None))
    for entry in manifest["cassettes"]:
        source = Path(entry["source_v1"])
        payload = json.loads(source.read_text())
        match = re.search(r"calib-[a-z-]+-[0-9]{3}", payload["_request_preview"])
        if match is None:
            raise ValueError(f"Missing source case identity: {source}")
        case = by_id[match.group()]
        target = directory / f"{_cassette_key_for_case(case, 'authored-fixture')}.json"
        entry["source_v1_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
        entry["target_v2"] = target.as_posix()
        entry["target_v2_sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
    manifest["cassetteCount"] = len(list(directory.glob("*.json")))
    manifest["migration"] = (
        "Authored fixture identity and zero provider usage; provider aliases deduplicated; "
        "all frozen integer scores and archived source bytes retained"
    )
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"Regenerated {manifest['cassetteCount']} authored fixtures from 112 archived sources")


if __name__ == "__main__":
    main()
