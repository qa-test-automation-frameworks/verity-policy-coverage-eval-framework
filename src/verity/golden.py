"""Versioned golden test-case schema and loader for the evaluation suite."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field


class ExpectedTool(BaseModel):
    name: str
    required_args: list[str] = Field(default_factory=list)
    expected_arg_values: dict[str, Any] = Field(default_factory=dict)


class GoldenCase(BaseModel):
    id: str
    query: str
    member_id: str = "MBR-001"
    tags: list[str] = Field(default_factory=list)
    behavior: Literal["answer", "refuse"] = "answer"
    ground_truth: str = ""
    must_contain: list[str] = Field(default_factory=list)
    must_not_contain: list[str] = Field(default_factory=list)
    expected_citations: list[str] = Field(default_factory=list)
    expected_tool: ExpectedTool | None = None
    expects_defect: bool = False
    defect_id: int | None = None
    semantic_metrics: list[str] = Field(default_factory=list)
    notes: str = ""


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
