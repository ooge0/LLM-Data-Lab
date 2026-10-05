"""
Unit tests for :mod:`utils.qa_report_lib` -- the pure helpers behind the generated QA pages
(``utils/generate_qa_docs.py``, ``utils/generate_test_results_rst.py``). No pytest files are
written or run through a subprocess here: ``type_from_node_id``, ``assign_tc_ids``,
``status_label``, ``first_docstring_line`` and ``render_list_table`` are exercised directly on
fixed inputs, and the collection plugin is exercised against fake items the same way
``tests/unit/test_check_traceability.py`` exercises its own collector.
"""

import pytest

from utils.qa_report_lib import (
    _QaTestCollector,
    assign_tc_ids,
    build_coverage,
    first_docstring_line,
    render_list_table,
    status_label,
    type_from_node_id,
)

# Infrastructure test -- see tests/unit/test_check_traceability.py's own comment on why files like
# this one carry no req marker: they test the QA tooling itself, not an application requirement.


def test_type_from_node_id_maps_every_known_directory():
    """Each of the four real test directories maps to its documented display name."""
    assert type_from_node_id("tests/unit/test_foo.py::test_bar") == "Unit"
    assert type_from_node_id("tests/integration/test_foo.py::test_bar") == "Integration"
    assert type_from_node_id("tests/e2e/test_foo.py::test_bar") == "E2E"
    assert type_from_node_id("tests/legacy_rag/test_foo.py::test_bar") == "Legacy RAG"


def test_type_from_node_id_rejects_an_unknown_directory():
    """A node id outside the four known test directories is a real error, not silently skipped here (the caller skips it)."""
    with pytest.raises(ValueError, match="does not look like"):
        type_from_node_id("scripts/test_something.py::test_x")


def test_assign_tc_ids_numbers_sequentially_per_type_starting_at_one():
    """Each type gets its own TC-<TYPE>-NNN sequence, zero-padded to three digits, starting at 001."""
    tc_ids = assign_tc_ids(
        {
            "Unit": ["tests/unit/a.py::test_1", "tests/unit/a.py::test_2"],
            "E2E": ["tests/e2e/b.py::test_3"],
        }
    )

    assert tc_ids == {
        "tests/unit/a.py::test_1": "TC-UNIT-001",
        "tests/unit/a.py::test_2": "TC-UNIT-002",
        "tests/e2e/b.py::test_3": "TC-E2E-001",
    }


def test_assign_tc_ids_on_a_type_with_no_tests_assigns_nothing():
    """An empty list for a type contributes zero entries, not a crash or an off-by-one id."""
    tc_ids = assign_tc_ids({"Legacy RAG": []})

    assert tc_ids == {}


def test_status_label_three_fixed_outcomes():
    """Not covered -> Not implemented; covered and real -> Automated; covered but xfail -> Automated (xfail)."""
    assert status_label(is_covered=False) == "Not implemented"
    assert status_label(is_covered=True, is_xfail=False) == "Automated"
    assert status_label(is_covered=True, is_xfail=True) == "Automated (xfail)"


def test_first_docstring_line_strips_and_takes_the_first_non_blank_line():
    """A multi-line docstring with leading blank lines/whitespace still yields a clean first line."""
    doc = "\n\n   A real one-line summary.\n\n    Longer body text here.\n    "

    assert first_docstring_line(doc) == "A real one-line summary."


def test_first_docstring_line_on_none_or_empty_returns_the_fixed_placeholder():
    """A test with no docstring at all gets an honest placeholder, not a crash or a blank cell."""
    assert first_docstring_line(None) == "(no docstring)"
    assert first_docstring_line("   \n  \n") == "(no docstring)"


def test_render_list_table_produces_valid_rst_structure():
    """The rendered text is a real `.. list-table::` directive with one '* -' row start per data row."""
    rst = render_list_table(["A", "B"], [["1", "2"], ["3", "4"]])

    assert rst.splitlines()[0] == ".. list-table::"
    assert ":header-rows: 1" in rst
    # one row-start marker ("* -") per header row + per data row = 3 total
    assert rst.count("* -") == 3
    assert "- 1" in rst and "- 4" in rst


def test_render_list_table_rejects_a_row_with_the_wrong_number_of_cells():
    """A malformed row (wrong cell count) is a real authoring error in the generator, caught immediately."""
    with pytest.raises(ValueError, match="expected 2"):
        render_list_table(["A", "B"], [["only-one-cell"]])


def test_build_coverage_groups_node_ids_by_req_id_and_excludes_xfail():
    """A non-xfail test's req ids all gain its node id; an xfail test's req ids gain nothing."""
    records = [
        {"node_id": "tests/unit/a.py::test_1", "req_ids": ("REQ-X", "REQ-Y"), "is_xfail": False},
        {"node_id": "tests/unit/a.py::test_2", "req_ids": ("REQ-X",), "is_xfail": False},
        {"node_id": "tests/unit/a.py::test_3", "req_ids": ("REQ-Z",), "is_xfail": True},
    ]

    coverage = build_coverage(records)

    assert coverage == {
        "REQ-X": ["tests/unit/a.py::test_1", "tests/unit/a.py::test_2"],
        "REQ-Y": ["tests/unit/a.py::test_1"],
    }
    assert "REQ-Z" not in coverage


class _FakeMarker:
    def __init__(self, *args):
        self.args = args


class _FakeFunc:
    __doc__ = "A fake test's docstring."


class _FakeItem:
    def __init__(self, nodeid, req_ids=(), xfail=False, has_func=True):
        self.nodeid = nodeid
        self._req = _FakeMarker(*req_ids) if req_ids else None
        self._xfail = xfail
        self.function = _FakeFunc() if has_func else None

    def get_closest_marker(self, name):
        if name == "req":
            return self._req
        if name == "xfail" and self._xfail:
            return object()
        return None


def test_qa_test_collector_records_type_req_ids_xfail_and_docstring():
    """The collection plugin builds one record per item with every field generate_qa_docs needs."""
    collector = _QaTestCollector()
    items = [
        _FakeItem("tests/unit/test_a.py::test_one", req_ids=("REQ-X",)),
        _FakeItem("tests/e2e/test_b.py::test_two", req_ids=(), xfail=True),
    ]
    collector.pytest_collection_modifyitems(session=None, config=None, items=items)

    assert len(collector.records) == 2
    first, second = collector.records
    assert first["node_id"] == "tests/unit/test_a.py::test_one"
    assert first["type"] == "Unit"
    assert first["req_ids"] == ("REQ-X",)
    assert first["is_xfail"] is False
    assert first["doc"] == "A fake test's docstring."
    assert second["type"] == "E2E"
    assert second["is_xfail"] is True


def test_qa_test_collector_skips_items_outside_the_known_test_directories():
    """An item whose node id isn't under tests/<known-dir>/ is silently excluded, not a crash."""
    collector = _QaTestCollector()
    items = [_FakeItem("scripts/test_outside.py::test_x")]
    collector.pytest_collection_modifyitems(session=None, config=None, items=items)

    assert collector.records == []
