"""Deliberately failing tests used to feed chitra with real failure-shaped data.

Not part of the real suite's coverage story — this file exists only on the
`chitra/failure-fixtures` branch so we can exercise chitra's failure/lifecycle/
flaky reporting against a variety of real failure types (assertion, exception,
setup/config error, timeout, flaky) with multiple instances of each. Stash or
drop this branch when done; never merge it into a real branch.
"""

from __future__ import annotations

import signal
from pathlib import Path

import pytest

# --- assertion failures -----------------------------------------------------


def test_assertion_wrong_scalar() -> None:
    expected = 42
    actual = 41
    assert actual == expected


def test_assertion_wrong_collection() -> None:
    expected = {"policy_id": "ctrl-1", "status": "covered"}
    actual = {"policy_id": "ctrl-1", "status": "uncovered"}
    assert actual == expected


def test_assertion_membership() -> None:
    allowed_owners = ["team-payments", "team-identity"]
    assert "team-storefront" in allowed_owners


# --- unhandled exceptions ---------------------------------------------------


def test_raises_type_error() -> None:
    value: int | None = None
    _ = value + 1  # type: ignore[operator]


def test_raises_key_error() -> None:
    record = {"policy_id": "ctrl-1"}
    _ = record["expected_owner"]


def test_raises_zero_division() -> None:
    numerator = 10
    denominator = 0
    _ = numerator / denominator


# --- config / setup errors (fixture raises -> pytest "error", not "failure") -


@pytest.fixture()
def missing_provider_config():
    raise RuntimeError("required provider config 'VERITY_JUDGE_MODEL' is not set")


def test_config_error_provider(missing_provider_config) -> None:
    assert missing_provider_config is not None


@pytest.fixture()
def unreachable_policy_store():
    raise ConnectionError("could not reach policy store at policy-store.internal:8443")


def test_config_error_policy_store(unreachable_policy_store) -> None:
    assert unreachable_policy_store is not None


# --- timeout-shaped failures -------------------------------------------------


def test_timeout_policy_retrieval() -> None:
    def _on_alarm(signum, frame):
        raise TimeoutError("policy retrieval exceeded 1s budget")

    signal.signal(signal.SIGALRM, _on_alarm)
    signal.alarm(1)
    try:
        for _ in range(500_000_000):
            pass
    finally:
        signal.alarm(0)


# --- flaky: oscillates across sequential script invocations -----------------

_FLAKY_STATE_DIR = Path("/tmp/chitra-flaky-state")


def _next_count(name: str) -> int:
    _FLAKY_STATE_DIR.mkdir(parents=True, exist_ok=True)
    state_file = _FLAKY_STATE_DIR / f"verity-{name}.count"
    count = int(state_file.read_text()) if state_file.exists() else 0
    count += 1
    state_file.write_text(str(count))
    return count


def test_flaky_retriever_ordering() -> None:
    count = _next_count("retriever_ordering")
    assert count % 2 == 1, f"non-deterministic chunk ordering on invocation {count}"


def test_flaky_judge_latency_budget() -> None:
    count = _next_count("judge_latency_budget")
    assert count % 3 != 0, f"judge call exceeded latency budget on invocation {count}"


# --- regression: fails, gets "fixed", then breaks its own fix promise -------
#
# Invocations 1-2 fail (introduced/active), 3-4 pass (fixed), 5+ fail again
# (regressed, then active on any further run) -- exactly two status flips
# across the sequence, so it stays out of "intermittent" (min_oscillations=3).
# Needs *exactly* 5 ingested runs total so the latest persisted state is the
# fresh "regressed" transition itself, not the "active" state a 6th run would
# settle into -- stop seeding this fixture at 5 runs.
#
# (v2: a fresh test_key/counter -- an earlier attempt at this same fixture
# overshot to 6 runs and settled on "active"; rather than surgically edit the
# hash-chained lifecycle ledger, this starts a clean sequence.)


def test_policy_sync_promise_regression_v2() -> None:
    count = _next_count("policy_sync_promise_regression_v2")
    if count <= 2 or count >= 5:
        assert False, "policy replica drifted from source of truth"
