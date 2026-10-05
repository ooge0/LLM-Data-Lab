"""
Unit tests for :mod:`utils.generate_qa_docs`'s four page builders. Each takes a small, hand-built
catalogue dict (the same shape ``tomllib`` produces from ``catalogue.toml``, not parsed from a real
file) plus synthetic coverage/known-gaps data, so every case is exercised without touching the real
catalogue or running pytest collection.
"""

import docutils.frontend
import docutils.parsers.rst
import docutils.utils

from utils.generate_qa_docs import (
    build_coverage_by_feature_rst,
    build_feature_catalogue_rst,
    build_test_cases_rst,
    build_traceability_rst,
)

_CATALOGUE = {
    "epic": [{"id": "E", "name": "Epic One"}],
    "feature": [
        {"id": "FEAT-A", "epic": "E", "name": "Feature A"},
        {"id": "FEAT-B", "epic": "E", "name": "Feature B"},
    ],
    "requirement": [
        {"id": "REQ-COVERED", "feature": "FEAT-A", "value": "High", "text": "A covered requirement"},
        {"id": "REQ-GAP", "feature": "FEAT-B", "value": "Low", "text": "A documented gap"},
    ],
}

_KNOWN_GAPS = {"REQ-GAP": {"reason": "no data", "condition": "collect it"}}


def _assert_valid_rst(rst: str) -> None:
    settings = docutils.frontend.OptionParser(components=(docutils.parsers.rst.Parser,)).get_default_values()
    settings.report_level = 5
    doc = docutils.utils.new_document("<test>", settings)
    errors = []
    doc.reporter.system_message = lambda level, message, *a, **k: errors.append((level, message))
    docutils.parsers.rst.Parser().parse(rst, doc)
    assert not [e for e in errors if e[0] >= 3], errors


def test_build_feature_catalogue_rst_lists_every_requirement_under_its_feature_and_epic():
    """Every requirement appears once, grouped under its feature's name under its epic's heading."""
    rst = build_feature_catalogue_rst(_CATALOGUE)

    assert "Epic One" in rst
    assert "Feature A" in rst
    assert "Feature B" in rst
    assert "REQ-COVERED" in rst
    assert "REQ-GAP" in rst
    assert "A covered requirement" in rst
    _assert_valid_rst(rst)


def test_build_test_cases_rst_numbers_real_tests_and_adds_a_known_gaps_section():
    """A real (non-xfail) test gets a TC id and 'Automated' status; the gap gets a 'Not implemented' placeholder row."""
    records = [
        {
            "node_id": "tests/unit/test_foo.py::test_covers_it",
            "type": "Unit",
            "req_ids": ("REQ-COVERED",),
            "is_xfail": False,
            "doc": "Covers the requirement.",
        }
    ]

    rst = build_test_cases_rst(_CATALOGUE, _KNOWN_GAPS, records)

    assert "TC-UNIT-001" in rst
    assert "Covers the requirement." in rst
    assert "Automated" in rst
    assert "Known Gaps" in rst
    assert "REQ-GAP" in rst
    assert "Not implemented" in rst
    _assert_valid_rst(rst)


def test_build_test_cases_rst_marks_an_xfail_test_as_automated_xfail():
    """An xfail test still gets a TC row (it exists), but its status says so distinctly."""
    records = [
        {
            "node_id": "tests/unit/test_foo.py::test_known_broken",
            "type": "Unit",
            "req_ids": ("REQ-COVERED",),
            "is_xfail": True,
            "doc": "Known-broken, xfail.",
        }
    ]

    rst = build_test_cases_rst(_CATALOGUE, {}, records)

    assert "Automated (xfail)" in rst


def test_build_traceability_rst_reports_covered_and_gap_rows_with_the_right_summary_count():
    """REQ-COVERED shows Covered/Automated with its TC id; REQ-GAP shows Gap/Not implemented; summary says 1 of 2."""
    coverage = {"REQ-COVERED": ["tests/unit/test_foo.py::test_covers_it"]}
    tc_ids = {"tests/unit/test_foo.py::test_covers_it": "TC-UNIT-001"}

    rst = build_traceability_rst(_CATALOGUE, _KNOWN_GAPS, coverage, tc_ids)

    assert "1 of 2 requirements" in rst
    assert "TC-UNIT-001" in rst
    assert "Covered" in rst
    assert "Gap" in rst
    _assert_valid_rst(rst)


def test_build_traceability_rst_flags_an_uncovered_requirement_not_in_known_gaps_as_undocumented():
    """A requirement with no test and no known_gaps.txt entry is a real, unflagged hole -- labelled distinctly."""
    rst = build_traceability_rst(_CATALOGUE, {}, {}, {})

    assert "GAP (undocumented)" in rst


def test_build_coverage_by_feature_rst_reports_fraction_and_percent_per_feature():
    """FEAT-A (its one requirement covered) shows 1/1, 100%; FEAT-B (its one requirement a gap) shows 0/1, 0%."""
    coverage = {"REQ-COVERED": ["tests/unit/test_foo.py::test_covers_it"]}

    rst = build_coverage_by_feature_rst(_CATALOGUE, coverage)

    assert "1/1" in rst
    assert "100%" in rst
    assert "0/1" in rst
    assert "0%" in rst
    _assert_valid_rst(rst)


def test_build_coverage_by_feature_rst_on_a_feature_with_no_requirements_reports_zero_not_a_crash():
    """A feature that (hypothetically) has no requirements yet reports 0/0, 0% rather than dividing by zero."""
    catalogue = {
        "epic": [{"id": "E", "name": "Epic One"}],
        "feature": [{"id": "FEAT-EMPTY", "epic": "E", "name": "Empty Feature"}],
        "requirement": [],
    }

    rst = build_coverage_by_feature_rst(catalogue, {})

    assert "0/0" in rst
    assert "0%" in rst
