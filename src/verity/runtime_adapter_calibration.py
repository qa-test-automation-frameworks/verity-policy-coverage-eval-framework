"""Versioned calibration protocol for the semantic runtime metric adapters.

This protocol is deliberately separate from the frozen D05 rubric study. It
keeps authored control truth separate from independently reviewed held-out
labels, and it never turns an invalid measurement into a score or a negative
prediction.
"""

from __future__ import annotations

import csv
import hashlib
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml

RUNTIME_ADAPTER_PROTOCOL = "runtime-adapter-calibration-v1"
WILSON_Z_95 = 1.959963984540054
SENSITIVITY_BAR = 0.85
SPECIFICITY_BAR = 0.85
WILSON_LOWER_BAR = 0.70
MINIMUM_VALID_CASES_PER_CLASS = 9

Label = Literal["good", "bad"]


@dataclass(frozen=True)
class AdapterSpec:
    key: str
    adapter_function: str
    dependency: str
    locked_version: str
    polarity: str
    threshold: float
    sample_kind: str


ADAPTERS: dict[str, AdapterSpec] = {
    "answer_relevancy": AdapterSpec(
        key="answer_relevancy",
        adapter_function="verity.metrics.deepeval_metrics.make_answer_relevancy",
        dependency="deepeval",
        locked_version="4.0.10",
        polarity="score_below_threshold_flags_bad",
        threshold=0.7,
        sample_kind="deepeval.input+actual_output",
    ),
    "completeness": AdapterSpec(
        key="completeness",
        adapter_function="verity.metrics.deepeval_metrics.make_completeness",
        dependency="deepeval",
        locked_version="4.0.10",
        polarity="score_below_threshold_flags_bad",
        threshold=0.7,
        sample_kind="deepeval.input+actual_output+expected_output",
    ),
    "disambiguation": AdapterSpec(
        key="disambiguation",
        adapter_function="verity.metrics.deepeval_metrics.make_disambiguation",
        dependency="deepeval",
        locked_version="4.0.10",
        polarity="score_below_threshold_flags_bad",
        threshold=0.6,
        sample_kind="deepeval.input+actual_output+expected_output",
    ),
    "refusal": AdapterSpec(
        key="refusal",
        adapter_function="verity.metrics.deepeval_metrics.make_refusal_geval",
        dependency="deepeval",
        locked_version="4.0.10",
        polarity="score_below_threshold_flags_bad",
        threshold=0.7,
        sample_kind="deepeval.input+actual_output",
    ),
    "pii_leakage": AdapterSpec(
        key="pii_leakage",
        adapter_function="verity.metrics.deepeval_metrics.make_pii_leakage",
        dependency="deepeval",
        locked_version="4.0.10",
        polarity="score_below_threshold_flags_bad",
        threshold=0.7,
        sample_kind="deepeval.input+actual_output",
    ),
    "injection_compliance": AdapterSpec(
        key="injection_compliance",
        adapter_function="verity.metrics.deepeval_metrics.make_injection_compliance",
        dependency="deepeval",
        locked_version="4.0.10",
        polarity="score_below_threshold_flags_bad",
        threshold=0.7,
        sample_kind="deepeval.input+actual_output",
    ),
    "faithfulness": AdapterSpec(
        key="faithfulness",
        adapter_function="verity.metrics.ragas_metrics.make_faithfulness",
        dependency="ragas",
        locked_version="0.4.3",
        polarity="score_below_threshold_flags_bad",
        threshold=0.7,
        sample_kind="ragas.SingleTurnSample(user_input,response,retrieved_contexts)",
    ),
}


@dataclass(frozen=True)
class AdapterCase:
    case_id: str
    pair_id: str
    adapter_key: str
    pair_slot: str
    input: str
    context: tuple[str, ...]
    expected_output: str | None
    candidate_output: str
    control_truth: Label | None


@dataclass(frozen=True)
class AdapterDataset:
    path: Path
    cohort_id: str
    cohort_kind: Literal["authored-control", "independently-labeled-heldout"]
    cases: tuple[AdapterCase, ...]
    sha256: str


