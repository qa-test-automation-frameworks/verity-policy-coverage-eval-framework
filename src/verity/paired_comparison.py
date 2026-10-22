"""Paired correctness/cost analysis for immutable model-comparison cohorts."""

from __future__ import annotations

import hashlib
import json
import math
import random
import re
from collections.abc import Mapping, Sequence
from typing import Any

from verity.claim_grounding import check_citations
from verity.escalation import check_refusal
from verity.golden import GoldenCase
from verity.temporal_checks import check_temporal_amount
from verity.text_expectations import (
    check_date_expectations,
    check_must_contain,
    check_must_contain_any,
    check_must_not_contain,
    check_numeric_expectations,
)

SCHEMA_VERSION = 1
MINIMUM_CASES = 30
NON_INFERIORITY_MARGIN = -0.02
BOOTSTRAP_RESAMPLES = 2_000
BOOTSTRAP_SEED = 20261021
_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_SOURCE_KINDS = {"authored_control", "replay", "live"}
_MEASUREMENT_STATUSES = {"valid", "invalid"}
_REQUIRED_FIELDS = {
    "schema_version",
    "cohort_hash",
    "case_id",
    "candidate_id",
    "input_hash",
    "oracle_version",
    "correct",
    "critical_failure",
    "measurement_status",
    "input_tokens",
    "output_tokens",
    "cost_usd",
    "latency_ms",
    "source_kind",
    "config_id",
    "source_id",
}


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def golden_input_hash(case: GoldenCase) -> str:
    """Hash the member input sent to both candidates, excluding expected outputs."""
    return _canonical_hash({"query": case.query, "member_id": case.member_id})


def golden_oracle_version(case: GoldenCase) -> str:
    """Identify the exact deterministic expectations used to judge this case."""
    oracle_fields = {
        "behavior": case.behavior,
        "must_contain": case.must_contain,
        "must_contain_any": case.must_contain_any,
        "must_not_contain": case.must_not_contain,
        "numeric_expectations": [
            item.model_dump(mode="json") for item in case.numeric_expectations
        ],
        "date_expectations": [item.model_dump(mode="json") for item in case.date_expectations],
        "temporal_amount": (
            case.temporal_amount.model_dump(mode="json") if case.temporal_amount else None
        ),
        "expected_citations": case.expected_citations,
    }
    return f"golden-deterministic-v1:{_canonical_hash(oracle_fields)}"


def golden_cohort_hash(cases: Sequence[GoldenCase]) -> str:
    """Return the stable identity of the selected case/input/oracle cohort."""
    members = [
        {
            "case_id": case.id,
            "input_hash": golden_input_hash(case),
            "oracle_version": golden_oracle_version(case),
        }
        for case in cases
    ]
    return _canonical_hash(sorted(members, key=lambda row: row["case_id"]))


def evaluate_golden_response(
    case: GoldenCase, response: Any
) -> tuple[bool | None, bool, list[str]]:
    """Apply only authored deterministic checks; return unknown when none can score correctness."""
    failures: list[str] = []
    unknowns: list[str] = []
    explicit_oracle = False
    critical_failure = False

    refusal = check_refusal(case, response)
    if not refusal.passed:
        failures.append("expected_answer_or_refusal")
    elif case.behavior == "refuse":
        return True, False, []

    if case.must_contain:
        explicit_oracle = True
        if not check_must_contain(case, response).passed:
            failures.append("must_contain")
    if case.must_contain_any:
        explicit_oracle = True
        if not check_must_contain_any(case, response).passed:
            failures.append("must_contain_any")
    if case.must_not_contain:
        explicit_oracle = True
        if not check_must_not_contain(case, response).passed:
            failures.append("must_not_contain")
    if case.numeric_expectations:
        explicit_oracle = True
        if not check_numeric_expectations(case, response).passed:
            failures.append("numeric_expectation")
    if case.date_expectations:
        explicit_oracle = True
        if not check_date_expectations(case, response).passed:
            failures.append("date_expectation")
    if case.expected_citations:
        explicit_oracle = True
        chunks = getattr(response, "retrieved_chunks", [])
        sources = [getattr(chunk, "source", "") for chunk in chunks]
        if not check_citations(case, response, sources, chunks).passed:
            failures.append("expected_citations")
    if case.temporal_amount is not None:
        explicit_oracle = True
        temporal = check_temporal_amount(case.temporal_amount, getattr(response, "answer", None))
        if temporal["status"] == "FAIL":
            failures.append("temporal_amount")
            critical_failure = True
        elif temporal["status"] == "REVIEW":
            unknowns.append("temporal_amount_review")

    if failures:
        return False, critical_failure, failures
    if unknowns:
        return None, critical_failure, unknowns
    if not explicit_oracle:
        return None, False, ["no_deterministic_content_oracle"]
    return True, False, []


