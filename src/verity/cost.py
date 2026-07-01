"""Token/cost accounting for all LLM calls made by the framework and SUT."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Price table ($/million tokens). Add provider-verified rates as needed.
#
# Only models this repo actively routes to by default are priced here, and
# only at a rate we can point to a public source for. Rates drift — verify
# against the provider's current pricing page before treating a run's cost
# total as exact; this table is a reference estimate, not a billing record.
# Unlisted/unverified models (including free-tier routes such as OpenRouter's
# `:free` slugs) fall back to __default__, which is priced at $0 but flagged
# via Cost.priced=False so callers can tell "genuinely free" apart from
# "we don't have a rate for this model" instead of both looking like $0.
# ---------------------------------------------------------------------------
_PRICE_TABLE: dict[str, dict[str, float]] = {
    # Z.ai GLM-4.5 standard pricing as of the reference calibration date
    # (see docs/adr/0001-glm-4-5-model-choice.md). Verify current rates at
    # https://docs.z.ai before relying on this for budgeting.
    "glm-4.5": {"prompt": 0.60, "completion": 2.20},
}
_DEFAULT_PRICE: dict[str, float] = {"prompt": 0.0, "completion": 0.0}


def _price_for(model: str) -> tuple[dict[str, float], bool]:
    """Return (prices, priced) — priced is False when the model isn't in the table."""
    # Strip litellm provider prefix.
    slug = model.split("/")[-1].lower()
    if slug in _PRICE_TABLE:
        return _PRICE_TABLE[slug], True
    return _DEFAULT_PRICE, False


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
    priced: bool = True  # False means the model has no entry in _PRICE_TABLE

    def __str__(self) -> str:
        if not self.priced:
            return (
                f"${self.total_usd:.6f} (UNPRICED MODEL — cost not tracked, not $0) "
                f"(prompt=${self.prompt_usd:.6f}, completion=${self.completion_usd:.6f})"
            )
        return (
            f"${self.total_usd:.6f} "
            f"(prompt=${self.prompt_usd:.6f}, completion=${self.completion_usd:.6f})"
        )


def estimate_cost(usage: Usage, model: str) -> Cost:
    prices, priced = _price_for(model)
    if not priced:
        logger.warning(
            "No price entry for model %r — reporting $0 cost, which is NOT a "
            "confirmed free rate. Add this model to _PRICE_TABLE in verity.cost "
            "to track its cost accurately.",
            model,
        )
    prompt_usd = usage.prompt_tokens * prices["prompt"] / 1_000_000
    completion_usd = usage.completion_tokens * prices["completion"] / 1_000_000
    return Cost(
        prompt_usd=prompt_usd,
        completion_usd=completion_usd,
        total_usd=prompt_usd + completion_usd,
        priced=priced,
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
        all_priced = all(r.cost.priced for r in self.records)
        return Cost(
            prompt_usd=prompt,
            completion_usd=completion,
            total_usd=prompt + completion,
            priced=all_priced,
        )

    @property
    def unpriced_models(self) -> list[str]:
        """Distinct models in this run that have no confirmed price entry."""
        seen: list[str] = []
        for r in self.records:
            if not r.cost.priced and r.model not in seen:
                seen.append(r.model)
        return seen

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
        base = (
            f"Calls: {calls} | "
            f"Tokens: {t.total_tokens} "
            f"(prompt={t.prompt_tokens}, completion={t.completion_tokens}) | "
            f"Cost: {c}"
        )
        if not c.priced:
            models = ", ".join(self.unpriced_models)
            base += f" | WARNING: unpriced model(s) in this run: {models}"
        return base


def usage_from_litellm(response: Any) -> Usage:
    """Extract Usage from a litellm CompletionResponse."""
    u = response.usage
    return Usage(
        prompt_tokens=u.prompt_tokens or 0,
        completion_tokens=u.completion_tokens or 0,
        total_tokens=u.total_tokens or 0,
    )