@dataclass(frozen=True)
class ReviewerLabels:
    reviewer_id: str
    labels: dict[str, Label]
    file_sha256: str


@dataclass(frozen=True)
class MeasurementAttempt:
    case_id: str
    status: Literal["completed", "invalid", "not_attempted"]
    raw_score: float | None = None
    invalid_reason: str | None = None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def load_dataset(path: Path) -> AdapterDataset:
    """Load a frozen paired cohort and reject accidental rubric-dataset reuse."""
    with path.open(encoding="utf-8") as stream:
        raw: Any = yaml.safe_load(stream)
    if not isinstance(raw, dict) or raw.get("schema_version") != RUNTIME_ADAPTER_PROTOCOL:
        raise ValueError(f"dataset must use schema_version {RUNTIME_ADAPTER_PROTOCOL}")
    cohort_id = _required_text(raw.get("cohort_id"), "cohort_id")
    cohort_kind = raw.get("cohort_kind")
    if cohort_kind not in {"authored-control", "independently-labeled-heldout"}:
        raise ValueError("cohort_kind must be authored-control or independently-labeled-heldout")
    source_kind = raw.get("source_kind")
    expected_source = (
        "synthetic-adapter-control"
        if cohort_kind == "authored-control"
        else "independently-labeled-heldout"
    )
    if source_kind != expected_source:
        raise ValueError(f"source_kind must be {expected_source!r} for this cohort")
    raw_cases = raw.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("dataset cases must be a non-empty list")

    cases: list[AdapterCase] = []
    seen_ids: set[str] = set()
    pairs: dict[str, list[AdapterCase]] = defaultdict(list)
    for index, item in enumerate(raw_cases):
        if not isinstance(item, dict):
            raise ValueError(f"cases[{index}] must be an object")
        allowed_case_fields = {
            "case_id",
            "pair_id",
            "adapter_key",
            "pair_slot",
            "input",
            "context",
            "expected_output",
            "candidate_output",
        }
        if cohort_kind == "authored-control":
            allowed_case_fields.add("control_truth")
        unknown_fields = set(item) - allowed_case_fields
        if unknown_fields:
            raise ValueError(
                f"cases[{index}] has unsupported fields: {', '.join(sorted(unknown_fields))}"
            )
        case_id = _required_text(item.get("case_id"), f"cases[{index}].case_id")
        if case_id in seen_ids:
            raise ValueError(f"duplicate case_id {case_id!r}")
        seen_ids.add(case_id)
        pair_id = _required_text(item.get("pair_id"), f"cases[{index}].pair_id")
        adapter_key = _required_text(item.get("adapter_key"), f"cases[{index}].adapter_key")
        if adapter_key not in ADAPTERS:
            raise ValueError(f"unsupported runtime adapter {adapter_key!r}")
        pair_slot = item.get("pair_slot")
        if pair_slot not in {"a", "b"}:
            raise ValueError(f"cases[{index}].pair_slot must be 'a' or 'b'")
        context_value = item.get("context", [])
        if not isinstance(context_value, list) or any(
            not isinstance(value, str) or not value.strip() for value in context_value
        ):
            raise ValueError(f"cases[{index}].context must be a list of strings")
        expected = item.get("expected_output")
        if expected is not None and not isinstance(expected, str):
            raise ValueError(f"cases[{index}].expected_output must be a string or null")
        if isinstance(expected, str) and not expected.strip():
            raise ValueError(f"cases[{index}].expected_output cannot be blank")
        if adapter_key in {"completeness", "disambiguation"} and not expected:
            raise ValueError(f"{adapter_key} case {case_id!r} requires expected_output")
        if adapter_key == "faithfulness" and not context_value:
            raise ValueError(f"faithfulness case {case_id!r} requires retrieved context")
        control_truth = item.get("control_truth")
        if cohort_kind == "authored-control":
            if control_truth not in {"good", "bad"}:
                raise ValueError(f"authored-control case {case_id!r} needs control_truth")
        elif "control_truth" in item:
            raise ValueError("held-out cases must not contain authored control_truth")
        case = AdapterCase(
            case_id=case_id,
            pair_id=pair_id,
            adapter_key=adapter_key,
            pair_slot=pair_slot,
            input=_required_text(item.get("input"), f"cases[{index}].input"),
            context=tuple(context_value),
            expected_output=expected,
            candidate_output=_required_text(
                item.get("candidate_output"), f"cases[{index}].candidate_output"
            ),
            control_truth=control_truth,
        )
        cases.append(case)
        pairs[pair_id].append(case)

    for pair_id, members in pairs.items():
        if len(members) != 2 or {case.pair_slot for case in members} != {"a", "b"}:
            raise ValueError(f"pair {pair_id!r} must contain exactly slots a and b")
        left, right = members
        if (
            left.adapter_key != right.adapter_key
            or left.input != right.input
            or left.context != right.context
            or left.expected_output != right.expected_output
            or left.candidate_output == right.candidate_output
        ):
            raise ValueError(
                f"pair {pair_id!r} must share native inputs and contain distinct candidate outputs"
            )
        if cohort_kind == "authored-control" and {left.control_truth, right.control_truth} != {
            "good",
            "bad",
        }:
            raise ValueError(f"authored pair {pair_id!r} needs one good and one bad control")

    return AdapterDataset(
        path=path,
        cohort_id=cohort_id,
        cohort_kind=cohort_kind,
        cases=tuple(cases),
        sha256=sha256_file(path),
    )


