"""
Architecture rules from CLAUDE.md SS2, enforced as tests instead of left as prose.

The rule: ``core`` (domain, services, adapters, analysis) never imports a web framework or a
visualization library; presentation lives in ``web/`` and ``api/``. Until 2026-10-02 the rule was
stated in CLAUDE.md and ``core/domain/interfaces.py`` but violated by an unused
``get_plotly_fig()`` in ``core/analysis/cluster_discovery.py``; nothing noticed because nothing
checked.
"""

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.req("REQ-OPS-ARCH-02")

REPO_ROOT = Path(__file__).resolve().parents[2]
CORE_DIR = REPO_ROOT / "core"

# Top-level package names ``core`` must never import.
FORBIDDEN = {"plotly", "matplotlib", "fastapi", "starlette", "jinja2", "streamlit", "pyvis"}


def _imported_top_level_modules(source: str) -> set[str]:
    """Return the top-level module name of every ``import`` / ``from ... import`` in ``source``."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module.split(".")[0])
    return found


def _core_files() -> list[Path]:
    return sorted(p for p in CORE_DIR.rglob("*.py") if "__pycache__" not in p.parts)


def test_imported_top_level_modules_finds_plain_and_from_imports():
    """The scanner sees ``import a.b``, ``from c.d import e`` and ignores relative imports."""
    source = chr(10).join(
        ["import plotly.express as px", "from fastapi import APIRouter", "from . import sibling", "import os"]
    )
    assert _imported_top_level_modules(source) == {"plotly", "fastapi", "os"}


@pytest.mark.parametrize("path", _core_files(), ids=lambda p: p.relative_to(REPO_ROOT).as_posix())
def test_core_module_imports_no_web_or_visualization_library(path):
    """No file under ``core/`` imports a web framework or visualization library (CLAUDE.md SS2)."""
    violations = _imported_top_level_modules(path.read_text(encoding="utf-8")) & FORBIDDEN
    assert not violations, f"{path.relative_to(REPO_ROOT).as_posix()} imports {sorted(violations)}"
