"""Adversarial probe schema and loader for Tier-3 red-team evaluation.

Probes are adversarial queries designed to surface failures across eight
attack categories: prompt injection, jailbreak, PII extraction, harmful
content, coverage hallucination, prompt/system-instruction extraction, tool
abuse, and adjudication-language leakage. Each probe records the expected
defense type and whether the SUT is expected to handle it correctly
(defended) or fail (breached — seeded defect manifests).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

Category = Literal[
    "injection",
    "jailbreak",
    "pii_extraction",
    "harmful_content",
    "coverage_hallucination",
    "prompt_extraction",
    "tool_abuse",
    "adjudication_language",
]

Defense = Literal[
    "no_injection_compliance",  # scan_injection() must return False
    "no_pii",  # scan_pii() must return []
    "refuse",  # response.refused must be True
    "no_hallucinated_coverage",  # must_not_contain tokens checked
    "answer",  # response.refused must be False (not refused)
    "no_system_prompt_leak",  # must_not_contain tokens (system-prompt phrasing) checked
    "no_canary_leak",  # must_not_contain tokens (canary secret) checked
    "no_tool_abuse",  # tool_invocations must be empty for these probes
    "no_adjudication_language",  # check_no_adjudication_language() must pass
]

Outcome = Literal["defended", "breached"]


class AdversarialProbe(BaseModel):
    """A single adversarial probe for red-team evaluation."""

    id: str
    category: Category
    prompt: str
    member_id: str = "MBR-001"
    defense: Defense
    expected_outcome: Outcome
    must_not_contain: list[str] = Field(default_factory=list)
    retrieval_fixture_id: str = ""  # ID for FixtureRetriever (defaults to probe id)
    notes: str = ""

    def effective_fixture_id(self) -> str:
        return self.retrieval_fixture_id or self.id


def load_probes(path: Path) -> list[AdversarialProbe]:
    """Load adversarial probes from a YAML file."""
    with path.open() as fh:
        raw: Any = yaml.safe_load(fh)
    if not isinstance(raw, dict):
        return []
    return [AdversarialProbe.model_validate(item) for item in raw.get("probes", [])]
