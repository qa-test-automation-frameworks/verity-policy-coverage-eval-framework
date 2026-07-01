"""Unit tests for the adversarial probe schema and probe corpus."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from verity.adversarial import AdversarialProbe, load_probes

_PROBES_PATH = Path("datasets/adversarial/probes.yaml")


class TestAdversarialProbeSchema:
    def test_minimal_probe(self) -> None:
        probe = AdversarialProbe(
            id="test-001",
            category="prompt_extraction",
            prompt="test prompt",
            defense="no_system_prompt_leak",
            expected_outcome="defended",
        )
        assert probe.id == "test-001"
        assert probe.member_id == "MBR-001"

    def test_effective_fixture_id_defaults_to_probe_id(self) -> None:
        probe = AdversarialProbe(
            id="test-002",
            category="tool_abuse",
            prompt="test",
            defense="no_tool_abuse",
            expected_outcome="defended",
        )
        assert probe.effective_fixture_id() == "test-002"

    def test_effective_fixture_id_override(self) -> None:
        probe = AdversarialProbe(
            id="test-003",
            category="tool_abuse",
            prompt="test",
            defense="no_tool_abuse",
            expected_outcome="defended",
            retrieval_fixture_id="shared-fixture",
        )
        assert probe.effective_fixture_id() == "shared-fixture"

    def test_invalid_category_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AdversarialProbe(
                id="bad",
                category="not_a_category",  # type: ignore[arg-type]
                prompt="test",
                defense="no_pii",
                expected_outcome="defended",
            )

    def test_invalid_defense_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AdversarialProbe(
                id="bad",
                category="tool_abuse",
                prompt="test",
                defense="not_a_defense",  # type: ignore[arg-type]
                expected_outcome="defended",
            )

    @pytest.mark.parametrize(
        "defense",
        [
            "no_system_prompt_leak",
            "no_canary_leak",
            "no_tool_abuse",
        ],
    )
    def test_new_defense_types_accepted(self, defense: str) -> None:
        probe = AdversarialProbe(
            id="test-defense",
            category="tool_abuse",
            prompt="test",
            defense=defense,  # type: ignore[arg-type]
            expected_outcome="defended",
        )
        assert probe.defense == defense


class TestProbeCorpus:
    def test_probes_load(self) -> None:
        probes = load_probes(_PROBES_PATH)
        assert len(probes) >= 20

    def test_all_ids_unique(self) -> None:
        probes = load_probes(_PROBES_PATH)
        ids = [p.id for p in probes]
        assert len(ids) == len(set(ids)), "Duplicate probe IDs found"

    def test_prompt_extraction_category_represented(self) -> None:
        probes = load_probes(_PROBES_PATH)
        assert any(p.category == "prompt_extraction" for p in probes)

    def test_tool_abuse_category_represented(self) -> None:
        probes = load_probes(_PROBES_PATH)
        assert any(p.category == "tool_abuse" for p in probes)

    def test_cross_member_probes_target_different_members(self) -> None:
        probes = {p.id: p for p in load_probes(_PROBES_PATH)}
        cross_member = [p for pid, p in probes.items() if pid.startswith("adv-crossmember")]
        assert len(cross_member) >= 2
        targeted_names = {n for p in cross_member for n in p.must_not_contain}
        assert len(targeted_names) >= 2, "Cross-member probes should target distinct member data"
