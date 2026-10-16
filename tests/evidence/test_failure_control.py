"""Deliberate failed pytest case, guarded and explicitly invoked by CI."""

import os

import pytest

pytestmark = pytest.mark.evidence_control


def test_expected_failure_control() -> None:
    if os.environ.get("VERITY_EVIDENCE_FAILURE_CONTROL") != "1":
        pytest.skip("Only run when the controlled-failure evidence gate enables it")
    pytest.fail("VERITY_EVIDENCE_CONTROL_FAILURE: deliberate failure proves JUnit evidence")
