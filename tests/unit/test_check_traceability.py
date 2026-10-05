"""
Unit tests for :mod:`utils.check_traceability` -- the QA traceability gate itself. Uses small,
throwaway catalogue/known_gaps files and a fake pytest plugin result instead of the real
`tests/qa/catalogue.toml` (over a hundred requirements), so each rule is exercised in isolation on
a input small enough to reason about by eye.
"""

import pytest

from utils.check_traceability import check, load_catalogue, load_known_gaps

# No pytestmark here: this file tests the traceability checker itself, which has no corresponding
# catalogue requirement (REQ-OPS-DOC-02 is specifically about utils/list_tests.py, a different
# script -- tagging this file with it would make the gate think that known gap is closed).

_CATALOGUE = """
schema_version = 1

[[epic]]
id = "E"
name = "Epic"

[[feature]]
id = "F"
epic = "E"
name = "Feature"

[[requirement]]
id = "REQ-COVERED"
feature = "F"
value = "High"
text = "A covered requirement"

[[requirement]]
id = "REQ-GAP"
feature = "F"
value = "Low"
text = "A documented gap"
known_gap = true
"""


def _write_catalogue(tmp_path, text=_CATALOGUE):
    path = tmp_path / "catalogue.toml"
    path.write_text(text, encoding="utf-8")
    return path


def _write_gaps(tmp_path, text):
    path = tmp_path / "known_gaps.txt"
    path.write_text(text, encoding="utf-8")
    return path


def test_load_catalogue_returns_every_requirement_id(tmp_path):
    """load_catalogue returns the full parsed data plus the flat set of every requirement id."""
    path = _write_catalogue(tmp_path)

    data, req_ids = load_catalogue(path)

    assert req_ids == {"REQ-COVERED", "REQ-GAP"}
    assert len(data["requirement"]) == 2


def test_load_known_gaps_parses_well_formed_lines(tmp_path):
    """Each 'REQ-ID | reason | condition' line becomes one dict entry; comments and blanks are skipped."""
    path = _write_gaps(
        tmp_path,
        "# a comment\n\nREQ-GAP | no data yet | collect real data\n",
    )

    gaps = load_known_gaps(path)

    assert gaps == {"REQ-GAP": {"reason": "no data yet", "condition": "collect real data"}}


def test_load_known_gaps_on_a_missing_file_returns_empty_dict(tmp_path):
    """A project with no known_gaps.txt yet (or a typo'd path) is treated as zero gaps, not an error."""
    gaps = load_known_gaps(tmp_path / "does_not_exist.txt")

    assert gaps == {}


def test_load_known_gaps_rejects_a_malformed_line(tmp_path):
    """A line that isn't comment/blank and doesn't match 'ID | reason | condition' is a real authoring error."""
    path = _write_gaps(tmp_path, "REQ-GAP this line has no pipes at all\n")

    with pytest.raises(ValueError, match="malformed known_gaps.txt line"):
        load_known_gaps(path)


def test_check_passes_when_every_requirement_is_covered_or_a_documented_gap(tmp_path, monkeypatch):
    """The gate passes with zero problems when REQ-COVERED has a real test and REQ-GAP is listed."""
    catalogue_path = _write_catalogue(tmp_path)
    gaps_path = _write_gaps(tmp_path, "REQ-GAP | no data yet | collect real data\n")
    monkeypatch.setattr(
        "utils.check_traceability.collect_requirement_coverage",
        lambda pytest_args=None: ({"REQ-COVERED": ["tests/test_x.py::test_a"]}, {"REQ-COVERED"}),
    )

    problems = check(catalogue_path=catalogue_path, known_gaps_path=gaps_path)

    assert problems == []


def test_check_flags_a_requirement_with_no_test_and_no_known_gap(tmp_path, monkeypatch):
    """REQ-GAP without a known_gaps.txt entry and without a covering test is a real, unflagged hole."""
    catalogue_path = _write_catalogue(tmp_path)
    gaps_path = _write_gaps(tmp_path, "")
    monkeypatch.setattr(
        "utils.check_traceability.collect_requirement_coverage",
        lambda pytest_args=None: ({"REQ-COVERED": ["tests/test_x.py::test_a"]}, {"REQ-COVERED"}),
    )

    problems = check(catalogue_path=catalogue_path, known_gaps_path=gaps_path)

    assert any("REQ-GAP" in p and "no covering test" in p for p in problems)


