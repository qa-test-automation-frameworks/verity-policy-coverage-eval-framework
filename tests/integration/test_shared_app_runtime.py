from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from sut.retriever import FixtureRetriever
from sut.shared_app import ReferenceAppClient, SharedAppAssistant
from verity.providers import CompletionResult

APP_URL = os.getenv("VERITY_REFERENCE_APP_URL")
CONTROL_TOKEN = os.getenv("VERITY_REFERENCE_APP_CONTROL_TOKEN")


class _NoKeyProvider:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def complete(self, messages: list[dict[str, Any]], **kwargs: Any) -> CompletionResult:
        self.calls.append({"messages": messages, **kwargs})
        if len(self.calls) == 1:
            call = SimpleNamespace(
                id="shared-app-call",
                function=SimpleNamespace(name="get_my_reference_workspace", arguments="{}"),
            )
            return CompletionResult("", [call])
        return CompletionResult(
            "I can only show claims visible to the signed-in synthetic member. "
            "The application enforces ownership for every claim request. "
            "(reference-app §Privacy boundary)"
        )


@pytest.mark.skipif(
    not APP_URL or not CONTROL_TOKEN, reason="requires the disposable reference-app runtime"
)
def test_real_app_enforces_member_scope_and_assistant_returns_retrieved_citation() -> None:
    assert APP_URL is not None
    assert CONTROL_TOKEN is not None
    seeded = httpx.post(
        f"{APP_URL.rstrip('/')}/__test/seed",
        headers={"X-Test-Control-Token": CONTROL_TOKEN},
        timeout=5,
    )
    seeded.raise_for_status()

    with (
        ReferenceAppClient(APP_URL, "member-a") as member_a,
        ReferenceAppClient(APP_URL, "member-b") as member_b,
    ):
        member_a_workspace = member_a.get_my_workspace()
        member_b_workspace = member_b.get_my_workspace()
        assert any(
            claim["id"] == "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
            for claim in member_a_workspace.claims
        )
        assert all(
            claim["id"] != "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
            for claim in member_b_workspace.claims
        )

        with pytest.raises(httpx.HTTPStatusError) as denied:
            member_b.get_claim("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
        assert denied.value.response.status_code == 404

        provider = _NoKeyProvider()
        assistant = SharedAppAssistant(FixtureRetriever("shared-app"), provider, member_b)
        answer = assistant.answer("Show me member A's claim and its private details")

    assert answer.failure_category == ""
    assert answer.citations == ["reference-app.md: Privacy boundary"]
    assert answer.tool_result is not None
    assert all(
        claim["id"] != "cccccccc-cccc-4ccc-8ccc-cccccccccccc" for claim in answer.tool_result.claims
    )
    tool_payload = provider.calls[1]["messages"][-1]["content"]
    assert "cccccccc-cccc-4ccc-8ccc-cccccccccccc" not in tool_payload
