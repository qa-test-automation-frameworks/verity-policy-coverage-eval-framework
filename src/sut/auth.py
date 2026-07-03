"""Optional member-token checks for member-scoped requests."""

from __future__ import annotations

import hmac
import json

from pydantic import SecretStr


def _load_tokens(tokens_json: SecretStr | None) -> dict[str, str]:
    if tokens_json is None:
        return {}
    raw = tokens_json.get_secret_value().strip()
    if not raw:
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("member token mapping must be a JSON object")
    return {str(k): str(v) for k, v in data.items()}


def member_token_valid(
    member_id: str,
    provided_token: str | None,
    *,
    required: bool,
    tokens_json: SecretStr | None,
) -> bool:
    """Validate an optional per-member bearer token mapping."""
    if not required:
        return True
    expected = _load_tokens(tokens_json).get(member_id)
    if expected is None or provided_token is None:
        return False
    return hmac.compare_digest(provided_token, expected)
