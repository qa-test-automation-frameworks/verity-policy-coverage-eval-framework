"""Regenerate authored fixture identity, keys, usage, and the source mapping."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path

from scripts.check_current_evidence import ROOT, update_summary
from scripts.run_calibration import _cassette_key_for_case, run_author_mode

from verity.calibration import load_calibration
from verity.config import Settings


def refresh_inventory() -> None:
    """Refresh only current synthetic metadata from the report and CI source."""
    source_sha = os.environ.get("GITHUB_SHA", "")
    if not re.fullmatch(r"[a-f0-9]{40}", source_sha):
        raise ValueError("Inventory regeneration requires the real GitHub CI source SHA")
    path = Path("portfolio/current-evidence.json")
    inventory = json.loads(path.read_text())
    synthetic = inventory["evaluationModes"]["synthetic-replay"]
    report = Path(synthetic["report"]["path"])
    report_date = re.search(r"\*\*Generated:\*\* (\d{4}-\d{2}-\d{2})", report.read_text())
    if report_date is None:
        raise ValueError("Generated report date is missing")
    synthetic["report"]["sha256"] = hashlib.sha256(report.read_bytes()).hexdigest()
    synthetic["report"]["date"] = report_date.group(1)
    synthetic["model"]["reason"] = "Authored fixtures identify no measured live model."
    synthetic["limitations"][-1] = "The authored-fixture identity claims no provider execution."
    synthetic["summary"] = (
        f"Calculation self-test regenerated on {report_date.group(1)} from 56 authored cases; "
        "all frozen scores and figures are retained, with explicit fixture identity and "
        "zero provider token usage. This is not live or runtime-adapter calibration."
    )
    inventory["generatedFrom"]["sourceSha"] = source_sha
    path.write_text(json.dumps(inventory, indent=2) + "\n")
    update_summary(ROOT, inventory, write=True)
    print(f"Regenerated current synthetic inventory from CI source {source_sha}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh-inventory", action="store_true")
    if parser.parse_args().refresh_inventory:
        refresh_inventory()
        return
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
