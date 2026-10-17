"""Optional grounded assistant for the synthetic quality reference application.

This integration is deliberately separate from ``CoverageAgent``: the existing
seeded/clean evaluation target remains unchanged and no app connection is made
unless a caller explicitly constructs this assistant.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from sut.citations import resolve_citations
from sut.guardrails import REFUSAL_MESSAGE, check_input
from sut.retriever import Chunk, Retriever
from verity.providers import LLMProvider

SHARED_APP_CORPUS_VERSION = "v0.2.0"
SHARED_APP_TOOL_SCHEMA_VERSION = "v2"


class WorkspaceArgs(BaseModel):
    """The model cannot supply a member, policy, or claim identifier."""

    model_config = ConfigDict(extra="forbid", strict=True)


GET_MY_WORKSPACE_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "get_my_reference_workspace",
        "description": "Read the policies and claims visible to the signed-in synthetic identity.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    },
}


@dataclass(frozen=True)
class ReferenceWorkspace:
    policies: list[dict[str, Any]]
    claims: list[dict[str, Any]]


class ReferenceAppClient:
    """A fixed-identity client; the API, not the model, scopes returned records."""

    def __init__(
        self,
        base_url: str,
        identity_key: str,
        *,
        timeout: float = 5.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if identity_key not in {"member-a", "member-b", "reviewer"}:
            raise ValueError("identity_key must name a documented synthetic identity")
        self._identity_key = identity_key
        self._http = httpx.Client(
            base_url=base_url.rstrip("/"), timeout=timeout, transport=transport
        )
        response = self._http.post("/api/v1/sessions", json={"identityKey": identity_key})
        response.raise_for_status()
        payload = response.json()
        token = payload.get("token")
        if not isinstance(token, str) or not token:
            raise ValueError("reference app returned an invalid session")
        self._http.headers["Authorization"] = f"Bearer {token}"

    @property
    def identity_key(self) -> str:
        """The configured synthetic test identity; never derived from a model call."""
        return self._identity_key

    def get_my_workspace(self) -> ReferenceWorkspace:
        policies = self._http.get("/api/v2/policies")
        policies.raise_for_status()
        claims = self._http.get("/api/v2/claims")
        claims.raise_for_status()
        return ReferenceWorkspace(
            policies=_items(policies.json(), "policies"),
            claims=_items(claims.json(), "claims"),
        )

    def get_claim(self, claim_id: str) -> dict[str, Any]:
        """Read a claim by ID through the app's ownership-checked API.

        This method supports direct authorization tests. The assistant tool does
        not expose claim IDs and only calls ``get_my_workspace``.
        """
        try:
            canonical_claim_id = str(UUID(claim_id))
        except ValueError as exc:
            raise ValueError("claim_id must be a UUID") from exc
        response = self._http.get(f"/api/v2/claims/{canonical_claim_id}")
        response.raise_for_status()
        payload: Any = response.json()
        if not isinstance(payload, dict):
            raise ValueError("reference app returned a malformed claim")
        return payload

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> ReferenceAppClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def _items(payload: Any, label: str) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise ValueError(f"reference app returned malformed {label}")
    if not all(isinstance(item, dict) for item in payload["items"]):
        raise ValueError(f"reference app returned malformed {label}")
    return cast(list[dict[str, Any]], payload["items"])


@dataclass(frozen=True)
class SharedAppResponse:
    answer: str
    citations: list[str]
    retrieved_chunks: list[Chunk]
    tool_result: ReferenceWorkspace | None
    refused: bool = False
    failure_category: str = ""


class SharedAppAssistant:
    """Optional RAG + read-only tool assistant using Verity's existing interfaces."""

    def __init__(
        self, retriever: Retriever, provider: LLMProvider, app: ReferenceAppClient
    ) -> None:
        self._retriever = retriever
        self._provider = provider
        self._app = app

    def answer(self, query: str, *, top_k: int | None = None) -> SharedAppResponse:
        refused, _reason = check_input(query)
        if refused:
            return SharedAppResponse(REFUSAL_MESSAGE, [], [], None, refused=True)

        chunks = self._retriever.retrieve(query, top_k=top_k)
        if not chunks:
            return SharedAppResponse(
                "I could not find relevant information in the reference policy corpus.",
                [],
                [],
                None,
            )
        context = (
            "\n\n".join(f"[{chunk.source} — {chunk.section}]\n{chunk.text}" for chunk in chunks)
            or "No relevant policy sections were retrieved."
        )
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "Answer questions about the synthetic reference application's policy and "
                    "claim workflow using only the retrieved policy text and the signed-in "
                    "workspace tool. The application independently enforces record ownership. "
                    "Never claim access to another member's records. Cite policy claims as "
                    "(source §section). The corpus version is "
                    f"{SHARED_APP_CORPUS_VERSION}; tool schema is "
                    f"{SHARED_APP_TOOL_SCHEMA_VERSION}.\n"
                    f"Retrieved policy context:\n{context}"
                ),
            },
            {"role": "user", "content": query},
        ]
        try:
            first = self._provider.complete(
                messages, tools=[GET_MY_WORKSPACE_SCHEMA], label="shared-app-first"
            )
            if len(first.tool_calls) > 1:
                return SharedAppResponse(
                    "I could not safely process that request.",
                    [],
                    chunks,
                    None,
                    failure_category="multiple_tool_calls",
                )
            workspace = None
            if first.tool_calls:
                call = first.tool_calls[0]
                if call.function.name != "get_my_reference_workspace":
                    return SharedAppResponse(
                        "I could not safely process that request.",
                        [],
                        chunks,
                        None,
                        failure_category="unknown_tool",
                    )
                try:
                    args = json.loads(call.function.arguments)
                    WorkspaceArgs.model_validate(args)
                except (json.JSONDecodeError, ValidationError, TypeError):
                    return SharedAppResponse(
                        "I could not safely process that request.",
                        [],
                        chunks,
                        None,
                        failure_category="invalid_tool_arguments",
                    )
                workspace = self._app.get_my_workspace()
                messages.extend(
                    [
                        {
                            "role": "assistant",
                            "content": first.content or "",
                            "tool_calls": [
                                {
                                    "id": call.id,
                                    "type": "function",
                                    "function": {
                                        "name": call.function.name,
                                        "arguments": call.function.arguments,
                                    },
                                }
                            ],
                        },
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "content": json.dumps(
                                {"policies": workspace.policies, "claims": workspace.claims}
                            ),
                        },
                    ]
                )
                final = self._provider.complete(messages, label="shared-app-second")
                if final.tool_calls:
                    return SharedAppResponse(
                        "I could not safely process that request.",
                        [],
                        chunks,
                        workspace,
                        failure_category="unsupported_tool_round",
                    )
            else:
                final = first
            answer = (
                final.content or "I could not find an answer in the available policy information."
            )
            citations = [
                f"{chunk.source}: {chunk.section}" for chunk in resolve_citations(chunks, answer)
            ]
            return SharedAppResponse(answer, citations, chunks, workspace)
        except Exception:
            return SharedAppResponse(
                "The reference assistant is temporarily unavailable.",
                [],
                chunks,
                None,
                failure_category="integration_unavailable",
            )
