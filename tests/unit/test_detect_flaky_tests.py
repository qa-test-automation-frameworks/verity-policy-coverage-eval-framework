"""Unit tests for the flake-detection script's pure parsing/aggregation logic."""

from __future__ import annotations

from pathlib import Path

from scripts.detect_flaky_tests import detect_flaky, parse_junit_outcomes

_JUNIT_ALL_PASS = """\
<testsuite>
  <testcase classname="tests.test_a" name="test_one"></testcase>
  <testcase classname="tests.test_a" name="test_two"></testcase>
</testsuite>
"""

_JUNIT_ONE_FAIL = """\
<testsuite>
  <testcase classname="tests.test_a" name="test_one">
    <failure message="boom">AssertionError</failure>
  </testcase>
  <testcase classname="tests.test_a" name="test_two"></testcase>
</testsuite>
"""

_JUNIT_ONE_ERROR = """\
<testsuite>
  <testcase classname="tests.test_a" name="test_one">
    <error message="boom">RuntimeError</error>
  </testcase>
</testsuite>
"""

_JUNIT_ONE_SKIPPED = """\
<testsuite>
  <testcase classname="tests.test_a" name="test_one">
    <skipped message="no key"></skipped>
  </testcase>
</testsuite>
"""


def _write(tmp_path: Path, name: str, content: str) -> Path:
    out = tmp_path / name
    out.write_text(content)
    return out


class TestParseJunitOutcomes:
    def test_passing_testcase_has_no_child_elements(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "pass.xml", _JUNIT_ALL_PASS)
        outcomes = parse_junit_outcomes(path)
        assert outcomes == {
            "tests.test_a::test_one": "passed",
            "tests.test_a::test_two": "passed",
        }

    def test_failure_element_reports_failed(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "fail.xml", _JUNIT_ONE_FAIL)
        outcomes = parse_junit_outcomes(path)
        assert outcomes["tests.test_a::test_one"] == "failed"
        assert outcomes["tests.test_a::test_two"] == "passed"

    def test_error_element_reports_error(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "error.xml", _JUNIT_ONE_ERROR)
        outcomes = parse_junit_outcomes(path)
        assert outcomes["tests.test_a::test_one"] == "error"

    def test_skipped_element_reports_skipped(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "skip.xml", _JUNIT_ONE_SKIPPED)
        outcomes = parse_junit_outcomes(path)
        assert outcomes["tests.test_a::test_one"] == "skipped"


class TestDetectFlaky:
    def test_consistently_passing_test_is_not_flaky(self) -> None:
        runs = [{"t1": "passed"}, {"t1": "passed"}, {"t1": "passed"}]
        report = detect_flaky(runs)
        assert report["t1"]["flaky"] is False

    def test_consistently_failing_test_is_not_flaky(self) -> None:
        runs = [{"t1": "failed"}, {"t1": "failed"}]
        report = detect_flaky(runs)
        assert report["t1"]["flaky"] is False

    def test_pass_then_fail_is_flaky(self) -> None:
        runs = [{"t1": "passed"}, {"t1": "failed"}, {"t1": "passed"}]
        report = detect_flaky(runs)
        assert report["t1"]["flaky"] is True

    def test_pass_then_error_is_flaky(self) -> None:
        runs = [{"t1": "passed"}, {"t1": "error"}]
        report = detect_flaky(runs)
        assert report["t1"]["flaky"] is True

    def test_skip_only_test_is_not_flaky(self) -> None:
        runs = [{"t1": "skipped"}, {"t1": "skipped"}]
        report = detect_flaky(runs)
        assert report["t1"]["flaky"] is False

    def test_test_missing_from_some_runs_recorded_as_not_run(self) -> None:
        runs = [{"t1": "passed"}, {}]
        report = detect_flaky(runs)
        assert report["t1"]["outcomes"] == ["passed", "not_run"]
        assert report["t1"]["flaky"] is False

    def test_report_covers_union_of_all_test_ids_across_runs(self) -> None:
        runs = [{"t1": "passed"}, {"t2": "passed"}]
        report = detect_flaky(runs)
        assert set(report.keys()) == {"t1", "t2"}