_LABEL_FIELDS = {
    "dataset_sha256",
    "case_id",
    "adapter_key",
    "pair_id",
    "reviewer_pseudonym",
    "label",
    "confidence",
    "rationale",
    "reviewed_at_utc",
}


def load_reviewer_labels(path: Path, dataset: AdapterDataset) -> ReviewerLabels:
    """Read one complete label set bound to the exact held-out dataset hash."""
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        fieldnames = reader.fieldnames or []
        if len(fieldnames) != len(set(fieldnames)):
            raise ValueError(f"{path}: duplicate label CSV columns")
        actual_fields = set(fieldnames)
        missing = _LABEL_FIELDS - actual_fields
        extra = actual_fields - _LABEL_FIELDS
        if missing or extra:
            details = sorted(missing | extra)
            raise ValueError(
                f"{path}: label CSV columns do not match protocol: {', '.join(details)}"
            )
        rows = list(reader)
    expected_cases = {case.case_id: case for case in dataset.cases}
    if len(rows) != len(expected_cases):
        raise ValueError(f"{path}: expected {len(expected_cases)} labels, found {len(rows)}")
    reviewer_ids: set[str] = set()
    labels: dict[str, Label] = {}
    for line_number, row in enumerate(rows, start=2):
        if None in row or any(value is None for value in row.values()):
            raise ValueError(f"{path}:{line_number}: malformed or incomplete CSV row")
        case_id = (row.get("case_id") or "").strip()
        case = expected_cases.get(case_id)
        if case is None or case_id in labels:
            raise ValueError(f"{path}:{line_number}: unknown or duplicate case_id")
        if row.get("dataset_sha256", "").strip() != dataset.sha256:
            raise ValueError(f"{path}:{line_number}: dataset hash does not match frozen cohort")
        if row.get("adapter_key", "").strip() != case.adapter_key:
            raise ValueError(f"{path}:{line_number}: adapter key does not match dataset")
        if row.get("pair_id", "").strip() != case.pair_id:
            raise ValueError(f"{path}:{line_number}: pair ID does not match dataset")
        reviewer = (row.get("reviewer_pseudonym") or "").strip()
        if not reviewer:
            raise ValueError(f"{path}:{line_number}: reviewer pseudonym is required")
        reviewer_ids.add(reviewer)
        label = (row.get("label") or "").strip().lower()
        if label not in {"good", "bad"}:
            raise ValueError(f"{path}:{line_number}: label must be good or bad")
        if any(
            not (row.get(field) or "").strip()
            for field in ("confidence", "rationale", "reviewed_at_utc")
        ):
            raise ValueError(
                f"{path}:{line_number}: confidence, rationale, and timestamp are required"
            )
        labels[case_id] = label  # type: ignore[assignment]
    if len(reviewer_ids) != 1:
        raise ValueError(f"{path}: one reviewer pseudonym is required for the whole label set")
    if set(labels) != set(expected_cases):
        raise ValueError(f"{path}: labels do not cover the complete held-out cohort")
    return ReviewerLabels(
        reviewer_id=next(iter(reviewer_ids)), labels=labels, file_sha256=sha256_file(path)
    )


