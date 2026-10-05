"""Page object for ``/nlp`` -- three tabbed sub-pages of Plotly charts for one chosen run."""

from tests.e2e.pages.base_page import BasePage


class NlpPage(BasePage):
    """The tabbed NLP analysis page (panels ``#nlp-1``, ``#nlp-2``, ``#nlp-3``)."""

    path = "/nlp"

    def choose_run(self, run_id: str) -> None:
        """Pick a run in the picker and wait until at least one chart has rendered."""
        self.page.locator("select[name='run_id']").select_option(run_id)
        self.page.wait_for_selector(".plotly-graph-div")

    def open_tab(self, label: str) -> None:
        """Click the tab button whose text contains ``label`` (for example ``NLP-2``)."""
        self.page.get_by_role("button", name=label, exact=False).click()

    def wait_for_panel_active(self, panel_id: str) -> None:
        """Wait until the panel with this id has the ``active`` class (is the visible one)."""
        self.page.wait_for_function(f"document.getElementById('{panel_id}').classList.contains('active')")

    def chart_width_ratio(self, panel_id: str) -> float:
        """Width of the panel's first chart divided by the panel's own width, from real layout geometry."""
        panel = self.page.locator(f"#{panel_id}")
        chart = panel.locator(".plotly-graph-div").first
        return chart.bounding_box()["width"] / panel.bounding_box()["width"]
