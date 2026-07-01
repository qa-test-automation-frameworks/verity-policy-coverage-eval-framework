"""Live smoke test — makes one real GLM-4.5 call and logs tokens/cost.

Run with: make smoke
Excluded from CI (requires ZAI_API_KEY or equivalent in .env).
"""

from __future__ import annotations

import pytest

from verity.config import get_settings
from verity.cost import RunAccumulator
from verity.providers import LLMProvider


@pytest.mark.live
def test_model_identity_smoke() -> None:
    """Verify the provider returns a non-empty response and logs tokens/cost."""
    settings = get_settings()
    acc = RunAccumulator()
    provider = LLMProvider(settings, acc)

    result = provider.complete(
        messages=[
            {"role": "user", "content": "Reply with exactly one word: 'ready'"},
        ],
        max_tokens=10,
        label="smoke-test",
    )

    assert result.content.strip() != "", "Expected non-empty response from model"
    assert len(acc.records) == 1
    record = acc.records[0]
    assert record.usage.total_tokens > 0
    assert record.latency_ms > 0

    print(f"\n[smoke] Model: {record.model}")
    print(f"[smoke] Response: {result.content!r}")
    print(f"[smoke] {acc.summary()}")
