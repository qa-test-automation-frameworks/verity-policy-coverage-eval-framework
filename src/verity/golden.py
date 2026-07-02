"""Versioned golden test-case schema and loader for the evaluation suite."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, model_validator


class ExpectedTool(BaseModel):
    name: str
    required_args: list[str] = Field(default_factory=list)
    expected_arg_values: dict[str, Any] = Field(default_factory=dict)


NumericComparator = Literal["eq", "gte", "lte", "gt", "lt", "range"]


class NumericExpectation(BaseModel):
    """A numeric value the answer must state, checked by comparison rather than
    literal substring match — catches a correct amount stated with different
    rounding/formatting that a must_contain token would miss.

    "eq" allows `tolerance` (absolute); "range" requires both min_value and
    max_value; the other comparators only need value.
    """

    description: str
    comparator: NumericComparator
    value: float | None = None
    tolerance: float = 0.0
    min_value: float | None = None
    max_value: float | None = None

    @model_validator(mode="after")
    def _required_bounds_present_for_comparator(self) -> NumericExpectation:
        if self.comparator == "range":
            if self.min_value is None or self.max_value is None:
                raise ValueError("comparator 'range' requires both min_value and max_value")
        elif self.value is None:
            raise ValueError(f"comparator {self.comparator!r} requires 'value'")
        return self


class DateExpectation(BaseModel):
    """A date the answer must state, within an inclusive [on_or_after, on_or_before]
    range. Either bound may be omitted for an open-ended range. Dates are ISO
    (YYYY-MM-DD)."""

    description: str
    on_or_after: str | None = None
    on_or_before: str | None = None

    @model_validator(mode="after")
    def _at_least_one_bound_set(self) -> DateExpectation:
        if self.on_or_after is None and self.on_or_before is None:
            raise ValueError("DateExpectation requires on_or_after and/or on_or_before")
        return self


ExpectationCategory = Literal[
    "coverage_decision",
    "amount",
    "limits",
    "refusal",
    "uncertainty",
    "evidence",
    "tool_behavior",
]


class GoldenCase(BaseModel):
    id: str
    query: str
    member_id: str = "MBR-001"
    tags: list[str] = Field(default_factory=list)
    behavior: Literal["answer", "refuse"] = "answer"
    ground_truth: str = ""
    must_contain: list[str] = Field(default_factory=list)
    must_not_contain: list[str] = Field(default_factory=list)
    numeric_expectations: list[NumericExpectation] = Field(default_factory=list)
    date_expectations: list[DateExpectation] = Field(default_factory=list)
    expected_citations: list[str] = Field(default_factory=list)
    requires_human_review: bool = False
    expected_tool: ExpectedTool | None = None
    expects_defect: bool = False
    defect_id: int | None = None
    semantic_metrics: list[str] = Field(default_factory=list)
    notes: str = ""

    # Case metadata (portfolio/evidence tracking) — optional, additive.
    dataset_version: str = "1.0.0"
    policy_version: str = "2024"
    evidence_ids: list[str] = Field(default_factory=list)
    risk_weight: Literal["low", "medium", "high"] = "medium"
    owner: str = ""
    last_reviewed: str = ""

    # Normalized expectation categories this case exercises, e.g. what kind of
    # claim is being checked (a dollar amount, a refusal, a tool call, ...).
    expectation_categories: list[ExpectationCategory] = Field(default_factory=list)


def load_golden(directory: Path | str | None = None) -> list[GoldenCase]:
    """Load all golden cases from YAML files in a directory."""
    d = Path(directory) if directory else Path("datasets/golden")
    cases: list[GoldenCase] = []
    for f in sorted(d.glob("*.yaml")):
        with f.open() as fh:
            raw: Any = yaml.safe_load(fh)
        if not isinstance(raw, dict):
            continue
        for item in raw.get("cases", []):
            cases.append(GoldenCase.model_validate(item))
    return cases
