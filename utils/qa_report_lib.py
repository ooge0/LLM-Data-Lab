"""
utils.qa_report_lib
=======================

Pure, unit-tested building blocks shared by :mod:`utils.generate_qa_docs` (the feature-catalogue,
test-cases, traceability and coverage-by-feature pages) and :mod:`utils.generate_test_results_rst`
(the test-results page). Kept separate from both generator scripts so the parts the plan calls out
for testing -- TC numbering, status rendering, table rendering -- are plain functions a test can
call directly, with no pytest subprocess or file I/O involved.

Everything that actually touches the filesystem or runs pytest lives in the two generator scripts,
not here.
"""

from __future__ import annotations

from typing import Optional

import pytest

TEST_TYPE_BY_DIR = {
    "unit": "Unit",
    "integration": "Integration",
    "e2e": "E2E",
    "legacy_rag": "Legacy RAG",
}

# The order sections appear in on every generated page -- unit first (the largest, fastest layer),
# ending with the slowest/most indirect one, matching CLAUDE.md SS7's own "unit, functional, API,
# E2E" layering.
TEST_TYPE_ORDER = ["Unit", "Integration", "E2E", "Legacy RAG"]


def type_from_node_id(node_id: str) -> str:
    """
    Return the test's type ("Unit", "Integration", "E2E", "Legacy RAG") from its node id.

    Parameters
    ----------
    node_id : str
        A pytest node id, e.g. ``tests/unit/test_foo.py::test_bar``.

    Raises
    ------
    ValueError
        If the node id's path does not start with ``tests/<known-dir>/``.
    """
    parts = node_id.replace("\\", "/").split("/")
    if len(parts) < 2 or parts[0] != "tests" or parts[1] not in TEST_TYPE_BY_DIR:
        raise ValueError(f"node id does not look like tests/<dir>/...: {node_id!r}")
    return TEST_TYPE_BY_DIR[parts[1]]


def assign_tc_ids(node_ids_by_type: dict[str, list[str]]) -> dict[str, str]:
    """
    Assign a stable ``TC-<TYPE>-<NNN>`` id to every node id, numbered sequentially within its type
    in the order given.

    Parameters
    ----------
    node_ids_by_type : dict[str, list[str]]
        Each type's node ids, already in the order they should be numbered in (collection order).

    Returns
    -------
    dict[str, str]
        node_id -> TC id.

    Notes
    -----
    TC numbers are assigned by this function every time it runs and shift whenever a test is added,
    removed, or reordered -- they are a display convenience for this page, not a stable identifier
    other pages may reference by number. Only ``REQ-*`` ids are stable cross-references.
    """
    tc_ids: dict[str, str] = {}
    for test_type, node_ids in node_ids_by_type.items():
        prefix = test_type.upper().replace(" ", "")
        for i, node_id in enumerate(node_ids, start=1):
            tc_ids[node_id] = f"TC-{prefix}-{i:03d}"
    return tc_ids


def status_label(is_covered: bool, is_xfail: bool = False) -> str:
    """
    Render a test-case/requirement's status as one of the project's three fixed labels.

    Parameters
    ----------
    is_covered : bool
        Whether a real (non-xfail) test exists for this row.
    is_xfail : bool
        Whether the test that exists is itself xfail (CLAUDE.md's "pins a known-wrong or
        not-yet-implemented behavior" pattern) -- only meaningful when ``is_covered`` is True.
    """
    if not is_covered:
        return "Not implemented"
    return "Automated (xfail)" if is_xfail else "Automated"


def first_docstring_line(doc: Optional[str]) -> str:
    """Return the first non-blank line of a docstring, or a fixed placeholder if there is none."""
    if not doc:
        return "(no docstring)"
    for line in doc.strip().splitlines():
        line = line.strip()
        if line:
            return line
    return "(no docstring)"


def render_list_table(headers: list[str], rows: list[list[str]], widths: Optional[list[int]] = None) -> str:
    """
    Render a Sphinx ``.. list-table::`` directive from a header row and data rows.

    Parameters
    ----------
    headers : list[str]
        Column headers.
    rows : list[list[str]]
        Each row's cell values, same length as ``headers``.
    widths : list[int], optional
        Relative column widths; defaults to equal widths.

    Returns
    -------
    str
        RST source for the table, with no leading/trailing blank lines (the caller places it in
        the page).
    """
    for row in rows:
        if len(row) != len(headers):
            raise ValueError(f"row has {len(row)} cells, expected {len(headers)}: {row!r}")
    widths = widths or [1] * len(headers)
    width_str = " ".join(str(w) for w in widths)
    lines = [".. list-table::", f"   :widths: {width_str}", "   :header-rows: 1", ""]
    for row_cells in [headers, *rows]:
        for i, cell in enumerate(row_cells):
            marker = "*" if i == 0 else " "
            lines.append(f"   {marker} - {cell}")
    return "\n".join(lines)


def build_coverage(records: list[dict]) -> dict[str, list[str]]:
    """
    Derive ``{req_id: [node_id, ...]}`` directly from :func:`collect_test_records`' output, so
    callers that already collected the richer records do not need a second pytest collection pass
    just to get coverage (the simpler coverage-only pass lives separately in
    :func:`utils.check_traceability.collect_requirement_coverage`, for callers that only need that).

    An xfail test's req ids are not counted as coverage, matching
    :mod:`utils.check_traceability`'s own rule.
    """
    coverage: dict[str, list[str]] = {}
    for record in records:
        if record["is_xfail"]:
            continue
        for req_id in record["req_ids"]:
            coverage.setdefault(req_id, []).append(record["node_id"])
    return coverage


class _QaTestCollector:
    """
    pytest plugin used only for collection (no tests are ever executed): records, for every
    collected item, the fields :mod:`utils.generate_qa_docs` needs -- its ``req`` marker ids, its
    type (derived from its node id's top test directory), whether it is itself xfail, and its first
    docstring line.
    """

    def __init__(self) -> None:
        self.records: list[dict] = []

    def pytest_collection_modifyitems(self, session, config, items) -> None:  # noqa: ARG002
        for item in items:
            req_marker = item.get_closest_marker("req")
            req_ids = tuple(req_marker.args) if req_marker is not None else ()
            is_xfail = item.get_closest_marker("xfail") is not None
            func = getattr(item, "function", None)
            doc = getattr(func, "__doc__", None) if func is not None else None
            try:
                test_type = type_from_node_id(item.nodeid)
            except ValueError:
                continue  # not one of the known tests/<dir>/ layers (shouldn't happen in this repo)
            self.records.append(
                {
                    "node_id": item.nodeid,
                    "type": test_type,
                    "req_ids": req_ids,
                    "is_xfail": is_xfail,
                    "doc": doc,
                }
            )


def collect_test_records(pytest_args: Optional[list[str]] = None, tests_dir: str = "tests") -> list[dict]:
    """
    Collect (never run) the suite and return one record per test, in collection order.

    Each record has ``node_id``, ``type``, ``req_ids`` (tuple, possibly empty), ``is_xfail``, and
    ``doc`` (the raw docstring, or ``None``).
    """
    collector = _QaTestCollector()
    args = ["--collect-only", "-q", *(pytest_args or [tests_dir])]
    exit_code = pytest.main(args, plugins=[collector])
    if exit_code not in (pytest.ExitCode.OK, pytest.ExitCode.NO_TESTS_COLLECTED):
        raise RuntimeError(f"pytest collection failed with exit code {exit_code!r}")
    return collector.records
