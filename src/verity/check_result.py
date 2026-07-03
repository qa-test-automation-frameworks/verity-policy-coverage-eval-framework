"""Shared result type for deterministic checks."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CheckResult:
    passed: bool
    message: str = ""

    def __bool__(self) -> bool:
        return self.passed