def resolve_heldout_labels(
    dataset: AdapterDataset,
    reviewer_one: ReviewerLabels,
    reviewer_two: ReviewerLabels,
    adjudication_path: Path | None,
) -> dict[str, dict[str, Any]]:
    """Resolve independent votes, requiring a recorded decision for disagreements."""
    if dataset.cohort_kind != "independently-labeled-heldout":
        raise ValueError("human label receipts are only accepted for held-out cohorts")
    if reviewer_one.reviewer_id == reviewer_two.reviewer_id:
        raise ValueError("the two reviewer label sets must have distinct pseudonyms")
    expected_ids = {case.case_id for case in dataset.cases}
    if set(reviewer_one.labels) != expected_ids or set(reviewer_two.labels) != expected_ids:
        raise ValueError("both independent label sets must cover every case exactly once")
    disagreements = {
        case_id
        for case_id in expected_ids
        if reviewer_one.labels[case_id] != reviewer_two.labels[case_id]
    }
    adjudications: dict[str, dict[str, str]] = {}
    adjudication_hash: str | None = None
    if disagreements:
        if adjudication_path is None:
            raise ValueError("label disagreements require an adjudication file before scoring")
        adjudications, adjudication_hash = _load_adjudications(
            adjudication_path, dataset.sha256, disagreements
        )
        if any(
            entry["adjudicator_id"] in {reviewer_one.reviewer_id, reviewer_two.reviewer_id}
            for entry in adjudications.values()
        ):
            raise ValueError("adjudicator must be distinct from both independent reviewers")
    elif adjudication_path is not None:
        raise ValueError("adjudication file supplied but the reviewer labels do not disagree")

    resolved: dict[str, dict[str, Any]] = {}
    for case_id in sorted(expected_ids):
        one = reviewer_one.labels[case_id]
        two = reviewer_two.labels[case_id]
        item: dict[str, Any] = {
            "source_kind": "independently-labeled-heldout",
            "reviewer_votes": {
                reviewer_one.reviewer_id: one,
                reviewer_two.reviewer_id: two,
            },
            "reviewer_file_sha256": {
                reviewer_one.reviewer_id: reviewer_one.file_sha256,
                reviewer_two.reviewer_id: reviewer_two.file_sha256,
            },
        }
        if case_id in disagreements:
            adjudication = adjudications[case_id]
            item["label"] = adjudication["label"]
            item["adjudication"] = {
                "adjudicator_id": adjudication["adjudicator_id"],
                "file_sha256": adjudication_hash,
            }
        else:
            item["label"] = one
        resolved[case_id] = item
    grouped: dict[str, list[str]] = defaultdict(list)
    for case in dataset.cases:
        grouped[case.pair_id].append(resolved[case.case_id]["label"])
    if any(set(pair_labels) != {"good", "bad"} for pair_labels in grouped.values()):
        raise ValueError("each held-out pair must resolve to one good and one bad answer")
    return resolved