def test_check_flags_a_closed_gap_still_listed_in_known_gaps(tmp_path, monkeypatch):
    """REQ-GAP now has a real covering test but is still in known_gaps.txt -- the stale line must be caught."""
    catalogue_path = _write_catalogue(tmp_path)
    gaps_path = _write_gaps(tmp_path, "REQ-GAP | no data yet | collect real data\n")
    monkeypatch.setattr(
        "utils.check_traceability.collect_requirement_coverage",
        lambda pytest_args=None: (
            {"REQ-COVERED": ["tests/test_x.py::test_a"], "REQ-GAP": ["tests/test_y.py::test_b"]},
            {"REQ-COVERED", "REQ-GAP"},
        ),
    )

    problems = check(catalogue_path=catalogue_path, known_gaps_path=gaps_path)

    assert any("REQ-GAP" in p and "gap is closed" in p for p in problems)


def test_check_flags_a_test_marker_naming_an_unknown_requirement_id(tmp_path, monkeypatch):
    """A req marker spelling or inventing an id that is not in the catalogue is caught, not silently ignored."""
    catalogue_path = _write_catalogue(tmp_path)
    gaps_path = _write_gaps(tmp_path, "REQ-GAP | no data yet | collect real data\n")
    monkeypatch.setattr(
        "utils.check_traceability.collect_requirement_coverage",
        lambda pytest_args=None: (
            {"REQ-COVERED": ["tests/test_x.py::test_a"]},
            {"REQ-COVERED", "REQ-TYPO-DOES-NOT-EXIST"},
        ),
    )

    problems = check(catalogue_path=catalogue_path, known_gaps_path=gaps_path)

    assert any("REQ-TYPO-DOES-NOT-EXIST" in p for p in problems)


def test_check_flags_a_stale_known_gaps_entry_naming_a_deleted_requirement(tmp_path, monkeypatch):
    """A known_gaps.txt line for a requirement id no longer in the catalogue is a stale entry, caught explicitly."""
    catalogue_path = _write_catalogue(tmp_path)
    gaps_path = _write_gaps(
        tmp_path,
        "REQ-GAP | no data yet | collect real data\nREQ-DELETED-LONG-AGO | stale | stale\n",
    )
    monkeypatch.setattr(
        "utils.check_traceability.collect_requirement_coverage",
        lambda pytest_args=None: ({"REQ-COVERED": ["tests/test_x.py::test_a"]}, {"REQ-COVERED"}),
    )

    problems = check(catalogue_path=catalogue_path, known_gaps_path=gaps_path)

    assert any("REQ-DELETED-LONG-AGO" in p and "stale entry" in p for p in problems)


def test_collect_requirement_coverage_excludes_xfail_tests_from_coverage():
    """An xfail test's req marker is recorded in all_marked_ids (so a typo'd id is still caught) but never
    counted as real coverage -- it documents a known-wrong or not-yet-implemented behavior, not a pass."""

    class _FakeMarker:
        def __init__(self, *args):
            self.args = args

    class _FakeItem:
        def __init__(self, nodeid, req_ids, xfail):
            self.nodeid = nodeid
            self._req = _FakeMarker(*req_ids)
            self._xfail = xfail

        def get_closest_marker(self, name):
            if name == "req":
                return self._req
            if name == "xfail" and self._xfail:
                return object()
            return None

    from utils.check_traceability import _ReqMarkerCollector

    collector = _ReqMarkerCollector()
    items = [
        _FakeItem("tests/test_a.py::test_real", ("REQ-REAL",), xfail=False),
        _FakeItem("tests/test_b.py::test_broken", ("REQ-XFAILED",), xfail=True),
    ]
    collector.pytest_collection_modifyitems(session=None, config=None, items=items)

    assert collector.coverage == {"REQ-REAL": ["tests/test_a.py::test_real"]}
    assert collector.all_marked_ids == {"REQ-REAL", "REQ-XFAILED"}
