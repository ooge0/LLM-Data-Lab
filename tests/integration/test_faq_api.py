"""
Functional API tests for the Stage 14 ``/faq`` endpoint
(:mod:`api.routers.faq`) -- through the real FastAPI app, against the real
``faq_eng.md``/``faq_ua.md`` files on disk (no fakes -- there's no
persisted-run data involved in this tab at all).
"""

import pytest
from fastapi.testclient import TestClient

from api.app import app

pytestmark = pytest.mark.req("REQ-PAGE-FAQ-01")


@pytest.fixture
def client():
    """TestClient as a context manager -- see test_demo_api.py's client fixture for why this matters."""
    with TestClient(app) as c:
        yield c


def test_faq_defaults_to_english(client):
    """GET /faq with no lang param renders faq_eng.md's real content as HTML."""
    response = client.get("/faq")
    assert response.status_code == 200
    assert "<h1>" in response.text or "<p>" in response.text
    assert "benchmarking suite" in response.text


def test_faq_renders_ukrainian_when_selected(client):
    """GET /faq?lang=Українська renders faq_ua.md, a different file than the English default."""
    response = client.get("/faq", params={"lang": "Українська"})
    assert response.status_code == 200
    english_response = client.get("/faq")
    assert response.text != english_response.text


def test_faq_with_unknown_language_shows_inline_error_not_500(client):
    """GET /faq?lang=Klingon (not a real option) shows an inline 'not found' message, not a crash."""
    response = client.get("/faq", params={"lang": "Klingon"})
    assert response.status_code == 200
    assert "not found" in response.text.lower()


def test_faq_page_includes_language_switch_links(client):
    """The rendered page includes links for both known languages, matching the legacy segmented control's options."""
    response = client.get("/faq")
    assert response.status_code == 200
    assert "English" in response.text
    assert "Українська" in response.text


def test_faq_math_elements_are_rendered_as_html_math_spans(client):
    """
    Regression for the reported bug: ``$...$`` formulas in faq_eng.md were
    rendered as plain paragraph text because ``MarkdownIt()`` had no math
    plugin.  With ``dollarmath_plugin`` enabled, each ``$...$`` formula is
    converted server-side to ``<span class="math inline">`` so the client-side
    KaTeX pass has a DOM target, not raw ``$`` text to hunt for.
    The FAQ files use single-dollar delimiters for both standalone (block-
    styled via CSS) and inline formulas.
    """
    response = client.get("/faq")
    assert response.status_code == 200
    # dollarmath_plugin wraps $...$ as <span class="math inline">
    assert 'class="math inline"' in response.text


def test_faq_ukrainian_math_elements_render_as_html_math_spans(client):
    """Same math-rendering guarantee for the Ukrainian variant of the FAQ."""
    response = client.get("/faq", params={"lang": "Українська"})
    assert response.status_code == 200
    assert 'class="math inline"' in response.text
