"""Shared base for every page object: holds the Playwright ``page`` and the live server's base URL."""

from playwright.sync_api import Page


class BasePage:
    """
    Common behaviour of all page objects.

    Parameters
    ----------
    page : playwright.sync_api.Page
        The browser page provided by the ``pytest-playwright`` ``page`` fixture.
    base_url : str
        Root URL of the live test server (the ``live_server`` fixture's value).

    Attributes
    ----------
    path : str
        The page's URL path, set by each subclass.
    """

    path = "/"

    def __init__(self, page: Page, base_url: str) -> None:
        self.page = page
        self.base_url = base_url

    def open(self):
        """Navigate to this page and return ``self`` so a fixture can ``return Page(...).open()``."""
        self.page.goto(f"{self.base_url}{self.path}")
        return self
