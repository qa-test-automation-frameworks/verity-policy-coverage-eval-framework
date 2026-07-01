"""Tests for the clean vs. seeded SUT profile split.

The default "seeded" profile preserves the intentional defects the eval
suite's defect-detection golden cases are built around (#5 ambiguous tool-arg
naming, #8 PII prompt/log leakage). The "clean" profile runs a hardened
variant of the same agent so production-like behavior can be verified
independently of those fixtures.
"""

from __future__ import annotations

import logging

import pytest

from sut.agent import _build_system_prompt, _load_members
from sut.guardrails import log_member_context
from verity.config import Settings


def _gold_member() -> dict[str, object]:
    members = _load_members()
    return next(m for m in members.values() if m["plan"].lower() == "gold")


class TestSystemPromptProfiles:
    def test_seeded_profile_includes_name_and_dob(self) -> None:
        member = _gold_member()
        prompt = _build_system_prompt(member, [], clean=False)
        assert str(member["name"]) in prompt
        assert str(member["dob"]) in prompt

    def test_clean_profile_omits_name_and_dob(self) -> None:
        member = _gold_member()
        prompt = _build_system_prompt(member, [], clean=True)
        assert str(member["name"]) not in prompt
        assert str(member["dob"]) not in prompt
        assert str(member["member_id"]) in prompt

    def test_clean_profile_includes_tool_arg_disambiguation(self) -> None:
        member = _gold_member()
        prompt = _build_system_prompt(member, [], clean=True)
        assert "do not swap these" in prompt.lower()

    def test_seeded_profile_lacks_tool_arg_disambiguation(self) -> None:
        member = _gold_member()
        prompt = _build_system_prompt(member, [], clean=False)
        assert "do not swap these" not in prompt.lower()

    def test_default_is_seeded(self) -> None:
        assert Settings(cassette_mode="off").sut_profile == "seeded"


class TestMemberContextLogging:
    def test_seeded_profile_logs_full_member_dict(self, caplog: pytest.LogCaptureFixture) -> None:
        member = {"member_id": "MBR-999", "name": "Jane Test", "dob": "1990-01-01"}
        with caplog.at_level(logging.DEBUG, logger="sut.guardrails"):
            log_member_context(member, clean=False)
        assert "Jane Test" in caplog.text

    def test_clean_profile_redacts_name_and_dob(self, caplog: pytest.LogCaptureFixture) -> None:
        member = {"member_id": "MBR-999", "name": "Jane Test", "dob": "1990-01-01"}
        with caplog.at_level(logging.DEBUG, logger="sut.guardrails"):
            log_member_context(member, clean=True)
        assert "Jane Test" not in caplog.text
        assert "1990-01-01" not in caplog.text
        assert "MBR-999" in caplog.text

    def test_default_clean_arg_is_false(self, caplog: pytest.LogCaptureFixture) -> None:
        member = {"member_id": "MBR-999", "name": "Jane Test", "dob": "1990-01-01"}
        with caplog.at_level(logging.DEBUG, logger="sut.guardrails"):
            log_member_context(member)
        assert "Jane Test" in caplog.text


class TestCleanProfileEndToEnd:
    def test_clean_profile_agent_run_omits_member_pii_from_prompt(self) -> None:
        from unittest.mock import MagicMock

        from sut.agent import CoverageAgent
        from sut.retriever import FixtureRetriever
        from verity.cost import RunAccumulator
        from verity.providers import CompletionResult

        member = _gold_member()
        settings = Settings(cassette_mode="off", sut_profile="clean")
        retriever = FixtureRetriever("ctrl-gold-deductible")

        mock_provider = MagicMock()
        mock_provider.accumulator = RunAccumulator()
        mock_provider.complete.return_value = CompletionResult(
            content="Your Gold deductible is $750.", tool_calls=[]
        )

        agent = CoverageAgent(settings=settings, retriever=retriever, provider=mock_provider)
        agent.answer("What is my deductible?", member_id=str(member["member_id"]))

        sent_messages = mock_provider.complete.call_args.kwargs["messages"]
        system_prompt = sent_messages[0]["content"]
        assert str(member["name"]) not in system_prompt
        assert str(member["dob"]) not in system_prompt