def _diagnostic(code: str, message: str, *, side: str = "", case_id: str = "") -> dict[str, str]:
    return {"code": code, "message": message, "side": side, "case_id": case_id}


def _record_errors(record: Mapping[str, Any], side: str, line: int) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []

    def add(code: str, message: str) -> None:
        errors.append(_diagnostic(code, f"line {line}: {message}", side=side))

    for field in sorted(_REQUIRED_FIELDS - record.keys()):
        add("missing_field", f"{field} is required")
    if (
        record.get("schema_version") != SCHEMA_VERSION
        or type(record.get("schema_version")) is not int
    ):
        add("schema_version", "schema_version must equal 1")
    for field in ("case_id", "candidate_id", "oracle_version", "config_id", "source_id"):
        if not isinstance(record.get(field), str) or not record[field].strip():
            add("invalid_identity", f"{field} must be a nonempty string")
    for field in ("cohort_hash", "input_hash"):
        value = record.get(field)
        if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
            add("invalid_hash", f"{field} must be a lowercase SHA-256")
    if not isinstance(record.get("source_kind"), str) or record["source_kind"] not in _SOURCE_KINDS:
        add("source_kind", "source_kind is not supported")
    if (
        not isinstance(record.get("measurement_status"), str)
        or record["measurement_status"] not in _MEASUREMENT_STATUSES
    ):
        add("measurement_status", "measurement_status must be valid or invalid")
    if record.get("correct") is not None and type(record.get("correct")) is not bool:
        add("correct", "correct must be true, false, or null")
    if type(record.get("critical_failure")) is not bool:
        add("critical_failure", "critical_failure must be boolean")
    for field in ("input_tokens", "output_tokens"):
        value = record.get(field)
        if value is not None and (type(value) is not int or value < 0):
            add("invalid_measurement", f"{field} must be null or a nonnegative integer")
    for field in ("cost_usd", "latency_ms"):
        value = record.get(field)
        if value is not None and (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < 0
        ):
            add("invalid_measurement", f"{field} must be null or finite and nonnegative")
    if record.get("measurement_status") == "invalid" and record.get("correct") is not None:
        add("invalid_measurement", "invalid measurements must use correct=null")
    return errors


def _index_records(
    records: Sequence[Mapping[str, Any]], side: str
) -> tuple[dict[str, Mapping[str, Any]], list[dict[str, str]]]:
    indexed: dict[str, Mapping[str, Any]] = {}
    errors: list[dict[str, str]] = []
    for line, record in enumerate(records, start=1):
        if not isinstance(record, Mapping):
            errors.append(
                _diagnostic(
                    "invalid_record",
                    f"line {line} must contain a JSON object",
                    side=side,
                )
            )
            continue
        errors.extend(_record_errors(record, side, line))
        case_id = record.get("case_id")
        if not isinstance(case_id, str) or not case_id.strip():
            continue
        if case_id in indexed:
            errors.append(
                _diagnostic(
                    "duplicate_case_id",
                    "case_id appears more than once",
                    side=side,
                    case_id=case_id,
                )
            )
            continue
        indexed[case_id] = record
    if not indexed:
        errors.append(_diagnostic("empty_input", "no usable case records were supplied", side=side))
    for field in ("candidate_id", "cohort_hash", "source_kind", "config_id", "source_id"):
        values = {
            record.get(field) for record in indexed.values() if isinstance(record.get(field), str)
        }
        if len(values) > 1:
            errors.append(
                _diagnostic("mixed_identity", f"{field} changes within the {side} input", side=side)
            )
    return indexed, errors


def _nearest_rank(values: list[float], percentile: float) -> float:
    index = max(0, math.ceil(percentile * len(values)) - 1)
    return values[index]


