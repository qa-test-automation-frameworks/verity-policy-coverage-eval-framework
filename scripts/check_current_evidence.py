#!/usr/bin/env python3
"""Validate the versioned evidence inventory and its generated summary."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import posixpath
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from verity.golden import load_golden  # noqa: E402

SCHEMA_VERSION = 1
EVALUATION_MODES = {
    "synthetic-replay",
    "live-rubric",
    "live-runtime-adapter",
}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SUMMARY_START = "<!-- current-evidence:start -->"
SUMMARY_END = "<!-- current-evidence:end -->"


class EvidenceError(ValueError):
    """Raised when the evidence inventory is incomplete or inconsistent."""


def _fail(message: str) -> None:
    raise EvidenceError(message)


def _object(value: Any, where: str, required: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(f"{where} must be an object")
    missing = required - value.keys()
    extra = value.keys() - required
    if missing:
        _fail(f"{where} is missing required fields: {', '.join(sorted(missing))}")
    if extra:
        _fail(f"{where} has unexpected fields: {', '.join(sorted(extra))}")
    return value


def _nonempty(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(f"{where} must be a non-empty string")
    return value


def _relative_path(value: Any, where: str) -> str:
    raw = _nonempty(value, where)
    path = Path(raw)
    if path.is_absolute() or ".." in path.parts:
        _fail(f"{where} must be a repository-relative path without '..'")
    return raw


def _sha256(value: Any, where: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        _fail(f"{where} must be a lowercase SHA-256 digest")
    return value


def _null_reason(value: Any, reason: Any, where: str) -> None:
    if value is None:
        _nonempty(reason, f"{where} null reason")
    else:
        _nonempty(value, where)
        if reason is not None:
            _fail(f"{where} reason must be null when value is present")


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hash_yaml_directory(root: Path, relative: str) -> str:
    directory = root / relative
    files = sorted(directory.glob("*.yaml"))
    if not directory.is_dir() or not files:
        _fail(f"golden dataset directory is missing or empty: {relative}")
    digest = hashlib.sha256()
    for path in files:
        relpath = path.relative_to(root).as_posix()
        digest.update(relpath.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _artifact(root: Path, artifact: Any, where: str) -> str:
    item = _object(artifact, where, {"path", "sha256"})
    relative = _relative_path(item["path"], f"{where}.path")
    expected = _sha256(item["sha256"], f"{where}.sha256")
    path = root / relative
    if not path.is_file():
        _fail(f"{where} does not exist: {relative}")
    actual = _hash_file(path)
    if actual != expected:
        _fail(f"{where} hash mismatch for {relative}: expected {expected}, found {actual}")
    return relative


def _load_yaml(path: Path, where: str) -> Any:
    try:
        import yaml

        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        _fail(f"could not read {where}: {exc}")


def _check_dataset(root: Path, key: str, dataset: Any) -> None:
    item = _object(
        dataset,
        f"datasets.{key}",
        {"path", "version", "versionReason", "count", "sha256", "hashAlgorithm"},
    )
    relative = _relative_path(item["path"], f"datasets.{key}.path")
    _sha256(item["sha256"], f"datasets.{key}.sha256")
    if item["version"] is None:
        _nonempty(item["versionReason"], f"datasets.{key}.versionReason")
    else:
        _nonempty(item["version"], f"datasets.{key}.version")
        if item["versionReason"] is not None:
            _fail(f"datasets.{key}.versionReason must be null when version is present")
    expected_algorithm = "sha256-path-nul-content-nul-v1" if key == "golden" else "sha256-file-v1"
    if item["hashAlgorithm"] != expected_algorithm:
        _fail(f"datasets.{key}.hashAlgorithm must be {expected_algorithm}")
    if not isinstance(item["count"], int) or isinstance(item["count"], bool) or item["count"] < 0:
        _fail(f"datasets.{key}.count must be a nonnegative integer")

    if key == "golden":
        cases = load_golden(root / relative)
        identifiers = [case.id for case in cases]
        if len(identifiers) != len(set(identifiers)):
            _fail("golden dataset contains duplicate case IDs")
        actual_count = len(cases)
        versions = {case.dataset_version for case in cases}
        if len(versions) != 1:
            _fail(f"golden dataset must have one version, found {sorted(versions)}")
        if item["version"] != next(iter(versions)):
            _fail(f"datasets.golden.version mismatch: expected {next(iter(versions))}")
        actual_hash = _hash_yaml_directory(root, relative)
    else:
        _null_reason(item["version"], item["versionReason"], f"datasets.{key}.version")
        path = root / relative
        if not path.is_file():
            _fail(f"dataset file does not exist: {relative}")
        data = _load_yaml(path, relative)
        if not isinstance(data, dict) or not isinstance(data.get("cases"), list):
            _fail(f"dataset {relative} must contain a cases list")
        case_ids = [case.get("id") for case in data["cases"] if isinstance(case, dict)]
        if len(case_ids) != len(data["cases"]) or any(
            not isinstance(value, str) for value in case_ids
        ):
            _fail(f"dataset {relative} contains a case without a string ID")
        if len(case_ids) != len(set(case_ids)):
            _fail(f"dataset {relative} contains duplicate case IDs")
        actual_count = len(case_ids)
        actual_hash = _hash_file(path)

    if actual_count != item["count"]:
        _fail(f"datasets.{key}.count mismatch: expected {item['count']}, found {actual_count}")
    if actual_hash != item["sha256"]:
        _fail(f"datasets.{key}.sha256 mismatch: expected {item['sha256']}, found {actual_hash}")


def _check_value_with_provenance(
    root: Path, value: Any, source: Any, reason: Any, where: str
) -> None:
    if value is None:
        _nonempty(reason, f"{where}.reason")
        if source is not None:
            _fail(f"{where}.source must be null when value is null")
    else:
        _nonempty(value, f"{where}.value")
        source_text = _nonempty(source, f"{where}.source")
        source_path = _relative_path(source_text.split(",", 1)[0], f"{where}.source")
        source_file = root / source_path
        if not source_file.is_file():
            _fail(f"{where}.source does not exist: {source_path}")
        if value not in source_file.read_text(encoding="utf-8"):
            _fail(f"{where}.value is not present in its cited source {source_path}")
        if reason is not None:
            _fail(f"{where}.reason must be null when value is present")


def _check_record(root: Path, mode: str, record: Any, dataset_names: set[str]) -> None:
    item = _object(
        record,
        f"evaluationModes.{mode}",
        {
            "status",
            "run",
            "model",
            "judge",
            "report",
            "dataset",
            "datasetReason",
            "nativeControlArtifacts",
            "nativeControlArtifactsReason",
            "calibrationScope",
            "limitations",
            "summary",
        },
    )
    status = item["status"]
    allowed_statuses = {
        "synthetic-demonstration",
        "historical-measured",
        "measured",
        "incomplete-provenance",
        "not-measured",
    }
    if not isinstance(status, str) or status not in allowed_statuses:
        _fail(f"evaluationModes.{mode}.status has unexpected value {status!r}")
    if mode == "synthetic-replay" and status != "synthetic-demonstration":
        _fail("synthetic-replay must use synthetic-demonstration status")
    if mode != "synthetic-replay" and status == "synthetic-demonstration":
        _fail(f"{mode} cannot use synthetic-demonstration status")

    run = _object(item["run"], f"evaluationModes.{mode}.run", {"id", "reason"})
    _null_reason(run["id"], run["reason"], f"evaluationModes.{mode}.run.id")
    for field in ("model", "judge"):
        value = _object(
            item[field], f"evaluationModes.{mode}.{field}", {"value", "source", "reason"}
        )
        _check_value_with_provenance(
            root,
            value["value"],
            value["source"],
            value["reason"],
            f"evaluationModes.{mode}.{field}",
        )
    if mode != "synthetic-replay" and status in {"historical-measured", "measured"}:
        if run["id"] is None:
            _fail(f"live measurement {mode} requires a run identifier")
        for field in ("model", "judge"):
            if item[field]["value"] is None:
                _fail(f"live measurement {mode} requires {field} identity")

    report = _object(
        item["report"],
        f"evaluationModes.{mode}.report",
        {"path", "pathReason", "sha256", "date", "dateReason"},
    )
    if report["path"] is None:
        _nonempty(report["pathReason"], f"evaluationModes.{mode}.report.pathReason")
        if report["sha256"] is not None:
            _fail(f"evaluationModes.{mode}.report.sha256 must be null without a path")
    else:
        _artifact(
            root,
            {"path": report["path"], "sha256": report["sha256"]},
            f"evaluationModes.{mode}.report",
        )
        if report["pathReason"] is not None:
            _fail(f"evaluationModes.{mode}.report.pathReason must be null with a path")
    if report["date"] is None:
        _nonempty(report["dateReason"], f"evaluationModes.{mode}.report.dateReason")
    else:
        try:
            date.fromisoformat(report["date"])
        except (TypeError, ValueError):
            _fail(f"evaluationModes.{mode}.report.date must be an ISO date or null")
        if report["dateReason"] is not None:
            _fail(f"evaluationModes.{mode}.report.dateReason must be null when date is present")

    dataset = item["dataset"]
    if dataset is None:
        _nonempty(item["datasetReason"], f"evaluationModes.{mode}.datasetReason")
    else:
        if not isinstance(dataset, str) or dataset not in dataset_names:
            _fail(f"evaluationModes.{mode}.dataset references unknown dataset {dataset!r}")
        if item["datasetReason"] is not None:
            _fail(f"evaluationModes.{mode}.datasetReason must be null with a dataset")

    artifacts = item["nativeControlArtifacts"]
    if not isinstance(artifacts, list):
        _fail(f"evaluationModes.{mode}.nativeControlArtifacts must be a list")
    artifact_paths = [
        _artifact(root, artifact, f"evaluationModes.{mode}.nativeControlArtifacts[{index}]")
        for index, artifact in enumerate(artifacts)
    ]
    if len(artifact_paths) != len(set(artifact_paths)):
        _fail(f"evaluationModes.{mode}.nativeControlArtifacts contains duplicate paths")
    if not artifacts:
        _nonempty(
            item["nativeControlArtifactsReason"],
            f"evaluationModes.{mode}.nativeControlArtifactsReason",
        )
    elif item["nativeControlArtifactsReason"] is not None:
        _fail(f"evaluationModes.{mode}.nativeControlArtifactsReason must be null with artifacts")

    _nonempty(item["calibrationScope"], f"evaluationModes.{mode}.calibrationScope")
    if not isinstance(item["limitations"], list) or not item["limitations"]:
        _fail(f"evaluationModes.{mode}.limitations must be a non-empty list")
    for index, limitation in enumerate(item["limitations"]):
        _nonempty(limitation, f"evaluationModes.{mode}.limitations[{index}]")
    _nonempty(item["summary"], f"evaluationModes.{mode}.summary")

    if (
        mode != "synthetic-replay"
        and status in {"historical-measured", "measured"}
        and (report["path"] is None or report["date"] is None)
    ):
        _fail(f"live measurement {mode} requires a dated report")


def _check_required_headers(root: Path, headers: Any) -> None:
    if not isinstance(headers, list) or not headers:
        _fail("requiredEvidenceHeaders must be a non-empty list")
    seen: set[tuple[str, str]] = set()
    for index, entry in enumerate(headers):
        item = _object(entry, f"requiredEvidenceHeaders[{index}]", {"path", "header"})
        path = root / _relative_path(item["path"], f"requiredEvidenceHeaders[{index}].path")
        header = _nonempty(item["header"], f"requiredEvidenceHeaders[{index}].header")
        key = (item["path"], header)
        if key in seen:
            _fail(f"duplicate required evidence header: {key}")
        seen.add(key)
        if not path.is_file() or header not in path.read_text(encoding="utf-8"):
            _fail(f"required evidence header {header!r} missing from {item['path']}")


def validate_manifest(manifest: Any, root: Path = ROOT) -> None:
    """Validate structure, evidence hashes, dataset counts, and polarity."""
    data = _object(
        manifest,
        "manifest",
        {
            "schemaVersion",
            "generatedFrom",
            "datasets",
            "evaluationModes",
            "hallucinationPolarity",
            "requiredEvidenceHeaders",
        },
    )
    if (
        not isinstance(data["schemaVersion"], int)
        or isinstance(data["schemaVersion"], bool)
        or data["schemaVersion"] != SCHEMA_VERSION
    ):
        _fail(f"unsupported schemaVersion {data['schemaVersion']!r}")
    source = _object(data["generatedFrom"], "generatedFrom", {"sourceSha", "sourcePath"})
    if not isinstance(source["sourceSha"], str) or not re.fullmatch(
        r"[0-9a-f]{40}", source["sourceSha"]
    ):
        _fail("generatedFrom.sourceSha must be a full lowercase Git SHA")
    _relative_path(source["sourcePath"], "generatedFrom.sourcePath")
    if not (root / source["sourcePath"]).exists():
        _fail(f"generatedFrom.sourcePath does not exist: {source['sourcePath']}")

    datasets = _object(
        data["datasets"],
        "datasets",
        {"golden", "calibration", "historicalLiveCalibration"},
    )
    for name, dataset in datasets.items():
        _check_dataset(root, name, dataset)

    modes = _object(data["evaluationModes"], "evaluationModes", EVALUATION_MODES)
    for mode in EVALUATION_MODES:
        _check_record(root, mode, modes[mode], set(datasets))

    polarity = _object(
        data["hallucinationPolarity"],
        "hallucinationPolarity",
        {"runtimeMetric", "calibrationMetric"},
    )
    runtime = _object(
        polarity["runtimeMetric"], "hallucinationPolarity.runtimeMetric", {"name", "polarity"}
    )
    calibration = _object(
        polarity["calibrationMetric"],
        "hallucinationPolarity.calibrationMetric",
        {"name", "sourceDatasetLabel", "polarity"},
    )
    if runtime["polarity"] != "lower_is_better":
        _fail("runtime hallucination metric polarity must be lower_is_better")
    if runtime["name"] != "deepeval_hallucination_score":
        _fail("runtime hallucination metric must name the raw DeepEval score")
    if calibration["polarity"] != "higher_is_better":
        _fail("normalized calibration metric polarity must be higher_is_better")
    if calibration["name"] != "hallucination_groundedness":
        _fail("calibration hallucination metric must be named hallucination_groundedness")
    if calibration["sourceDatasetLabel"] != "hallucination":
        _fail("calibration source dataset label must be documented as hallucination")

    _check_required_headers(root, data["requiredEvidenceHeaders"])


def _summary(manifest: dict[str, Any]) -> str:
    golden = manifest["datasets"]["golden"]
    modes = manifest["evaluationModes"]
    synthetic = modes["synthetic-replay"]
    historical = modes["live-rubric"]
    adapter = modes["live-runtime-adapter"]
    source_label = manifest["hallucinationPolarity"]["calibrationMetric"]["sourceDatasetLabel"]

    def link_path(report_path: str) -> str:
        return posixpath.relpath(report_path, "docs")

    def report_reference(record: dict[str, Any]) -> str:
        report = record["report"]
        if report["path"] is None:
            return f"Report unavailable: {report['pathReason']}"
        return f"See [`{report['path']}`]({link_path(report['path'])})."

    lines = [
        "## Current evidence",
        "",
        "The inventory is generated from `portfolio/current-evidence.json`; its source snapshot is "
        f"`{manifest['generatedFrom']['sourceSha']}`.",
        f"The current golden corpus has **{golden['count']} cases** "
        f"(version `{golden['version']}`; hash `{golden['sha256'][:12]}…`).",
        "",
        f"- **Synthetic rubric replay:** {synthetic['summary']}",
        f"  {report_reference(synthetic)}",
        f"- **Historical live rubric:** {historical['summary']}",
        f"  {report_reference(historical)}",
        f"- **Live runtime adapter artifact:** {adapter['summary']}",
        f"  {report_reference(adapter)}",
        "",
        "Hallucination polarity: the raw DeepEval runtime score is `lower_is_better`; "
        "the separately named calibration score `hallucination_groundedness` "
        f"(dataset label `{source_label}`) "
        "is `higher_is_better`.",
    ]
    return "\n".join(lines)


def update_summary(root: Path, manifest: dict[str, Any], *, write: bool) -> None:
    path = root / "docs/capability-status.md"
    contents = path.read_text(encoding="utf-8")
    block = f"{SUMMARY_START}\n{_summary(manifest)}\n{SUMMARY_END}"
    if SUMMARY_START in contents or SUMMARY_END in contents:
        if contents.count(SUMMARY_START) != 1 or contents.count(SUMMARY_END) != 1:
            _fail("capability-status evidence summary markers are unbalanced or duplicated")
        start = contents.index(SUMMARY_START)
        end = contents.index(SUMMARY_END) + len(SUMMARY_END)
        if end < start:
            _fail("capability-status evidence summary markers are out of order")
        current = contents[start:end]
        updated = contents[:start] + block + contents[end:]
        if not write and current != block:
            _fail("docs/capability-status.md evidence summary is stale; run with --write-summary")
    else:
        title_end = contents.find("\n", contents.find("# Capability Status"))
        if title_end < 0:
            _fail("docs/capability-status.md has no '# Capability Status' heading")
        updated = contents[: title_end + 1] + "\n" + block + "\n" + contents[title_end + 1 :]
        if not write:
            _fail(
                "docs/capability-status.md has no generated evidence summary; "
                "run with --write-summary"
            )
    if write:
        path.write_text(updated, encoding="utf-8")


def _reject_constant(value: str) -> None:
    raise EvidenceError(f"JSON contains non-finite number {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail(f"JSON contains duplicate field {key!r}")
        result[key] = value
    return result


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        manifest = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (OSError, json.JSONDecodeError) as exc:
        _fail(f"could not read {path}: {exc}")
    if not isinstance(manifest, dict):
        _fail("manifest root must be an object")

    def reject_non_finite(value: Any, location: str = "manifest") -> None:
        if isinstance(value, float) and not math.isfinite(value):
            _fail(f"{location} contains a non-finite number")
        if isinstance(value, dict):
            for key, child in value.items():
                reject_non_finite(child, f"{location}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                reject_non_finite(child, f"{location}[{index}]")

    reject_non_finite(manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "portfolio/current-evidence.json")
    parser.add_argument(
        "--write-summary",
        action="store_true",
        help="regenerate the marked block in docs/capability-status.md",
    )
    args = parser.parse_args()
    manifest_path = args.manifest.resolve()
    root = manifest_path.parent.parent
    manifest = load_manifest(manifest_path)
    validate_manifest(manifest, root)
    update_summary(root, manifest, write=args.write_summary)
    print(f"Current evidence inventory is valid: {manifest_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except EvidenceError as exc:
        print(f"Current evidence check failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
