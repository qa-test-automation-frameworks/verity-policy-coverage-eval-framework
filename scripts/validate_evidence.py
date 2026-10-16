"""Validate evidence v3 schema and semantic invariants for this repository."""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "portfolio/evidence/evidence-v3.schema.json"
POLICY_PATH = ROOT / "portfolio/evidence/freshness-policies.json"
PINNED_HASHES = {
    "evidence-v3.schema.json": "40502a47e825755d216e35ea19716ad7de69e47accd6aed1cfb3607160e4d1b9",
    "freshness-policies.json": "1313329c1c06bd3a056dd1ed7d25c631036cae58480fdc4e767f22a0a01a568e",
}


def read_contract(path: Path) -> bytes:
    data = path.read_bytes()
    expected = PINNED_HASHES[path.name]
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        raise RuntimeError(f"Pinned portfolio contract hash mismatch in {path}")
    return data


SCHEMA = json.loads(read_contract(SCHEMA_PATH))
POLICIES = json.loads(read_contract(POLICY_PATH))["policies"]
FORMAT_CHECKER = FormatChecker()


@FORMAT_CHECKER.checks("https-url")
def is_https_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlsplit(value)
    return parsed.scheme == "https" and bool(parsed.netloc)


SCHEMA_VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FORMAT_CHECKER)


def semantic_errors(record: dict[str, Any]) -> list[str]:
    if record.get("kind") == "historical_attestation":
        return []
    execution = record["execution"]
    publication = record["publication"]
    counts = execution["counts"]
    errors: list[str] = []

    def fail(message: str) -> None:
        errors.append(f"semantic: {message}")

    run_id = record["workflow"]["runId"]
    if record["workflow"]["url"] != (
        f"https://github.com/{record['repository']}/actions/runs/{run_id}"
    ):
        fail("workflow URL must identify this repository and immutable run ID")
    if record["scope"]["freshnessPolicy"] not in POLICIES:
        fail("unknown freshness policy")
    if execution["disposition"] != "passed" and not (execution["reason"] or "").strip():
        fail("non-passing execution requires a reason")
    if (
        execution["disposition"] in {"passed", "failed", "cancelled"}
        and not execution["completedAt"]
    ):
        fail("terminal execution requires completedAt")
    if (
        execution["disposition"] in {"passed", "failed", "in_progress", "cancelled"}
        and not execution["startedAt"]
    ):
        fail("attempted execution requires startedAt")
    if execution["disposition"] == "in_progress" and execution["completedAt"] is not None:
        fail("in-progress execution cannot be completed")
    if execution["startedAt"] and execution["completedAt"]:
        started = datetime.fromisoformat(execution["startedAt"].replace("Z", "+00:00"))
        completed = datetime.fromisoformat(execution["completedAt"].replace("Z", "+00:00"))
        if completed < started:
            fail("completion precedes start")

    expected = set(execution["shards"]["expected"])
    received_list = execution["shards"]["received"]
    received = set(received_list)
    if len(received) != len(received_list):
        fail("duplicate shard received")
    if any(shard not in expected for shard in received):
        fail("unexpected shard")
    all_shards = len(received) == len(expected) and received == expected
    if execution["integrity"] == "complete" and not all_shards:
        fail("complete integrity requires every expected shard")

    if counts["unit"] == "not_applicable" and any(
        counts[key] is not None
        for key in ("selected", "executed", "passed", "failed", "skipped", "retried")
    ):
        fail("non-test scope must not invent test counts")
    if (
        counts["passed"] is not None
        and counts["failed"] is not None
        and counts["executed"] is not None
    ) and counts["passed"] + counts["failed"] > counts["executed"]:
        fail("final outcomes exceed execution count")
    if (
        counts["selected"] is not None
        and counts["executed"] is not None
        and counts["skipped"] is not None
    ) and counts["executed"] + counts["skipped"] > counts["selected"]:
        fail("execution plus skips exceed selected count")
    if (
        counts["retried"] is not None
        and counts["executed"] is not None
        and counts["retried"] > counts["executed"]
    ):
        fail("retried unique cases exceed executed unique cases")
    if execution["disposition"] in {"skipped", "unavailable"} and (
        any(
            counts[key] is not None and counts[key] > 0
            for key in ("executed", "passed", "failed", "retried")
        )
        or execution["measurements"]
    ):
        fail("non-execution disposition cannot claim substantive execution")
    if execution["integrity"] == "empty" and (
        (counts["executed"] or 0) > 0 or execution["measurements"]
    ):
        fail("empty evidence cannot contain substantive execution")
    if execution["disposition"] == "passed":
        if execution["integrity"] != "complete" or not all_shards:
            fail("pass requires complete evidence and all expected shards")
        if not ((counts["executed"] or 0) > 0 or execution["measurements"]):
            fail("pass requires substantive native execution")
        if (counts["failed"] or 0) > 0:
            fail("pass cannot contain failed final cases")
        if (
            counts["executed"] is not None
            and counts["passed"] is not None
            and counts["failed"] is not None
        ) and counts["executed"] != counts["passed"] + counts["failed"]:
            fail("pass must reconcile final case outcomes")
        if (
            counts["selected"] is not None
            and counts["executed"] is not None
            and counts["skipped"] is not None
        ) and counts["selected"] != counts["executed"] + counts["skipped"]:
            fail("pass must reconcile selected cases")
    if len({item["name"] for item in execution["measurements"]}) != len(execution["measurements"]):
        fail("duplicate measurement identity")
    artifacts = publication["artifacts"]
    if len({item["name"] for item in artifacts}) != len(artifacts):
        fail("duplicate artifact identity")
    for artifact in artifacts:
        retention = artifact["retention"]
        if retention["class"] == "ephemeral" and not retention["expiresAt"]:
            fail("ephemeral artifact requires expiry")
        if retention["class"] == "durable" and retention["expiresAt"] is not None:
            fail("durable artifact must use its policy rather than ephemeral expiry")
    if publication["disposition"] == "published" and (
        not publication["publishedAt"] or not artifacts
    ):
        fail("published evidence requires time and checksummed artifacts")
    if publication["disposition"] != "published" and (
        publication["publishedAt"] is not None or publication["reportUrl"] is not None
    ):
        fail("unpublished evidence cannot claim current publication time/report")
    if (
        publication["disposition"] in {"failed", "not_applicable"}
        and not (publication["reason"] or "").strip()
    ):
        fail("publication disposition requires a reason")
    if publication["publishedAt"] and execution["completedAt"]:
        published = datetime.fromisoformat(publication["publishedAt"].replace("Z", "+00:00"))
        completed = datetime.fromisoformat(execution["completedAt"].replace("Z", "+00:00"))
        if published < completed:
            fail("publication precedes execution completion")
    return errors


def validate_record(record: dict[str, Any]) -> list[str]:
    errors = [
        f"schema: {error.message} at /{'/'.join(map(str, error.absolute_path))}"
        for error in SCHEMA_VALIDATOR.iter_errors(record)
    ]
    if errors:
        return errors
    return semantic_errors(record)


def main(paths: list[str]) -> int:
    if not paths:
        print("Usage: python scripts/validate_evidence.py <record.json> [...]", file=sys.stderr)
        return 2
    invalid = False
    for value in paths:
        path = Path(value)
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            errors = validate_record(record)
        except (OSError, json.JSONDecodeError, RuntimeError) as error:
            errors = [str(error)]
        if errors:
            invalid = True
            print(f"{path}: invalid")
            for error in errors:
                print(f"  {error}")
        else:
            print(f"{path}: valid")
    return 1 if invalid else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