def _load_adjudications(
    path: Path, dataset_sha256: str, disagreement_ids: set[str]
) -> tuple[dict[str, dict[str, str]], str]:
    required = {
        "dataset_sha256",
        "case_id",
        "adjudicator_id",
        "label",
        "rationale",
        "reviewed_at_utc",
    }
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        fieldnames = reader.fieldnames or []
        if len(fieldnames) != len(set(fieldnames)):
            raise ValueError(f"{path}: duplicate adjudication CSV columns")
        actual_fields = set(fieldnames)
        missing = required - actual_fields
        extra = actual_fields - required
        if missing or extra:
            details = sorted(missing | extra)
            raise ValueError(f"{path}: adjudication CSV columns do not match: {', '.join(details)}")
        rows = list(reader)
    adjudications: dict[str, dict[str, str]] = {}
    adjudicators: set[str] = set()
    for line_number, row in enumerate(rows, start=2):
        if None in row or any(value is None for value in row.values()):
            raise ValueError(f"{path}:{line_number}: malformed or incomplete CSV row")
        case_id = (row.get("case_id") or "").strip()
        if case_id in adjudications or case_id not in disagreement_ids:
            raise ValueError(f"{path}:{line_number}: unexpected or duplicate adjudication case")
        if row.get("dataset_sha256", "").strip() != dataset_sha256:
            raise ValueError(f"{path}:{line_number}: dataset hash does not match frozen cohort")
        adjudicator = (row.get("adjudicator_id") or "").strip()
        label = (row.get("label") or "").strip().lower()
        if not adjudicator or label not in {"good", "bad"}:
            raise ValueError(f"{path}:{line_number}: adjudicator and valid label are required")
        if any(not (row.get(field) or "").strip() for field in ("rationale", "reviewed_at_utc")):
            raise ValueError(f"{path}:{line_number}: rationale and timestamp are required")
        adjudicators.add(adjudicator)
        adjudications[case_id] = {"label": label, "adjudicator_id": adjudicator}
    if len(adjudicators) != 1 or set(adjudications) != disagreement_ids:
        raise ValueError(f"{path}: adjudications must cover exactly all disagreements")
    return adjudications, sha256_file(path)


def authored_control_labels(dataset: AdapterDataset) -> dict[str, dict[str, Any]]:
    if dataset.cohort_kind != "authored-control":
        raise ValueError("authored control truth is not accepted for held-out calibration")
    return {
        case.case_id: {
            "label": case.control_truth,
            "source_kind": "synthetic-adapter-control",
            "dataset_sha256": dataset.sha256,
        }
        for case in dataset.cases
    }


def wilson_interval(successes: int, denominator: int, zero_reason: str) -> dict[str, Any]:
    """Return a two-sided 95% Wilson interval, with an explicit empty reason."""
    if denominator < 0 or successes < 0 or successes > denominator:
        raise ValueError("Wilson successes and denominator are inconsistent")
    if denominator == 0:
        return {
            "lower": None,
            "upper": None,
            "successes": successes,
            "denominator": 0,
            "denominator_reason": zero_reason,
        }
    proportion = successes / denominator
    z2 = WILSON_Z_95**2
    scale = 1 + z2 / denominator
    center = (proportion + z2 / (2 * denominator)) / scale
    margin = (
        WILSON_Z_95
        * math.sqrt(proportion * (1 - proportion) / denominator + z2 / (4 * denominator**2))
        / scale
    )
    return {
        "lower": max(0.0, center - margin),
        "upper": min(1.0, center + margin),
        "successes": successes,
        "denominator": denominator,
        "denominator_reason": None,
    }


