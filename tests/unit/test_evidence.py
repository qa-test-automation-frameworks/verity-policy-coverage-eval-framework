from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.evidence import EvidenceError, make_record, parse_junit
from scripts.validate_evidence import validate_record
from scripts.verify_failure_control import verify

ENV = {
    "GITHUB_SHA": "a" * 40,
    "GITHUB_RUN_ID": "123456789",
    "GITHUB_RUN_ATTEMPT": "1",
    "GITHUB_REPOSITORY": "qa-test-automation-frameworks/verity-policy-coverage-eval-framework",
    "GITHUB_WORKFLOW": "PR Gate",
    "GITHUB_WORKFLOW_REF": (
        "qa-test-automation-frameworks/verity-policy-coverage-eval-framework/"
        ".github/workflows/pr-gate.yml@refs/pull/1/merge"
    ),
    "GITHUB_REF_NAME": "1/merge",
    "GITHUB_EVENT_NAME": "pull_request",
    "EVIDENCE_STARTED_AT": "2026-10-16T10:00:00Z",
    "PYTHON_VERSION": "3.12.15",
    "UV_VERSION": "0.12.23",
    "PYTEST_VERSION": "9.0.2",
}


class EvidenceTests(unittest.TestCase):
    def write_xml(self, directory: str, name: str, content: str) -> Path:
        path = Path(directory) / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_junit_case_outcomes_are_counted_by_case(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = self.write_xml(
                directory,
                "results.xml",
                """<testsuites tests="4" failures="1" errors="0" skipped="1">
                  <testsuite name="deterministic" tests="4" failures="1" errors="0" skipped="1">
                    <testcase classname="suite" name="pass-a" />
                    <testcase classname="suite" name="failure">
                      <failure message="expected" />
                    </testcase>
                    <testcase classname="suite" name="skip"><skipped /></testcase>
                    <testcase classname="suite" name="pass-b" />
                  </testsuite>
                </testsuites>""",
            )
            record = make_record("verity.deterministic-py3.12.15", ENV, junit=report)
        self.assertEqual(record["execution"]["disposition"], "failed")
        self.assertEqual(
            record["execution"]["counts"],
            {
                "unit": "test_case",
                "selected": 4,
                "executed": 3,
                "passed": 2,
                "failed": 1,
                "skipped": 1,
                "retried": 0,
                "semantics": (
                    "JUnit testcase invocations; selected includes skips; errors count as failures."
                ),
            },
        )

    def test_complete_passing_junit_becomes_current_pass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = self.write_xml(
                directory,
                "results.xml",
                (
                    '<testsuite name="unit" tests="2"><testcase name="one"/>'
                    '<testcase name="two"/></testsuite>'
                ),
            )
            env = {**ENV, "PYTHON_VERSION": "3.13.16"}
            record = make_record("verity.deterministic-py3.13.16", env, junit=report)
        self.assertEqual(record["execution"]["disposition"], "passed")
        self.assertEqual(record["execution"]["integrity"], "complete")
        self.assertEqual(
            record["execution"]["shards"]["received"], ["verity.deterministic-py3.13.16"]
        )
        self.assertEqual(
            record["target"]["tools"],
            {"python": "3.13.16", "uv": "0.12.23", "pytest": "9.0.2"},
        )

    def test_empty_and_partial_junit_are_not_passed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            empty = self.write_xml(directory, "empty.xml", '<testsuite name="empty" tests="0"/>')
            empty_record = make_record("verity.empty", ENV, junit=empty)
            partial = self.write_xml(
                directory,
                "partial.xml",
                '<testsuite name="partial" tests="2"><testcase name="one"/></testsuite>',
            )
            partial_record = make_record("verity.partial", ENV, junit=partial)
        self.assertEqual(empty_record["execution"]["disposition"], "unavailable")
        self.assertEqual(empty_record["execution"]["integrity"], "empty")
        self.assertEqual(empty_record["execution"]["counts"]["selected"], 0)
        self.assertIsNotNone(empty_record["execution"]["startedAt"])
        self.assertIsNotNone(empty_record["execution"]["completedAt"])
        self.assertEqual(partial_record["execution"]["disposition"], "unavailable")
        self.assertEqual(partial_record["execution"]["integrity"], "partial")
        self.assertIsNone(partial_record["execution"]["counts"]["selected"])

    def test_missing_junit_and_missing_source_are_rejected(self) -> None:
        with (
            tempfile.TemporaryDirectory() as directory,
            self.assertRaisesRegex(EvidenceError, "missing or malformed"),
        ):
            parse_junit(Path(directory) / "missing.xml")
        with self.assertRaisesRegex(EvidenceError, "source identity"):
            make_record("verity.invalid", {**ENV, "GITHUB_SHA": "unknown"}, skip_reason="no key")

    def test_credentialed_no_key_run_has_null_counts_and_no_timestamps(self) -> None:
        env = {
            **ENV,
            "EVIDENCE_CLASS": "credentialed",
            "EVIDENCE_REQUIRED": "false",
            "EVIDENCE_FRESHNESS_POLICY": "quarterly_experiment_v1",
        }
        record = make_record(
            "verity.semantic-evaluation", env, skip_reason="No provider key configured"
        )
        execution = record["execution"]
        self.assertEqual(execution["disposition"], "skipped")
        self.assertIsNone(execution["startedAt"])
        self.assertIsNone(execution["completedAt"])
        self.assertIsNone(execution["counts"]["executed"])
        self.assertEqual(execution["measurements"], [])

    def test_attempted_run_without_native_results_is_unavailable(self) -> None:
        record = make_record(
            "verity.semantic-evaluation",
            ENV,
            unavailable_reason="Semantic result manifest was not generated",
        )
        execution = record["execution"]
        self.assertEqual(execution["disposition"], "unavailable")
        self.assertEqual(execution["integrity"], "unavailable")
        self.assertIsNotNone(execution["startedAt"])
        self.assertIsNotNone(execution["completedAt"])
        self.assertIsNone(execution["counts"]["executed"])
        self.assertEqual(execution["measurements"], [])

    def test_failure_control_requires_exact_expected_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = self.write_xml(
                directory,
                "control.xml",
                """<testsuite name="failure-control" tests="1" failures="1" errors="0" skipped="0">
                  <testcase name="test_expected_failure_control">
                    <failure message="deliberate">VERITY_EVIDENCE_CONTROL_FAILURE</failure>
                  </testcase>
                </testsuite>""",
            )
            verify(report, 1)
            with self.assertRaisesRegex(ValueError, "exit 1"):
                verify(report, 0)

    def test_parse_junit_rejects_suite_level_outcome_count_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = self.write_xml(
                directory,
                "results.xml",
                (
                    '<testsuite name="x" tests="1" failures="4">'
                    '<testcase name="one"><failure/></testcase></testsuite>'
                ),
            )
            self.assertEqual(parse_junit(report)["state"], "partial")

    def test_schema_and_semantics_accept_all_execution_dispositions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            passing_xml = self.write_xml(
                directory,
                "passing.xml",
                '<testsuite name="unit" tests="1"><testcase name="pass"/></testsuite>',
            )
            failed_xml = self.write_xml(
                directory,
                "failed.xml",
                '<testsuite name="unit" tests="1" failures="1">'
                '<testcase name="fail"><failure/></testcase></testsuite>',
            )
            records = [
                make_record("verity.pass", ENV, junit=passing_xml),
                make_record("verity.fail", ENV, junit=failed_xml),
                make_record("verity.skip", ENV, skip_reason="No provider key configured"),
                make_record("verity.unavailable", ENV, unavailable_reason="No JUnit report"),
            ]
        for record in records:
            self.assertEqual(validate_record(record), [])

    def test_schema_semantics_reject_pass_with_failed_case(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = self.write_xml(
                directory,
                "failed.xml",
                '<testsuite name="unit" tests="1" failures="1">'
                '<testcase name="fail"><failure/></testcase></testsuite>',
            )
            record = make_record("verity.fail", ENV, junit=report)
        record["execution"]["disposition"] = "passed"
        self.assertTrue(validate_record(record))


if __name__ == "__main__":
    unittest.main()
