"""Token/cost accounting for all LLM calls made by the framework and SUT."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Price table ($/million tokens). Seed values from roadmap; update as needed.
# ---------------------------------------------------------------------------
_PRICE_TABLE: dict[str, dict[str, float]] = {
    # GLM-4-Plus pricing via Zhipu AI (verify with your provider before relying on these).
    "glm-4-plus": {"prompt": 0.14, "completion": 0.14},
    # Fallback for unknown models — zero cost so accounting never crashes.
    "__default__": {"prompt": 0.0, "completion": 0.0},
}


def _price_for(model: str) -> dict[str, float]:
    # Strip litellm provider prefix (e.g. "openai/glm-5.2" → "glm-5.2")
    slug = model.split("/")[-1].lower()
    return _PRICE_TABLE.get(slug, _PRICE_TABLE["__default__"])


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass(frozen=True)
class Cost:
    prompt_usd: float
    completion_usd: float
    total_usd: float

    def __str__(self) -> str:
        return (
            f"${self.total_usd:.6f} "
            f"(prompt=${self.prompt_usd:.6f}, completion=${self.completion_usd:.6f})"
        )


def estimate_cost(usage: Usage, model: str) -> Cost:
    prices = _price_for(model)
    prompt_usd = usage.prompt_tokens * prices["prompt"] / 1_000_000
    completion_usd = usage.completion_tokens * prices["completion"] / 1_000_000
    return Cost(
        prompt_usd=prompt_usd,
        completion_usd=completion_usd,
        total_usd=prompt_usd + completion_usd,
    )


@dataclass
class CallRecord:
    model: str
    usage: Usage
    cost: Cost
    latency_ms: float
    timestamp: float = field(default_factory=time.time)
    label: str = ""


# ---------------------------------------------------------------------------
# Per-run accumulator (thread-local-safe enough for single-process runs)
# ---------------------------------------------------------------------------
@dataclass
class RunAccumulator:
    records: list[CallRecord] = field(default_factory=list)

    def log_call(
        self,
        model: str,
        usage: Usage,
        latency_ms: float,
        label: str = "",
    ) -> CallRecord:
        cost = estimate_cost(usage, model)
        record = CallRecord(model=model, usage=usage, cost=cost, latency_ms=latency_ms, label=label)
        self.records.append(record)
        return record

    @property
    def total_cost(self) -> Cost:
        prompt = sum(r.cost.prompt_usd for r in self.records)
        completion = sum(r.cost.completion_usd for r in self.records)
        return Cost(prompt_usd=prompt, completion_usd=completion, total_usd=prompt + completion)

    @property
    def total_tokens(self) -> Usage:
        return Usage(
            prompt_tokens=sum(r.usage.prompt_tokens for r in self.records),
            completion_tokens=sum(r.usage.completion_tokens for r in self.records),
            total_tokens=sum(r.usage.total_tokens for r in self.records),
        )

    def summary(self) -> str:
        t = self.total_tokens
        c = self.total_cost
        calls = len(self.records)
        return (
            f"Calls: {calls} | "
            f"Tokens: {t.total_tokens} "
            f"(prompt={t.prompt_tokens}, completion={t.completion_tokens}) | "
            f"Cost: {c}"
        )


def usage_from_litellm(response: Any) -> Usage:
    """Extract Usage from a litellm CompletionResponse."""
    u = response.usage
    return Usage(
        prompt_tokens=u.prompt_tokens or 0,
        completion_tokens=u.completion_tokens or 0,
        total_tokens=u.total_tokens or 0,
    )