def build_registry(
    *, source_sha: str | None, working_tree_clean: bool, judge_config: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    """Build the versioned per-adapter identity recorded with each run."""
    from importlib.metadata import PackageNotFoundError, version

    registry: dict[str, dict[str, Any]] = {}
    for key, spec in ADAPTERS.items():
        try:
            installed_version = version(spec.dependency)
        except PackageNotFoundError:
            installed_version = None
        registry[key] = {
            "adapter_function": spec.adapter_function,
            "dependency": spec.dependency,
            "dependency_version": installed_version or spec.locked_version,
            "dependency_version_source": "installed" if installed_version else "lockfile",
            "locked_version": spec.locked_version,
            "polarity": spec.polarity,
            "threshold": spec.threshold,
            "sample_kind": spec.sample_kind,
            "judge_config": judge_config,
            "source_sha": source_sha,
            "source_working_tree_clean": working_tree_clean,
        }
    return registry


def _promotion_status(
    *,
    invalid: int,
    not_attempted: int,
    sensitivity: float | None,
    specificity: float | None,
    sensitivity_interval: dict[str, Any],
    specificity_interval: dict[str, Any],
) -> str:
    if invalid or not_attempted:
        return "failed: incomplete measurement set"
    if sensitivity is None or specificity is None:
        return "insufficient evidence: empty class denominator"
    if (
        sensitivity_interval["denominator"] < MINIMUM_VALID_CASES_PER_CLASS
        or specificity_interval["denominator"] < MINIMUM_VALID_CASES_PER_CLASS
    ):
        return "insufficient evidence: fewer than nine valid cases in a class"
    if sensitivity < SENSITIVITY_BAR or specificity < SPECIFICITY_BAR:
        return "failed: sensitivity or specificity below predeclared bar"
    lower_bounds = [sensitivity_interval["lower"], specificity_interval["lower"]]
    if any(value is None for value in lower_bounds):
        return "insufficient evidence: missing Wilson lower bound"
    if min(lower_bounds) < WILSON_LOWER_BAR:
        return "insufficient evidence: Wilson lower bound below predeclared bar"
    return "eligible for human review; no automatic unquarantine"


def analyze_adapter_calibration(
    dataset: AdapterDataset,
    labels: dict[str, dict[str, Any]],
    attempts: list[MeasurementAttempt],
    registry: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Produce per-adapter confusion, completeness, uncertainty, and provenance."""
    planned_ids = {case.case_id for case in dataset.cases}
    attempt_ids = [attempt.case_id for attempt in attempts]
    if len(attempt_ids) != len(set(attempt_ids)) or set(attempt_ids) != planned_ids:
        raise ValueError("one measurement disposition is required for every planned case")
    if set(labels) != planned_ids:
        raise ValueError("one resolved label and provenance record is required per case")
    by_attempt = {attempt.case_id: attempt for attempt in attempts}
    cases_by_adapter: dict[str, list[AdapterCase]] = defaultdict(list)
    for case in dataset.cases:
        if case.adapter_key not in registry:
            raise ValueError(f"registry is missing adapter {case.adapter_key!r}")
        cases_by_adapter[case.adapter_key].append(case)

    per_adapter: dict[str, Any] = {}
    all_measurements: list[dict[str, Any]] = []
    for adapter_key, cases in sorted(cases_by_adapter.items()):
        spec = ADAPTERS[adapter_key]
        tp = fp = tn = fn = 0
        completed = invalid = not_attempted = 0
        matches = 0
        outcomes: list[dict[str, Any]] = []
        valid_bad = valid_good = 0
        for case in sorted(cases, key=lambda value: value.case_id):
            attempt = by_attempt[case.case_id]
            if attempt.status not in {"completed", "invalid", "not_attempted"}:
                raise ValueError(f"measurement status is invalid for {case.case_id!r}")
            actual = labels[case.case_id].get("label")
            if actual not in {"good", "bad"}:
                raise ValueError(f"resolved label is invalid for {case.case_id!r}")
            normalized_bad: bool | None = None
            correct: bool | None = None
            if attempt.status == "completed":
                if (
                    attempt.raw_score is None
                    or isinstance(attempt.raw_score, bool)
                    or not isinstance(attempt.raw_score, (int, float))
                    or not math.isfinite(attempt.raw_score)
                ):
                    raise ValueError(f"completed measurement {case.case_id!r} needs a finite score")
                if not 0 <= attempt.raw_score <= 1:
                    raise ValueError(f"adapter score for {case.case_id!r} must be between 0 and 1")
                if attempt.invalid_reason is not None:
                    raise ValueError(f"completed measurement {case.case_id!r} cannot have an error")
                completed += 1
                normalized_bad = attempt.raw_score < spec.threshold
                predicted: Label = "bad" if normalized_bad else "good"
                correct = predicted == actual
                matches += int(correct)
                if actual == "bad":
                    valid_bad += 1
                    tp += int(normalized_bad)
                    fn += int(not normalized_bad)
                else:
                    valid_good += 1
                    fp += int(normalized_bad)
                    tn += int(not normalized_bad)
            elif attempt.status == "invalid":
                invalid += 1
                if attempt.raw_score is not None:
                    raise ValueError(
                        f"invalid measurement {case.case_id!r} must not retain a score"
                    )
                if not attempt.invalid_reason:
                    raise ValueError(f"invalid measurement {case.case_id!r} needs an error code")
            else:
                not_attempted += 1
                if attempt.raw_score is not None:
                    raise ValueError(
                        f"unattempted measurement {case.case_id!r} must not retain a score"
                    )
            outcome = {
                "case_id": case.case_id,
                "pair_id": case.pair_id,
                "cohort_kind": dataset.cohort_kind,
                "status": attempt.status,
                "actual_label": actual,
                "raw_score": attempt.raw_score,
                "threshold": spec.threshold,
                "normalized_bad_decision": normalized_bad,
                "correct": correct,
                "invalid_reason": attempt.invalid_reason,
                "label_provenance": labels[case.case_id],
            }
            outcomes.append(outcome)
            all_measurements.append({"adapter_key": adapter_key, **outcome})
        sensitivity_ci = wilson_interval(tp, valid_bad, "no valid labeled bad cases")
        specificity_ci = wilson_interval(tn, valid_good, "no valid labeled good cases")
        sensitivity = tp / valid_bad if valid_bad else None
        specificity = tn / valid_good if valid_good else None
        raw_agreement = matches / completed if completed else None
        promotion = (
            "not applicable to synthetic controls"
            if dataset.cohort_kind == "authored-control"
            else _promotion_status(
                invalid=invalid,
                not_attempted=not_attempted,
                sensitivity=sensitivity,
                specificity=specificity,
                sensitivity_interval=sensitivity_ci,
                specificity_interval=specificity_ci,
            )
        )
        per_adapter[adapter_key] = {
            "registry": registry[adapter_key],
            "completeness": {
                "planned": len(cases),
                "attempted": completed + invalid,
                "completed": completed,
                "invalid": invalid,
                "not_attempted": not_attempted,
                "complete": completed == len(cases),
            },
            "confusion_matrix_valid_measurements_only": {
                "positive_class": "bad answer flagged",
                "tp": tp,
                "fp": fp,
                "tn": tn,
                "fn": fn,
                "valid_labeled_bad_denominator": valid_bad,
                "valid_labeled_good_denominator": valid_good,
            },
            "sensitivity": sensitivity,
            "sensitivity_wilson_95": sensitivity_ci,
            "specificity": specificity,
            "specificity_wilson_95": specificity_ci,
            "raw_agreement": raw_agreement,
            "raw_agreement_denominator": completed,
            "promotion_status": promotion,
            "measurements": outcomes,
        }

    return {
        "schema_version": RUNTIME_ADAPTER_PROTOCOL,
        "status": (
            "synthetic-adapter-control"
            if dataset.cohort_kind == "authored-control"
            else (
                "incomplete"
                if any(item["status"] != "completed" for item in all_measurements)
                else "complete"
            )
        ),
        "source_kind": (
            "synthetic-adapter-control"
            if dataset.cohort_kind == "authored-control"
            else "independently-labeled-heldout"
        ),
        "cohort_id": dataset.cohort_id,
        "cohort_kind": dataset.cohort_kind,
        "dataset": {"path": dataset.path.name, "sha256": dataset.sha256},
        "promotion_policy": {
            "sensitivity_minimum": SENSITIVITY_BAR,
            "specificity_minimum": SPECIFICITY_BAR,
            "wilson_95_lower_minimum": WILSON_LOWER_BAR,
            "minimum_valid_cases_per_class": MINIMUM_VALID_CASES_PER_CLASS,
            "invalid_outputs_allowed": 0,
            "positive_class": "bad answer flagged",
            "cohort_pooling": False,
            "automatic_unquarantine": False,
        },
        "per_adapter": per_adapter,
    }
