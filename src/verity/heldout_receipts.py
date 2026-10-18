"""Reconcile bounded D05 held-out runner receipts into scores and an index."""

from __future__ import annotations

import csv
import json
import math
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from verity.calibration import load_heldout_calibration
from verity.heldout_analysis import PLAN_ID, sha256_file


def reconcile_receipts(
    dataset_path: Path, receipt_dir: Path
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build a score table only when every case has exactly one valid success.

    Failed attempts remain in the receipt index. A failed attempt may be followed
    by a separately logged continuation, but duplicate successful scores are
    rejected to prevent rerun selection bias.
    """
    cases = load_heldout_calibration(dataset_path)
    dataset_hash = sha256_file(dataset_path)
    ordered_ids = [case.randomized_case_id for case in cases]
    case_metrics = {case.randomized_case_id: case.metric for case in cases}
    receipts = sorted(receipt_dir.glob("heldout-*.json"))
    if not receipts:
        raise ValueError(f"no heldout-*.json receipts found in {receipt_dir}")

    scores: dict[str, float] = {}
    attempts_by_case: Counter[str] = Counter()
    receipt_index: list[dict[str, Any]] = []
    unexpected_ids: set[str] = set()
    duplicate_successes: set[str] = set()

    for path in receipts:
        try:
            receipt = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}: invalid receipt JSON") from exc
        if not isinstance(receipt, dict):
            raise ValueError(f"{path}: receipt root must be a JSON object")
        if receipt.get("study_plan_id") != PLAN_ID:
            raise ValueError(f"{path}: receipt is not for {PLAN_ID}")
        purpose = receipt.get("purpose")
        if not isinstance(purpose, str) or not purpose.startswith("bounded live D05 held-out"):
            raise ValueError(f"{path}: receipt purpose is not held-out scoring")
        if receipt.get("dataset_sha256") != dataset_hash:
            raise ValueError(f"{path}: receipt dataset hash does not match frozen dataset")
        if receipt.get("requested_model") != "gemini-3.8-flash":
            raise ValueError(f"{path}: receipt model does not match the frozen model")
        if receipt.get("free_project_confirmed_by_operator") is not True:
            raise ValueError(f"{path}: missing free-project attestation")
        if receipt.get("billing_plan_verified_by_api") is not False:
            raise ValueError(f"{path}: unexpected billing-plan verification claim")
        limits = receipt.get("limits")
        if (
            not isinstance(limits, dict)
            or limits.get("spend_usd") != 0
            or limits.get("calls") != 7
            or limits.get("output_tokens_per_call") != 2048
            or limits.get("output_tokens_per_run") != 14336
            or limits.get("input_bytes_per_call") != 16000
            or limits.get("interval_seconds", 0) < 3.1
            or limits.get("retries") != 0
        ):
            raise ValueError(f"{path}: frozen zero-spend request bounds are absent")
        attempts = receipt.get("attempts")
        if not isinstance(attempts, list):
            raise ValueError(f"{path}: attempts must be a list")
        generation_config = receipt.get("generation_config")
        has_success = any(
            isinstance(attempt, dict) and attempt.get("status") == "success" for attempt in attempts
        )
        if has_success and generation_config != {
            "temperature": 1.0,
            "reasoning_effort": "low",
        }:
            raise ValueError(f"{path}: successful score used an unfrozen generation configuration")
        if len(attempts) > 7 or receipt.get("status") not in {"success", "failed"}:
            raise ValueError(f"{path}: invalid run status or more than seven attempts")
        selected_ids = receipt.get("selected_case_ids")
        if not isinstance(selected_ids, list) or len(selected_ids) > 7:
            raise ValueError(f"{path}: selected_case_ids exceed the seven-call batch limit")
        if any(not isinstance(case_id, str) for case_id in selected_ids):
            raise ValueError(f"{path}: selected_case_ids must be strings")
        selected_set = set(selected_ids)
        if len(selected_set) != len(selected_ids):
            raise ValueError(f"{path}: selected_case_ids must be unique")
        start_index = receipt.get("start_index")
        if (
            not isinstance(start_index, int)
            or isinstance(start_index, bool)
            or not 0 <= start_index < len(ordered_ids)
            or selected_ids != ordered_ids[start_index : start_index + 7]
        ):
            raise ValueError(f"{path}: selected IDs do not match the frozen contiguous batch")
        unexpected_ids.update(selected_set - set(case_metrics))
        record_attempts: list[dict[str, Any]] = []
        for attempt in attempts:
            if not isinstance(attempt, dict):
                raise ValueError(f"{path}: each attempt must be an object")
            case_id = attempt.get("case_id")
            if not isinstance(case_id, str) or case_id not in selected_set:
                raise ValueError(f"{path}: attempt case ID is missing or not selected")
            if case_id not in case_metrics:
                unexpected_ids.add(case_id)
                continue
            attempts_by_case[case_id] += 1
            status = attempt.get("status")
            score: float | None = None
            if status == "success":
                value = attempt.get("score")
                if not isinstance(value, (float, int)) or isinstance(value, bool):
                    raise ValueError(f"{path}: successful attempt lacks a numeric score")
                score = float(value)
                if not math.isfinite(score) or not 0.0 <= score <= 1.0:
                    raise ValueError(f"{path}: score must be finite and between 0 and 1")
                reported_cost = attempt.get("provider_reported_cost_usd")
                if reported_cost is not None and float(reported_cost) != 0.0:
                    raise ValueError(f"{path}: successful attempt reports nonzero provider cost")
                if case_id in scores:
                    duplicate_successes.add(case_id)
                else:
                    scores[case_id] = score
            elif status not in {"failed", "started"}:
                raise ValueError(f"{path}: attempt has unexpected status {status!r}")
            record_attempts.append(
                {"randomized_case_id": case_id, "status": status, "score": score}
            )
        receipt_index.append(
            {
                "file": path.name,
                "sha256": sha256_file(path),
                "run_status": receipt.get("status"),
                "generation_config": generation_config,
                "started_at": receipt.get("started_at"),
                "finished_at": receipt.get("ended_at"),
                "source_sha": receipt.get("source_sha"),
                "unattempted_selected_case_ids": sorted(
                    selected_set - {item["randomized_case_id"] for item in record_attempts}
                ),
                "attempts": record_attempts,
            }
        )

    missing_ids = sorted(set(case_metrics) - set(scores))
    index = {
        "schema_version": 1,
        "plan_id": PLAN_ID,
        "dataset_sha256": dataset_hash,
        "case_count": len(case_metrics),
        "successful_case_count": len(scores),
        "missing_case_ids": missing_ids,
        "unexpected_case_ids": sorted(unexpected_ids),
        "duplicate_success_case_ids": sorted(duplicate_successes),
        "attempt_counts_by_case": dict(sorted(attempts_by_case.items())),
        "status": "complete"
        if not missing_ids and not unexpected_ids and not duplicate_successes
        else "incomplete",
        "receipt_count": len(receipt_index),
        "receipts": receipt_index,
        "generated_at_utc": datetime.now(UTC).isoformat(),
    }
    rows = [
        {
            "randomized_case_id": case_id,
            "metric": case_metrics[case_id],
            "judge_score": scores[case_id],
        }
        for case_id in case_metrics
        if case_id in scores
    ]
    return rows, index


def write_reconciled_outputs(
    dataset_path: Path,
    receipt_dir: Path,
    score_path: Path,
    index_path: Path,
) -> dict[str, Any]:
    """Write a non-overwritable receipt index and, only when complete, score CSV."""
    if score_path.exists() or index_path.exists():
        raise FileExistsError("refusing to overwrite existing D05 reconciliation outputs")
    rows, index = reconcile_receipts(dataset_path, receipt_dir)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    with index_path.open("x", encoding="utf-8") as stream:
        json.dump(index, stream, indent=2, sort_keys=True)
        stream.write("\n")
    if index["status"] == "complete":
        score_path.parent.mkdir(parents=True, exist_ok=True)
        with score_path.open("x", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=("randomized_case_id", "metric", "judge_score"),
            )
            writer.writeheader()
            writer.writerows(rows)
    return index
