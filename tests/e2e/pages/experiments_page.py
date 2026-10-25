"""Page object for ``/experiments`` -- the experiment setup form and its live preview panel."""

from tests.e2e.pages.base_page import BasePage


class ExperimentsPage(BasePage):
    """The experiment form: sweep fields, conditional fields, required-field validation, preview."""

    path = "/experiments"

    #: Every sub-field of the sweep section; all start disabled until a sweep parameter is chosen.
    SWEEP_FIELDS = ["sweep_mode", "sweep_steps", "sweep_delta", "sweep_desc", "sweep_min", "sweep_max"]

    def _field(self, field_id: str) -> str:
        return f"#{field_id}"

    # --- reading state -------------------------------------------------

    def is_disabled(self, field_id: str) -> bool:
        """Whether the form control with this id is currently disabled."""
        return self.page.is_disabled(self._field(field_id))

    def is_visible(self, element_id: str) -> bool:
        """Whether the element with this id is currently visible."""
        return self.page.is_visible(self._field(element_id))

    def is_hidden(self, element_id: str) -> bool:
        """Whether the element with this id is currently hidden."""
        return self.page.is_hidden(self._field(element_id))

    def is_checked(self, field_id: str) -> bool:
        """Whether the checkbox with this id is checked."""
        return self.page.is_checked(self._field(field_id))

    def attribute(self, field_id: str, name: str):
        """An HTML attribute of the control with this id (for example its ``min``/``max`` bounds)."""
        return self.page.get_attribute(self._field(field_id), name)

    def archetypes_none_checked(self) -> bool:
        """True when no archetype checkbox is checked (the form would be blocked by JS validation on submit)."""
        return self.page.eval_on_selector_all(
            "input[name='archetypes']",
            "els => els.every(el => !el.checked)",
        )

    def preview_text(self) -> str:
        """Text of the live setup-summary panel."""
        return self.page.inner_text("#task-preview")

    # --- actions ---------------------------------------------------------

    def select_sweep_parameter(self, value: str) -> None:
        """Choose the swept parameter (``""`` means None)."""
        self.page.select_option("#sweep_param", value)

    def select_sweep_mode(self, value: str) -> None:
        """Choose the sweep mode, ``Delta`` or ``MIN-MAX``."""
        self.page.select_option("#sweep_mode", value)

    def set_self_critic(self, checked: bool) -> None:
        """Check or uncheck the self-critic box."""
        self.page.set_checked("#self_critic", checked)

    def set_rag_enabled(self, checked: bool) -> None:
        """Check or uncheck the Enable RAG box."""
        self.page.set_checked("#rag_enabled", checked)

    def set_exclude_archetype(self, checked: bool) -> None:
        """Check or uncheck 'Exclude archetype from prompt'."""
        self.page.set_checked("#exclude_archetype_from_prompt", checked)

    def select_prompt_mode(self, label: str) -> None:
        """Choose the prompt mode by its visible label."""
        self.page.select_option("#prompt_mode", label=label)

    def select_archetypes(self, values: list[str]) -> None:
        """Check the given archetypes by value in the checkbox list, then blur so the ``change`` event fires."""
        for value in values:
            self.page.check(f"input[name='archetypes'][value='{value}']")
        self.page.locator("body").click()

    def wait_for_preview(self, timeout: int = 5000) -> None:
        """Wait for the htmx round-trip to render the preview's summary list."""
        self.page.wait_for_selector("#task-preview dl", timeout=timeout)
