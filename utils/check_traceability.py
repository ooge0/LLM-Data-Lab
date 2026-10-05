"""
utils.check_traceability
===========================

The requirement-traceability gate for `tests/qa/catalogue.toml` (CLAUDE.md section 7's QA artifact).

Keeps the matrix honest without a human re-checking it by hand: it reads the `@pytest.mark.req("REQ-...")`
markers off the collected test suite (collection only -- nothing is executed) and fails if

- a catalogue requirement is covered by no real test and is not listed in `tests/qa/known_gaps.txt`,
- a requirement *is* covered but a stale `known_gaps.txt` line still claims it is a gap,
- a test names a `REQ-*` id that does not exist in the catalogue, or
- `known_gaps.txt` names a `REQ-*` id that does not exist in the catalogue.

A test that is itself `xfail` does not count as coverage -- it documents a known-wrong or
not-yet-implemented behavior (CLAUDE.md's own "pins today's known-wrong behavior" pattern), not a
verified requirement.

Run it with ``python -m utils.check_traceability`` (exit code 0 = pass, 1 = fail, with every
problem printed). There is no CI in this project (CLAUDE.md section 11's own disclosed gap), so
this is invoked by hand or via ``tox -e traceability``.
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path
from typing import Optional

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOGUE_PATH = REPO_ROOT / "tests" / "qa" / "catalogue.toml"
KNOWN_GAPS_PATH = REPO_ROOT / "tests" / "qa" / "known_gaps.txt"
TESTS_DIR = REPO_ROOT / "tests"

_GAP_LINE_RE = re.compile(r"^(REQ-[A-Za-z0-9-]+)\s*\|\s*([^|]*)\|\s*(.+)$")


def load_catalogue(path: Path = CATALOGUE_PATH) -> tuple[dict, set[str]]:
    """Parse `catalogue.toml` and return (the raw parsed data, the set of every requirement id)."""
    with open(path, "rb") as fh:
        data = tomllib.load(fh)
    req_ids = {r["id"] for r in data.get("requirement", [])}
    return data, req_ids


def load_known_gaps(path: Path = KNOWN_GAPS_PATH) -> dict[str, dict[str, str]]:
    """
    Parse `known_gaps.txt` into ``{req_id: {"reason": ..., "condition": ...}}``.

    Blank lines and lines starting with ``#`` are ignored. Every other non-blank line must match
    ``REQ-ID | reason | closing condition`` -- a malformed line is a real authoring error, not
    silently skipped.
    """
    gaps: dict[str, dict[str, str]] = {}
    if not path.exists():
        return gaps
    for lineno, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = _GAP_LINE_RE.match(line)
        if not match:
            raise ValueError(
                f"{path}:{lineno}: malformed known_gaps.txt line (expected 'REQ-ID | reason | closing condition'): {raw_line!r}"
            )
        req_id, reason, condition = match.groups()
        gaps[req_id] = {"reason": reason.strip(), "condition": condition.strip()}
    return gaps


class _ReqMarkerCollector:
    """
    pytest plugin used only for collection (no tests are ever run): for every collected item,
    records which `REQ-*` ids its closest `req` marker names, and whether that item is itself
    xfail.

    ``get_closest_marker`` (not ``iter_markers``) is deliberate: a test-level
    ``@pytest.mark.req(...)`` overrides a module-level ``pytestmark = pytest.mark.req(...)``
    rather than adding to it, matching how the catalogue's test-binding table describes per-test
    overrides of a file's default requirement id.
    """

    def __init__(self) -> None:
        self.coverage: dict[str, list[str]] = {}
        self.all_marked_ids: set[str] = set()

    def pytest_collection_modifyitems(self, session, config, items) -> None:  # noqa: ARG002
        for item in items:
            req_marker = item.get_closest_marker("req")
            if req_marker is None:
                continue
            is_xfail = item.get_closest_marker("xfail") is not None
            for req_id in req_marker.args:
                self.all_marked_ids.add(req_id)
                if not is_xfail:
                    self.coverage.setdefault(req_id, []).append(item.nodeid)


def collect_requirement_coverage(pytest_args: Optional[list[str]] = None) -> tuple[dict[str, list[str]], set[str]]:
    """
    Collect (never run) the suite under ``tests/`` and return ``(coverage, all_marked_ids)``.

    ``coverage`` maps a requirement id to the node ids of its non-xfail covering tests.
    ``all_marked_ids`` is every id any test's ``req`` marker names, xfail or not -- used to catch a
    marker that misspells or invents a requirement id.
    """
    collector = _ReqMarkerCollector()
    args = ["--collect-only", "-q", *(pytest_args or [str(TESTS_DIR)])]
    exit_code = pytest.main(args, plugins=[collector])
    if exit_code not in (pytest.ExitCode.OK, pytest.ExitCode.NO_TESTS_COLLECTED):
        raise RuntimeError(f"pytest collection failed with exit code {exit_code!r}; cannot check traceability")
    return collector.coverage, collector.all_marked_ids


def check(
    catalogue_path: Path = CATALOGUE_PATH,
    known_gaps_path: Path = KNOWN_GAPS_PATH,
    pytest_args: Optional[list[str]] = None,
) -> list[str]:
    """
    Run every rule the gate enforces and return the list of problems found (empty = gate passes).

    Kept separate from ``main`` so a test can call it directly and assert on the returned list
    instead of parsing process output.
    """
    _, req_ids = load_catalogue(catalogue_path)
    gaps = load_known_gaps(known_gaps_path)
    coverage, all_marked_ids = collect_requirement_coverage(pytest_args)

    problems: list[str] = []

    unknown_markers = all_marked_ids - req_ids
    for req_id in sorted(unknown_markers):
        problems.append(f"a test's req marker names an id that is not in the catalogue: {req_id}")

    stale_gaps = set(gaps) - req_ids
    for req_id in sorted(stale_gaps):
        problems.append(f"known_gaps.txt names an id that is not in the catalogue (stale entry): {req_id}")

    for req_id in sorted(req_ids):
        is_covered = bool(coverage.get(req_id))
        is_known_gap = req_id in gaps
        if not is_covered and not is_known_gap:
            problems.append(f"requirement has no covering test and is not in known_gaps.txt: {req_id}")
        elif is_covered and is_known_gap:
            problems.append(
                f"requirement is covered by a real test but known_gaps.txt still lists it -- "
                f"the gap is closed, delete its known_gaps.txt line: {req_id}"
            )

    return problems


def main(argv: Optional[list[str]] = None) -> int:  # noqa: ARG001
    problems = check()
    if problems:
        print(f"Traceability gate FAILED ({len(problems)} problem(s)):", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print("Traceability gate passed: every catalogue requirement is covered by a real test or a documented gap.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
