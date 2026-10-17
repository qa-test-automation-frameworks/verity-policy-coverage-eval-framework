from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import httpx

from sut.retriever import Chunk
from sut.shared_app import (
    GET_MY_WORKSPACE_SCHEMA,
    ReferenceAppClient,
    SharedAppAssistant,
    WorkspaceArgs,
)
from verity.providers import CompletionResult


class _Retriever:
    def retrieve(self, query: str, top_k: int | None = None) -> list[Chunk]:
        return [Chunk("Claims are owned by the submitting member.", "claims.md", "Ownership", "c1")]


class _Provider:
    def __init__(self, *results: CompletionResult) -> None:
        self.results = list(results)
        self.calls: list[dict[str, Any]] = []

    def complete(self, messages: list[dict[str, Any]], **kwargs: Any) -> CompletionResult:
        self.calls.append({"messages": messages, **kwargs})
        return self.results.pop(0)


def _tool_call(arguments: str = "{}") -> Any:
    return SimpleNamespace(
        id="call-1",
        function=SimpleNamespace(name="get_my_reference_workspace", arguments=arguments),
    )


def _app_transport(requests: list[httpx.Request]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/v1/sessions":
            assert request.read() == b'{"identityKey":"member-a"}'
            return httpx.Response(201, json={"token": "opaque-test-token"})
        assert request.headers.get("Authorization") == "Bearer opaque-test-token"
        if request.url.path == "/api/v1/policies":
            return httpx.Response(200, json={"items": [{"id": "policy-a"}]})
        if request.url.path == "/api/v1/claims":
            return httpx.Response(200, json={"items": [{"id": "claim-a"}]})
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def test_reference_app_client_keeps_identity_out_of_tool_arguments() -> None:
    requests: list[httpx.Request] = []
    with ReferenceAppClient(
        "https://reference.example", "member-a", transport=_app_transport(requests)
    ) as client:
        workspace = client.get_my_workspace()

    assert client.identity_key == "member-a"
    assert workspace.policies == [{"id": "policy-a"}]
    assert workspace.claims == [{"id": "claim-a"}]
    assert [request.url.path for request in requests] == [
        "/api/v1/sessions",
        "/api/v1/policies",
        "/api/v1/claims",
    ]
    assert GET_MY_WORKSPACE_SCHEMA["function"]["parameters"] == {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False,
    }


def test_reference_app_client_validates_direct_claim_lookup_ids() -> None:
    requests: list[httpx.Request] = []
    with ReferenceAppClient(
        "https://reference.example", "member-a", transport=_app_transport(requests)
    ) as client:
        try:
            client.get_claim("not-a-claim-id")
        except ValueError as error:
            assert "must be a UUID" in str(error)
        else:
            raise AssertionError("invalid claim path must be rejected before HTTP")

    assert [request.url.path for request in requests] == ["/api/v1/sessions"]


def test_workspace_tool_rejects_member_or_claim_selector() -> None:
    try:
        WorkspaceArgs.model_validate({"member_id": "member-b"})
    except Exception as error:
        assert "Extra inputs are not permitted" in str(error)
    else:
        raise AssertionError("tool must reject caller-selected identity")


def test_shared_assistant_retrieves_citations_and_uses_fixed_identity() -> None:
    requests: list[httpx.Request] = []
    client = ReferenceAppClient(
        "https://reference.example", "member-a", transport=_app_transport(requests)
    )
    tool_response = CompletionResult("", [_tool_call()])
    final_response = CompletionResult("Claims belong to the submitting member. (claims §Ownership)")
    provider = _Provider(tool_response, final_response)
    result = SharedAppAssistant(_Retriever(), provider, client).answer("Show my claims")
    client.close()

    assert result.failure_category == ""
    assert result.tool_result is not None
    assert result.tool_result.claims == [{"id": "claim-a"}]
    assert result.citations == ["claims.md: Ownership"]
    assert provider.calls[0]["tools"] == [GET_MY_WORKSPACE_SCHEMA]
    assert "member_id" not in provider.calls[0]["tools"][0]["function"]["parameters"]["properties"]


def test_shared_assistant_rejects_extra_tool_arguments_without_api_access() -> None:
    requests: list[httpx.Request] = []
    client = ReferenceAppClient(
        "https://reference.example", "member-a", transport=_app_transport(requests)
    )
    provider = _Provider(CompletionResult("", [_tool_call('{"member_id":"member-b"}')]))
    result = SharedAppAssistant(_Retriever(), provider, client).answer(
        "Show another member's claims"
    )
    client.close()

    assert result.failure_category == "invalid_tool_arguments"
    assert [request.url.path for request in requests] == ["/api/v1/sessions"]


def test_shared_assistant_does_not_call_provider_when_retrieval_is_empty() -> None:
    class EmptyRetriever:
        def retrieve(self, query: str, top_k: int | None = None) -> list[Chunk]:
            return []

    requests: list[httpx.Request] = []
    client = ReferenceAppClient(
        "https://reference.example", "member-a", transport=_app_transport(requests)
    )
    provider = _Provider()
    result = SharedAppAssistant(EmptyRetriever(), provider, client).answer("unrelated question")
    client.close()

    assert result.citations == []
    assert "could not find relevant information" in result.answer
    assert provider.calls == []
    assert [request.url.path for request in requests] == ["/api/v1/sessions"]


def test_shared_assistant_rejects_a_second_tool_round() -> None:
    requests: list[httpx.Request] = []
    client = ReferenceAppClient(
        "https://reference.example", "member-a", transport=_app_transport(requests)
    )
    second_call = SimpleNamespace(
        id="call-2",
        function=SimpleNamespace(name="get_my_reference_workspace", arguments="{}"),
    )
    provider = _Provider(CompletionResult("", [_tool_call()]), CompletionResult("", [second_call]))
    result = SharedAppAssistant(_Retriever(), provider, client).answer("Show my claims")
    client.close()

    assert result.failure_category == "unsupported_tool_round"
    assert [request.url.path for request in requests] == [
        "/api/v1/sessions",
        "/api/v1/policies",
        "/api/v1/claims",
    ]
