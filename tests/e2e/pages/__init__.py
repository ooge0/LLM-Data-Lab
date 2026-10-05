"""
Page Objects for the Playwright E2E suite (CLAUDE.md SS7: "lightweight Page Object Model").

Each class wraps one page of the app: it owns that page's selectors and exposes actions and state
reads, so a test says *what* it does ("select a sweep parameter") instead of *how* ("page.select_option
on #sweep_param"). When a template's markup changes, the selector is fixed here once instead of in every
test. Assertions stay in the tests; a page object only drives the page and reports what it sees.
"""

from tests.e2e.pages.base_page import BasePage
from tests.e2e.pages.db_export_page import DbExportPage
from tests.e2e.pages.experiments_page import ExperimentsPage
from tests.e2e.pages.nlp_page import NlpPage

__all__ = ["BasePage", "DbExportPage", "ExperimentsPage", "NlpPage"]
