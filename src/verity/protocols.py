"""Typed extension contracts for judges and metric factories."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol


class JudgeProtocol(Protocol):
    """Minimal provider-backed judge surface used by metric adapters."""

    @property
    def model_name(self) -> str: ...

    def generate(self, prompt: str) -> str: ...

    async def a_generate(self, prompt: str) -> str: ...


class MetricProtocol(Protocol):
    """Common callable surface for metric objects used in semantic tests."""

    score: float | int | None
    reason: str | None

    def measure(self, test_case: Any) -> Any: ...


type MetricFactory = Callable[..., MetricProtocol]