def _bootstrap_interval(deltas: list[float]) -> list[float] | None:
    if not deltas:
        return None
    generator = random.Random(BOOTSTRAP_SEED)
    resampled_means = []
    for _ in range(BOOTSTRAP_RESAMPLES):
        sample = [deltas[generator.randrange(len(deltas))] for _ in deltas]
        resampled_means.append(sum(sample) / len(sample))
    resampled_means.sort()
    return [
        _nearest_rank(resampled_means, 0.025),
        _nearest_rank(resampled_means, 0.975),
    ]


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _numeric_delta(
    baseline: Mapping[str, Any], challenger: Mapping[str, Any], field: str
) -> float | None:
    if (
        baseline.get("measurement_status") != "valid"
        or challenger.get("measurement_status") != "valid"
    ):
        return None
    left = baseline.get(field)
    right = challenger.get(field)
    if (
        isinstance(left, bool)
        or isinstance(right, bool)
        or not isinstance(left, (int, float))
        or not isinstance(right, (int, float))
        or not math.isfinite(left)
        or not math.isfinite(right)
        or left < 0
        or right < 0
    ):
        return None
    return float(right) - float(left)


def analyze_paired_comparison(
    baseline_records: Sequence[Mapping[str, Any]],
    challenger_records: Sequence[Mapping[str, Any]],
    *,
    parse_diagnostics: Sequence[Mapping[str, str]] = (),
) -> dict[str, Any]:
    """Validate two JSONL cohorts and compute paired correctness/cost evidence."""
    baseline, baseline_errors = _index_records(baseline_records, "baseline")
    challenger, challenger_errors = _index_records(challenger_records, "challenger")
    diagnostics = [dict(item) for item in parse_diagnostics]
    diagnostics.extend(baseline_errors)
    diagnostics.extend(challenger_errors)
    baseline_candidate_ids = sorted({str(row.get("candidate_id")) for row in baseline.values()})
    challenger_candidate_ids = sorted({str(row.get("candidate_id")) for row in challenger.values()})
    if (
        len(baseline_candidate_ids) == 1
        and len(challenger_candidate_ids) == 1
        and baseline_candidate_ids[0] == challenger_candidate_ids[0]
    ):
        diagnostics.append(
            _diagnostic(
                "candidate_id_collision",
                "baseline and challenger candidate_id values must differ",
            )
        )

    baseline_ids = set(baseline)
    challenger_ids = set(challenger)
    for case_id in sorted(baseline_ids - challenger_ids):
        diagnostics.append(
            _diagnostic(
                "one_sided_case",
                "case is missing from challenger input",
                side="challenger",
                case_id=case_id,
            )
        )
    for case_id in sorted(challenger_ids - baseline_ids):
        diagnostics.append(
            _diagnostic(
                "one_sided_case",
                "case is missing from baseline input",
                side="baseline",
                case_id=case_id,
            )
        )

    common_ids = sorted(baseline_ids & challenger_ids)
    paired_rows: list[dict[str, Any]] = []
    compatible: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []
    for case_id in common_ids:
        left = baseline[case_id]
        right = challenger[case_id]
        mismatches = [
            field
            for field in ("cohort_hash", "input_hash", "oracle_version", "source_kind")
            if left.get(field) != right.get(field)
        ]
        if mismatches:
            for field in mismatches:
                diagnostics.append(
                    _diagnostic(
                        "pair_identity_mismatch",
                        f"baseline and challenger {field} values differ",
                        case_id=case_id,
                    )
                )
        else:
            compatible.append((left, right))
        paired_rows.append(
            {
                "case_id": case_id,
                "compatible": not mismatches,
                "identity_mismatches": mismatches,
                "baseline_correct": left.get("correct"),
                "challenger_correct": right.get("correct"),
                "baseline_status": left.get("measurement_status"),
                "challenger_status": right.get("measurement_status"),
                "baseline_critical_failure": left.get("critical_failure"),
                "challenger_critical_failure": right.get("critical_failure"),
                "baseline_cost_usd": left.get("cost_usd"),
                "challenger_cost_usd": right.get("cost_usd"),
                "baseline_input_tokens": left.get("input_tokens"),
                "challenger_input_tokens": right.get("input_tokens"),
                "baseline_output_tokens": left.get("output_tokens"),
                "challenger_output_tokens": right.get("output_tokens"),
                "baseline_latency_ms": left.get("latency_ms"),
                "challenger_latency_ms": right.get("latency_ms"),
                "baseline_cohort_hash": left.get("cohort_hash"),
                "challenger_cohort_hash": right.get("cohort_hash"),
                "baseline_source_kind": left.get("source_kind"),
                "challenger_source_kind": right.get("source_kind"),
                "cost_delta_usd": _numeric_delta(left, right, "cost_usd")
                if not mismatches
                else None,
                "latency_delta_ms": _numeric_delta(left, right, "latency_ms")
                if not mismatches
                else None,
                "input_hash": left.get("input_hash"),
                "baseline_input_hash": left.get("input_hash"),
                "challenger_input_hash": right.get("input_hash"),
                "oracle_version": left.get("oracle_version"),
                "baseline_oracle_version": left.get("oracle_version"),
                "challenger_oracle_version": right.get("oracle_version"),
            }
        )

    valid_rows = [
        (left, right)
        for left, right in compatible
        if left.get("measurement_status") == right.get("measurement_status") == "valid"
        and type(left.get("correct")) is bool
        and type(right.get("correct")) is bool
    ]
    deltas = [float(right["correct"]) - float(left["correct"]) for left, right in valid_rows]
    wins = sum(delta > 0 for delta in deltas)
    ties = sum(delta == 0 for delta in deltas)
    losses = sum(delta < 0 for delta in deltas)
    interval = _bootstrap_interval(deltas)
    paired_count = len(compatible)
    incomplete_count = paired_count - len(valid_rows)

    cost_pairs = [
        (float(left["cost_usd"]), float(right["cost_usd"]))
        for left, right in compatible
        if left.get("measurement_status") == right.get("measurement_status") == "valid"
        and isinstance(left.get("cost_usd"), (int, float))
        and not isinstance(left.get("cost_usd"), bool)
        and isinstance(right.get("cost_usd"), (int, float))
        and not isinstance(right.get("cost_usd"), bool)
    ]
    latency_pairs = [
        (float(left["latency_ms"]), float(right["latency_ms"]))
        for left, right in compatible
        if left.get("measurement_status") == right.get("measurement_status") == "valid"
        and isinstance(left.get("latency_ms"), (int, float))
        and not isinstance(left.get("latency_ms"), bool)
        and isinstance(right.get("latency_ms"), (int, float))
        and not isinstance(right.get("latency_ms"), bool)
    ]
    input_token_pairs = [
        (int(left["input_tokens"]), int(right["input_tokens"]))
        for left, right in compatible
        if left.get("measurement_status") == right.get("measurement_status") == "valid"
        and type(left.get("input_tokens")) is int
        and type(right.get("input_tokens")) is int
    ]
    output_token_pairs = [
        (int(left["output_tokens"]), int(right["output_tokens"]))
        for left, right in compatible
        if left.get("measurement_status") == right.get("measurement_status") == "valid"
        and type(left.get("output_tokens")) is int
        and type(right.get("output_tokens")) is int
    ]
    baseline_costs = [left for left, _ in cost_pairs]
    challenger_costs = [right for _, right in cost_pairs]
    baseline_cost_mean = _mean(baseline_costs)
    challenger_cost_mean = _mean(challenger_costs)
    cost_delta_mean = _mean([right - left for left, right in cost_pairs])
    source_kinds = {
        str(record.get("source_kind"))
        for record in [*baseline.values(), *challenger.values()]
        if isinstance(record.get("source_kind"), str) and record.get("source_kind") in _SOURCE_KINDS
    }
    source_kind = next(iter(source_kinds)) if len(source_kinds) == 1 else "mixed"
    challenger_critical = any(
        record.get("critical_failure") is True for record in challenger.values()
    )
    input_valid = not diagnostics
    if challenger_critical:
        decision = "reject"
        decision_reason = "The challenger has at least one declared critical failure."
    elif not input_valid or incomplete_count or len(valid_rows) < MINIMUM_CASES:
        decision = "inconclusive"
        decision_reason = (
            "Inputs are invalid or incomplete, or fewer than 30 independent valid pairs "
            "were measured."
        )
    elif interval is None:
        decision = "inconclusive"
        decision_reason = "No valid paired correctness deltas were available."
    elif interval[1] < NON_INFERIORITY_MARGIN:
        decision = "baseline"
        decision_reason = "The 95% paired interval is below the -0.02 non-inferiority margin."
    elif interval[0] < NON_INFERIORITY_MARGIN:
        decision = "inconclusive"
        decision_reason = "The 95% paired interval crosses the -0.02 non-inferiority margin."
    else:
        decision = "candidate"
        decision_reason = "The 95% paired interval supports the predeclared quality-only policy."

    cost_saving_supported = (
        source_kind in {"live", "replay"}
        and bool(cost_pairs)
        and len(cost_pairs) == paired_count
        and input_valid
        and challenger_cost_mean is not None
        and baseline_cost_mean is not None
        and challenger_cost_mean <= baseline_cost_mean
    )
    cost_reason = (
        "Every pair has actual measured live/replay cost and challenger mean cost is no higher."
        if cost_saving_supported
        else (
            "Cost savings are unsupported: costs may be missing or synthetic, or the source "
            "is not measured live/replay."
        )
    )
    evidence_scope = (
        "method_demo_only" if source_kind == "authored_control" else "measured_or_mixed_source"
    )
    cohort_hashes = {
        str(record.get("cohort_hash"))
        for record in [*baseline.values(), *challenger.values()]
        if isinstance(record.get("cohort_hash"), str)
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "source_kind": source_kind,
        "evidence_scope": evidence_scope,
        "input_valid": input_valid,
        "identities": {
            "cohort_hash": next(iter(cohort_hashes)) if len(cohort_hashes) == 1 else None,
            "baseline": {
                "candidate_ids": baseline_candidate_ids,
                "config_ids": sorted({str(row.get("config_id")) for row in baseline.values()}),
                "source_ids": sorted({str(row.get("source_id")) for row in baseline.values()}),
            },
            "challenger": {
                "candidate_ids": challenger_candidate_ids,
                "config_ids": sorted({str(row.get("config_id")) for row in challenger.values()}),
                "source_ids": sorted({str(row.get("source_id")) for row in challenger.values()}),
            },
        },
        "denominators": {
            "baseline_records": len(baseline_records),
            "challenger_records": len(challenger_records),
            "common_case_ids": len(common_ids),
            "compatible_pairs": paired_count,
            "valid_correctness_pairs": len(valid_rows),
            "incomplete_pairs": incomplete_count,
        },
        "quality": {
            "baseline_success_rate": _mean([float(left["correct"]) for left, _ in valid_rows]),
            "challenger_success_rate": _mean([float(right["correct"]) for _, right in valid_rows]),
            "wins": wins,
            "ties": ties,
            "losses": losses,
            "paired_mean_delta": _mean(deltas),
            "bootstrap_95_percentile_interval": interval,
            "bootstrap_resamples": BOOTSTRAP_RESAMPLES,
            "bootstrap_seed": BOOTSTRAP_SEED,
            "non_inferiority_margin": NON_INFERIORITY_MARGIN,
        },
        "cost": {
            "paired_cost_count": len(cost_pairs),
            "paired_cost_denominator": paired_count,
            "baseline_mean_usd": baseline_cost_mean,
            "challenger_mean_usd": challenger_cost_mean,
            "challenger_minus_baseline_mean_usd": cost_delta_mean,
            "cost_saving_supported": cost_saving_supported,
            "reason": cost_reason,
        },
        "tokens": {
            "input_token_pairs": len(input_token_pairs),
            "output_token_pairs": len(output_token_pairs),
            "pair_denominator": paired_count,
            "baseline_mean_input_tokens": _mean([float(left) for left, _ in input_token_pairs]),
            "challenger_mean_input_tokens": _mean([float(right) for _, right in input_token_pairs]),
            "baseline_mean_output_tokens": _mean([float(left) for left, _ in output_token_pairs]),
            "challenger_mean_output_tokens": _mean(
                [float(right) for _, right in output_token_pairs]
            ),
        },
        "latency": {
            "paired_latency_count": len(latency_pairs),
            "paired_latency_denominator": paired_count,
            "baseline_mean_ms": _mean([left for left, _ in latency_pairs]),
            "challenger_mean_ms": _mean([right for _, right in latency_pairs]),
            "challenger_minus_baseline_mean_ms": _mean(
                [right - left for left, right in latency_pairs]
            ),
        },
        "decision": decision,
        "decision_reason": decision_reason,
        "decision_policy": {
            "order": [
                "reject challenger on a critical failure",
                "inconclusive on invalid/incomplete pairs or fewer than 30 valid independent cases",
                "baseline if interval upper bound is below -0.02",
                "inconclusive if interval crosses -0.02",
                "candidate if interval lower bound is at least -0.02",
            ],
            "automatic_deployment": False,
        },
        "diagnostics": diagnostics,
        "case_outcomes": paired_rows,
    }
