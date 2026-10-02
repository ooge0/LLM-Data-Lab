"""Page object for ``/db_export`` -- the table of runs with per-row export buttons and sync status."""

from playwright.sync_api import Locator

from tests.e2e.pages.base_page import BasePage


class DbExportPage(BasePage):
    """One row per run; each row has Send to DB / Re-export (overwrite) buttons and a status cell."""

    path = "/db_export"

    def row(self, run_id: str) -> Locator:
        """The table row for this run, found by the run id shown in its first cell."""
        return self.page.locator("tr", has=self.page.locator(f"code:text-is('{run_id}')"))

    def sync_cell(self, run_id: str) -> Locator:
        """The row's 'Export status' cell, which is always the last ``td`` of the row."""
        return self.row(run_id).locator("td").last

    def sync_text(self, run_id: str) -> str:
        """Rendered text of the status cell (``inner_text`` reflects real rendered line breaks)."""
        return self.sync_cell(run_id).inner_text()

    def click_send_to_db(self, run_id: str) -> None:
        """Click the row's 'Send to DB' button."""
        self.row(run_id).get_by_role("button", name="Send to DB").click()

    def click_reexport(self, run_id: str) -> None:
        """Click the row's 'Re-export (overwrite)' button (it only exists after a refused export)."""
        self.row(run_id).get_by_role("button", name="Re-export (overwrite)").click()

    def wait_for_reexport_button(self, run_id: str, timeout: int = 5000) -> None:
        """Wait until the 'Re-export (overwrite)' button appears in the row."""
        self.row(run_id).get_by_role("button", name="Re-export (overwrite)").wait_for(timeout=timeout)

    def wait_for_timestamp(self, run_id: str, previous: str | None = None, timeout: int = 5000) -> None:
        """
        Wait until the status cell shows a real timestamp (``UTC``). With ``previous`` given, also wait
        until the text differs from it, i.e. until a genuinely newer timestamp replaced the old one.
        """
        cell = self.sync_cell(run_id).element_handle()
        if previous is None:
            self.page.wait_for_function("el => el.innerText.includes('UTC')", arg=cell, timeout=timeout)
        else:
            self.page.wait_for_function(
                "([el, prev]) => el.innerText.includes('UTC') && el.innerText !== prev",
                arg=[cell, previous],
                timeout=timeout,
            )
