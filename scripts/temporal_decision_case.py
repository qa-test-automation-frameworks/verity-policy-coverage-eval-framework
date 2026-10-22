"""Reproduce an authored, no-key temporal-regression decision case."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from verity.golden import load_golden
from verity.temporal_checks import check_temporal_amount

_ROOT = Path(__file__).resolve().parents[1]
_CASE_ID = "defect-2-silver-premium-stale"
_ORACLE_PATH = Path("src/verity/temporal_checks.py")
_SCRIPT_PATH = Path(__file__).resolve().relative_to(_ROOT)
_ALLOWED_EVIDENCE = {
    "src/sut/corpus/silver.md",
    "src/sut/corpus/amendments.md",
}
_CONTROLS = {
    "stale": {
        "answer": "The current Silver plan monthly premium is $420.",
        "evidence": "src/sut/corpus/silver.md",
    },
    "current": {
        "answer": "The amended Silver plan monthly premium is $445 effective 2024-07-01.",
        "evidence": "src/sut/corpus/amendments.md",
    },
}
_DECISIONS = {"PASS": "ship", "FAIL": "quarantine", "REVIEW": "inconclusive"}
_MONEY = re.compile(r"\$\s*(\d[\d,]*)(?:\.(\d{1,2}))?")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _amounts_minor(text: str) -> list[int]:
    amounts: list[int] = []
    for whole, fraction in _MONEY.findall(text):
        cents = (fraction or "").ljust(2, "0")
        amounts.append(int(whole.replace(",", "")) * 100 + int(cents or "0"))
    return amounts


def _control_result(
    *,
    name: str,
    answer: str,
    evidence_path: str,
    expectation: Any,
    root: Path,
) -> dict[str, Any]:
    evidence_text = (root / evidence_path).read_text(encoding="utf-8")
    answer_amounts = _amounts_minor(answer)
    evidence_amounts = set(_amounts_minor(evidence_text))
    temporal = check_temporal_amount(expectation, answer)
    status = temporal["status"]
    return {
        "control": name,
        "answer": answer,
        "evidence_file": evidence_path,
        "grounding": {
            "method": "literal amount match in the authored evidence file",
            "all_answer_amounts_appear_in_evidence": bool(answer_amounts)
            and all(amount in evidence_amounts for amount in answer_amounts),
            "answer_amounts_minor": answer_amounts,
        },
        "temporal": temporal,
        "measurement_status": "valid_oracle_result",
        "decision": _DECISIONS[status],
        "errors": 0,
        "invalid_measurements": 0,
    }


def build_report(
    root: Path,
    *,
    control: str = "all",
    answer: str | None = None,
    evidence: str | None = None,
) -> dict[str, Any]:
    """Build a deterministic report without contacting a provider."""
    if control not in (*_CONTROLS, "all"):
        raise ValueError(f"unknown control {control!r}")
    if control == "all" and (answer is not None or evidence is not None):
        raise ValueError("answer/evidence overrides require one named control")
    if evidence is not None and evidence not in _ALLOWED_EVIDENCE:
        raise ValueError(f"evidence must be one of {sorted(_ALLOWED_EVIDENCE)}")

    case = next(
        (item for item in load_golden(root / "datasets/golden") if item.id == _CASE_ID), None
    )
    if case is None or case.temporal_amount is None:
        raise ValueError(f"golden temporal case {_CASE_ID!r} is missing")

    selected = list(_CONTROLS) if control == "all" else [control]
    results = []
    for name in selected:
        defaults = _CONTROLS[name]
        selected_answer = answer if answer is not None else defaults["answer"]
        selected_evidence = evidence if evidence is not None else defaults["evidence"]
        results.append(
            _control_result(
                name=name,
                answer=selected_answer,
                evidence_path=selected_evidence,
                expectation=case.temporal_amount,
                root=root,
            )
        )

    config = {
        "policy": "temporal-decision-v1",
        "controls": _CONTROLS,
        "decision_mapping": _DECISIONS,
    }
    corpus_paths = ["src/sut/corpus/silver.md", "src/sut/corpus/amendments.md"]
    dataset_path = Path("datasets/golden/defects.yaml")
    final_decision = next(
        (item["decision"] for item in results if item["control"] == "stale"),
        results[0]["decision"],
    )
    return {
        "schema_version": 1,
        "source_kind": "authored_control",
        "hypothesis": (
            "A grounded obsolete premium can pass a grounding-only check; "
            "the temporal oracle should quarantine it."
        ),
        "case": {
            "id": case.id,
            "dataset_version": case.dataset_version,
            "query": case.query,
            "authoritative_truth": {
                "current_amount_minor": case.temporal_amount.current_amount_minor,
                "superseded_amounts_minor": case.temporal_amount.superseded_amounts_minor,
                "currency": case.temporal_amount.currency,
                "effective_date": case.temporal_amount.effective_date.isoformat(),
                "evidence_id": case.temporal_amount.authoritative_evidence_id,
                "source": case.temporal_amount.authoritative_source,
            },
        },
        "identities": {
            "golden_file": {
                "path": dataset_path.as_posix(),
                "sha256": _sha256(root / dataset_path),
            },
            "corpus_files": {path: _sha256(root / path) for path in corpus_paths},
            "framework_files": {
                _ORACLE_PATH.as_posix(): _sha256(root / _ORACLE_PATH),
                _SCRIPT_PATH.as_posix(): _sha256(root / _SCRIPT_PATH),
            },
            "control_config": {
                "id": config["policy"],
                "sha256": hashlib.sha256(
                    json.dumps(config, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest(),
            },
            "provider_configuration": "none; no provider is called",
        },
        "sampling": {
            "independent_case_denominator": 1,
            "authored_control_outputs": len(results),
            "independent_model_samples": 0,
            "provider_requests": 0,
            "input_tokens": None,
            "output_tokens": None,
            "cost_usd": None,
        },
        "uncertainty": (
            "No Wilson interval is calculated for this purposive one-case authored control. "
            "When used on sampled measurements, a Wilson interval estimates the probability "
            "of crossing a fixed threshold under those sampled conditions; it does not express "
            "confidence that the mean score is correct or estimate a production population."
        ),
        "decision_policy": {
            "PASS": "ship the authored answer control",
            "FAIL": "quarantine the authored answer control",
            "REVIEW": "inconclusive; inspect the answer",
            "production_decision": "none; controls are not a deployment evaluation",
        },
        "decision": final_decision,
        "controls": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control", choices=["all", *_CONTROLS], default="all")
    parser.add_argument("--answer", help="replace the named control's seeded answer")
    parser.add_argument("--evidence", choices=sorted(_ALLOWED_EVIDENCE))
    parser.add_argument("--out", type=Path, help="write the sanitized JSON report here")
    args = parser.parse_args()
    try:
        report = build_report(
            _ROOT, control=args.control, answer=args.answer, evidence=args.evidence
        )
    except ValueError as exc:
        parser.error(str(exc))
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.out:
        destination = args.out if args.out.is_absolute() else _ROOT / args.out
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
