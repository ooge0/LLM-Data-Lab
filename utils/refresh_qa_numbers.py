"""
utils.refresh_qa_numbers
========================

Updates the auto-generated numeric blocks in ``docs/source/qa.rst`` and writes
``docs/source/_qa_coverage_table.rst`` from a live pytest + coverage run.

Run once after any test additions / deletions or a coverage-impacting code change::

    python -m utils.refresh_qa_numbers

What it updates
---------------
- ``docs/source/qa.rst``
  - "Test suite at a glance" table  (files / cases / lines of test code)
  - "Test suite breakdown" table    (per-category counts and percentages)
- ``docs/source/_qa_coverage_table.rst`` (included by qa.rst)
  - Coverage by package table

Then rebuilds Sphinx::

    sphinx-build docs/source docs/source/_build/html -q

Nothing else in qa.rst is touched -- the requirements matrix, prose, known-issues
section, and historical bug table are maintained by hand.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DOCS_SOURCE = REPO / "docs" / "source"
QA_RST = DOCS_SOURCE / "qa.rst"
COVERAGE_RST = DOCS_SOURCE / "_qa_coverage_table.rst"
TESTS_DIR = REPO / "tests"


# ---------------------------------------------------------------------------
# 1. Collect test counts
# ---------------------------------------------------------------------------

def _collect(extra_args: list[str] = ()) -> int:
    """Return number of tests collected for the given subset."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "--tb=no", *extra_args],
        capture_output=True, text=True, cwd=REPO,
    )
    for line in reversed(result.stdout.splitlines()):
        m = re.search(r"(\d+) tests? collected", line)
        if m:
            return int(m.group(1))
    return 0


def _count_test_files(subdir: str) -> int:
    return len(list((TESTS_DIR / subdir).glob("test_*.py")))


def _count_test_files_total() -> int:
    return len(list(TESTS_DIR.rglob("test_*.py")))


def _count_test_lines() -> int:
    total = 0
    for p in TESTS_DIR.rglob("test_*.py"):
        total += len(p.read_text(encoding="utf-8").splitlines())
    return total


# ---------------------------------------------------------------------------
# 2. Run coverage
# ---------------------------------------------------------------------------

def _run_coverage() -> list[tuple[str, int, int, str]]:
    """Return list of (name, stmts, missed, cover%) rows including TOTAL."""
    result = subprocess.run(
        [
            sys.executable, "-m", "pytest",
            "tests", "--ignore=tests/e2e",
            "--cov=core", "--cov=api", "--cov=cli", "--cov=web", "--cov=utils",
            "--cov-report=term",
            "-q", "--tb=no",
        ],
        capture_output=True, text=True, cwd=REPO,
    )
    rows: list[tuple[str, int, int, str]] = []
    in_table = False
    for line in result.stdout.splitlines():
        if line.startswith("Name") and "Stmts" in line:
            in_table = True
            continue
        if in_table and line.startswith("---"):
            continue
        if in_table and line.strip() == "":
            break
        if in_table:
            parts = line.split()
            if len(parts) >= 4:
                name = parts[0]
                try:
                    stmts = int(parts[1])
                    missed = int(parts[2])
                    cover = parts[3]
                    rows.append((name, stmts, missed, cover))
                except ValueError:
                    pass
    return rows


# ---------------------------------------------------------------------------
# 3. Build RST tables
# ---------------------------------------------------------------------------

def _glance_table(n_files: int, n_cases: int, n_lines: int) -> str:
    return (
        ".. list-table::\n"
        "   :widths: 30 15\n"
        "   :header-rows: 0\n\n"
        f"   * - Test files\n     - {n_files}\n"
        f"   * - Test cases (``def test_*``)\n     - {n_cases}\n"
        f"   * - Lines of test code\n     - {n_lines}\n"
        "   * - Test framework\n"
        "     - pytest 9.0.3 + pytest-playwright (``tests/e2e`` only)\n"
        "   * - Reporting\n"
        "     - Allure (``results/allure-results/``) + pytest-html (``results/pytest_test_results/``)\n"
    )


def _breakdown_table(unit: int, integ: int, rag: int, e2e: int) -> str:
    total = unit + integ + rag + e2e

    def pct(n: int) -> str:
        return f"{round(n / total * 100)}%"

    title = f"Test suite breakdown ({total} tests -- re-measured {_today()})"
    return (
        f".. list-table:: {title}\n"
        "   :widths: 40 15 45\n"
        "   :header-rows: 1\n\n"
        "   * - Category\n     - Count\n     - Share\n"
        f"   * - Unit (``tests/unit``)\n     - {unit}\n     - {pct(unit)}\n"
        f"   * - Integration / API (``tests/integration``)\n     - {integ}\n     - {pct(integ)}\n"
        f"   * - Legacy RAG suite (``tests/legacy_rag``)\n     - {rag}\n     - {pct(rag)}\n"
        f"   * - E2E, Playwright (``tests/e2e``)\n     - {e2e}\n     - {pct(e2e)}\n"
    )


