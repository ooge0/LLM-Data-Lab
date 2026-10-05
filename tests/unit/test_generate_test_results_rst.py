"""
Unit tests for :mod:`utils.generate_test_results_rst` -- the junit.xml parser (``parse_junit``) and
the page builder (``build_test_results_rst``). No real pytest run is needed: a small, hand-written
junit.xml fixture stands in for a real one.
"""

import pytest

from utils.generate_test_results_rst import build_test_results_rst, parse_junit

_JUNIT_XML = """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" errors="1" failures="1" skipped="1" tests="4" time="1.500" timestamp="2026-10-02T12:00:00">
    <testcase classname="tests.unit.test_foo" name="test_passes" time="0.100"></testcase>
    <testcase classname="tests.unit.test_foo" name="test_fails" time="0.200">
      <failure message="assert 1 == 2">AssertionError</failure>
    </testcase>
    <testcase classname="tests.integration.test_bar" name="test_errors" time="0.300">
      <error message="boom">RuntimeError</error>
    </testcase>
    <testcase classname="tests.integration.test_bar" name="test_skipped" time="0.000">
      <skipped message="not applicable"></skipped>
    </testcase>
  </testsuite>
</testsuites>
"""


def test_parse_junit_raises_a_clear_message_when_the_file_is_missing(tmp_path):
    """A missing junit.xml is a clear instruction to run the suite first, not a traceback."""
    with pytest.raises(SystemExit, match="Run the suite with --junitxml first"):
        parse_junit(tmp_path / "does_not_exist.xml")


def test_parse_junit_reads_totals_and_per_case_status(tmp_path):
    """Totals and each case's status (passed/failed/error/skipped) are read correctly from real junit XML shape."""
    path = tmp_path / "junit.xml"
    path.write_text(_JUNIT_XML, encoding="utf-8")

    data = parse_junit(path)

    assert data["generated"] == "2026-10-02T12:00:00"
    assert data["totals"] == {
        "total": 4,
        "failed": 1,
        "error": 1,
        "skipped": 1,
        "passed": 1,
        "duration": 1.5,
    }
    statuses = {case["node_id"]: case["status"] for case in data["cases"]}
    assert statuses == {
        "tests/unit/test_foo.py::test_passes": "passed",
        "tests/unit/test_foo.py::test_fails": "failed",
        "tests/integration/test_bar.py::test_errors": "error",
        "tests/integration/test_bar.py::test_skipped": "skipped",
    }


def test_build_test_results_rst_includes_the_summary_and_a_section_per_type(tmp_path):
    """The rendered page has a summary table and one section per test type present in the junit data."""
    path = tmp_path / "junit.xml"
    path.write_text(_JUNIT_XML, encoding="utf-8")
    junit_data = parse_junit(path)
    coverage = {"REQ-FOO": ["tests/unit/test_foo.py::test_passes"]}

    rst = build_test_results_rst(junit_data, coverage)

    assert "Test Results" in rst
    assert "Unit" in rst
    assert "Integration" in rst
    assert "REQ-FOO" in rst
    assert "TC-UNIT-001" in rst  # test_passes is the only unit case, numbered first
    assert "failed" in rst and "error" in rst and "skipped" in rst


def test_build_test_results_rst_is_valid_rst(tmp_path):
    """The generated page parses as real RST (list-table structure is well-formed)."""
    import docutils.frontend
    import docutils.parsers.rst
    import docutils.utils

    path = tmp_path / "junit.xml"
    path.write_text(_JUNIT_XML, encoding="utf-8")
    rst = build_test_results_rst(parse_junit(path), {})

    settings = docutils.frontend.OptionParser(components=(docutils.parsers.rst.Parser,)).get_default_values()
    settings.report_level = 5
    doc = docutils.utils.new_document("test_results.rst", settings)
    errors = []
    doc.reporter.system_message = lambda level, message, *a, **k: errors.append((level, message))
    docutils.parsers.rst.Parser().parse(rst, doc)

    assert not [e for e in errors if e[0] >= 3]