def _coverage_table(rows: list[tuple[str, int, int, str]]) -> str:
    if not rows:
        return "*(coverage data unavailable -- run pytest --cov manually)*\n"

    def _short(name: str) -> str:
        # shorten paths like core/analysis/foo.py → core/analysis
        p = Path(name)
        if p.suffix == ".py":
            return str(p.parent).replace("\\", "/")
        return name.replace("\\", "/")

    # group by package prefix
    from collections import defaultdict
    buckets: dict[str, list[tuple[int, int]]] = defaultdict(list)
    total_stmts = total_missed = 0
    for name, stmts, missed, _ in rows:
        if name.upper() == "TOTAL":
            total_stmts, total_missed = stmts, missed
            continue
        pkg = _short(name)
        # roll up to top 2 levels
        parts = pkg.split("/")
        key = "/".join(parts[:2]) if len(parts) > 1 else parts[0]
        buckets[key].append((stmts, missed))

    lines = [
        ".. list-table:: Coverage by package",
        "   :widths: 30 15 15 15",
        "   :header-rows: 1",
        "",
        "   * - Package",
        "     - Statements",
        "     - Missed",
        "     - Coverage",
    ]
    for pkg, pairs in sorted(buckets.items()):
        s = sum(x[0] for x in pairs)
        m = sum(x[1] for x in pairs)
        c = f"{round((s - m) / s * 100)}%" if s else "n/a"
        lines += [f"   * - ``{pkg}``", f"     - {s}", f"     - {m}", f"     - {c}"]

    if total_stmts:
        total_cover = f"{round((total_stmts - total_missed) / total_stmts * 100)}%"
        lines += [
            "   * - **Total**",
            f"     - **{total_stmts}**",
            f"     - **{total_missed}**",
            f"     - **{total_cover}**",
        ]

    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 4. Patch qa.rst in-place
# ---------------------------------------------------------------------------

_GLANCE_START = re.compile(
    r"(?m)^\.\. list-table::\n   :widths: 30 15\n   :header-rows: 0\n"
)
_GLANCE_END_SENTINEL = "All figures re-measured"

_BREAKDOWN_START = re.compile(
    r"(?m)^\.\. list-table:: Test suite breakdown \("
)
_BREAKDOWN_END_SENTINEL = "**Unit** --"


def _replace_block(text: str, start_re: re.Pattern, end_sentinel: str, replacement: str) -> str:
    m = start_re.search(text)
    if not m:
        return text
    end_idx = text.find(end_sentinel, m.start())
    if end_idx == -1:
        return text
    return text[: m.start()] + replacement + "\n" + text[end_idx:]


def _today() -> str:
    from datetime import date
    return date.today().strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# 5. Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("Collecting test counts...", flush=True)
    n_files = _count_test_files_total()
    n_lines = _count_test_lines()
    unit  = _collect(["tests/unit"])
    integ = _collect(["tests/integration"])
    rag   = _collect(["tests/legacy_rag"])
    e2e   = _collect(["tests/e2e"])
    total = unit + integ + rag + e2e
    print(f"  unit={unit}  integration={integ}  legacy_rag={rag}  e2e={e2e}  total={total}")
    print(f"  files={n_files}  lines={n_lines}")

    print("Measuring coverage (this takes ~2 min)...", flush=True)
    cov_rows = _run_coverage()
    print(f"  coverage rows: {len(cov_rows)}")

    # patch qa.rst
    text = QA_RST.read_text(encoding="utf-8")
    glance = _glance_table(n_files, total, n_lines) + f"\nAll figures re-measured {_today()} via ``pytest --collect-only -q`` and ``wc -l``."
    text = _replace_block(text, _GLANCE_START, _GLANCE_END_SENTINEL, glance)
    breakdown = _breakdown_table(unit, integ, rag, e2e)
    text = _replace_block(text, _BREAKDOWN_START, _BREAKDOWN_END_SENTINEL, breakdown)
    QA_RST.write_text(text, encoding="utf-8")
    print(f"  wrote {QA_RST}")

    # write coverage include file
    COVERAGE_RST.write_text(_coverage_table(cov_rows), encoding="utf-8")
    print(f"  wrote {COVERAGE_RST}")

    print("Rebuilding Sphinx...", flush=True)
    result = subprocess.run(
        ["sphinx-build", "docs/source", "docs/source/_build/html", "-q"],
        cwd=REPO, capture_output=True, text=True,
    )
    if result.returncode == 0:
        print("  Sphinx: ok")
    else:
        print("  Sphinx warnings/errors:")
        print(result.stdout[-1000:] if result.stdout else "")
        print(result.stderr[-1000:] if result.stderr else "")


if __name__ == "__main__":
    main()
