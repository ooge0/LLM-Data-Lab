"""
Playwright E2E tests for ``/experiments`` -- the first real browser-driven
layer this project has (CLAUDE.md SS7 names Playwright as a target layer;
before this file, zero infra existed anywhere in the repo -- see
:doc:`qa`'s former R37 gap). Scoped deliberately to what a real browser is
*required* for: the client-side JS added alongside this file (conditional
field enabling/disabling, dynamic sweep-parameter bounds, tab switching) is
invisible to ``TestClient``, which never executes JavaScript at all --
every other test in this suite that touches ``/experiments`` tests the
server side, not this.

No real Ollama call happens anywhere here -- these tests exercise form
*behavior* (what becomes enabled/disabled/validated as fields change), not
a live generation run, so they're fast and don't depend on a local model
being pulled.
"""

import pytest

from tests.e2e.pages import ExperimentsPage

# live_server is defined once in tests/e2e/conftest.py and shared across every E2E file --
# pytest's fixture resolution finds it there automatically, no import needed. Selectors live in
# tests/e2e/pages/experiments_page.py (Page Object Model); the tests below only state intent.


@pytest.fixture
def experiments_page(live_server, page):
    """A fresh /experiments page object, opened for each test."""
    return ExperimentsPage(page, live_server).open()


# --- Sweep parameter: disabled-by-default, correctly re-enabled -------------


def test_sweep_fields_are_disabled_when_no_sweep_parameter_selected(experiments_page):
    """
    Regression test for the reported bug: 'Steps' (and every other sweep
    sub-field) must be disabled while Sweep parameter = None, not silently
    editable with no effect.
    """
    form = experiments_page
    for field_id in form.SWEEP_FIELDS:
        assert form.is_disabled(field_id), f"#{field_id} should start disabled"


def test_selecting_a_sweep_parameter_enables_mode_and_steps_and_delta_mode_fields(experiments_page):
    """Choosing a real sweep parameter enables Mode/Steps, and (since Delta is the default mode) the Delta/Descending fields -- but not the MIN-MAX explicit fields."""
    form = experiments_page
    form.select_sweep_parameter("Temperature")

    assert not form.is_disabled("sweep_mode")
    assert not form.is_disabled("sweep_steps")
    assert not form.is_disabled("sweep_delta")
    assert not form.is_disabled("sweep_desc")
    assert form.is_disabled("sweep_min")
    assert form.is_disabled("sweep_max")


def test_switching_sweep_mode_to_minmax_swaps_which_fields_are_enabled(experiments_page):
    """Switching Mode from Delta to MIN-MAX disables Delta/Descending and enables the explicit min/max fields -- mutually exclusive, not all-editable at once."""
    form = experiments_page
    form.select_sweep_parameter("Temperature")
    form.select_sweep_mode("MIN-MAX")

    assert form.is_disabled("sweep_delta")
    assert form.is_disabled("sweep_desc")
    assert not form.is_disabled("sweep_min")
    assert not form.is_disabled("sweep_max")


def test_choosing_none_again_disables_every_sweep_field_again(experiments_page):
    """Selecting a parameter then switching back to None re-disables everything -- the toggle is fully reversible, not one-way."""
    form = experiments_page
    form.select_sweep_parameter("Top P")
    form.select_sweep_parameter("")

    for field_id in form.SWEEP_FIELDS:
        assert form.is_disabled(field_id)


@pytest.mark.parametrize(
    "param, expected_min, expected_max",
    [
        ("Temperature", "0", "2"),
        ("Top P", "0", "1"),
        ("Frequency penalty", "-2", "2"),
        ("Presence penalty", "-2", "2"),
    ],
)
def test_sweep_min_max_bounds_are_real_per_parameter_not_a_fixed_fake_range(
    experiments_page, param, expected_min, expected_max
):
    """
    Regression test: the explicit min/max fields' own min/max *attributes*
    (the browser-enforced bounds) must match the selected parameter's real
    valid range -- e.g. Top P must be bounded to [0, 1], not left at
    Temperature's [0, 2] regardless of which parameter is actually being
    swept, which would let an unskilled user submit a nonsensical value.
    """
    form = experiments_page
    form.select_sweep_parameter(param)
    form.select_sweep_mode("MIN-MAX")

    assert form.attribute("sweep_min", "min") == expected_min
    assert form.attribute("sweep_min", "max") == expected_max
    assert form.attribute("sweep_max", "min") == expected_min
    assert form.attribute("sweep_max", "max") == expected_max


# --- Other conditional fields ------------------------------------------------


def test_self_critic_checkbox_disables_teacher_model_and_shows_hint(experiments_page):
    """Checking self-critic disables the (now-irrelevant) teacher_model select and reveals the 'ignored while self-critic is on' hint."""
    form = experiments_page
    assert not form.is_disabled("teacher_model")
    assert form.is_hidden("teacher-hint")

    form.set_self_critic(True)

    assert form.is_disabled("teacher_model")
    assert form.is_visible("teacher-hint")

    form.set_self_critic(False)
    assert not form.is_disabled("teacher_model")


def test_rag_enabled_checkbox_enables_rag_mode_and_top_k(experiments_page):
    """RAG mode/Top-K start disabled and only become editable once 'Enable RAG' is checked."""
    form = experiments_page
    assert form.is_disabled("rag_mode")
    assert form.is_disabled("rag_top_k")

    form.set_rag_enabled(True)

    assert not form.is_disabled("rag_mode")
    assert not form.is_disabled("rag_top_k")


def test_non_tuned_prompt_mode_disables_and_unchecks_exclude_archetype(experiments_page):
    """'Exclude archetype from prompt' only makes sense in Tuned mode -- switching away disables it and clears any existing check, rather than silently submitting a no-op checked value."""
    form = experiments_page
    form.set_exclude_archetype(True)
    assert form.is_checked("exclude_archetype_from_prompt")

    form.select_prompt_mode("Blind mode (Hide label)")

    assert form.is_disabled("exclude_archetype_from_prompt")
    assert not form.is_checked("exclude_archetype_from_prompt")


# --- Required-field validation -----------------------------------------------


def test_submitting_with_no_archetypes_selected_is_blocked_by_the_browser(experiments_page):
    """
    Regression test: student_models/archetypes are required selects; a
    browser must refuse to submit the form while archetypes has nothing
    selected (native HTML5 constraint validation), rather than silently
    POSTing a config that resolves to a real-but-empty 0-task run.
    """
    form = experiments_page
    assert form.archetypes_select_is_valid() is False


# --- Live setup summary (real htmx round-trip against the live server) ------


def test_preview_panel_updates_live_when_a_field_changes(experiments_page):
    """Changing a real form field triggers a real htmx round-trip to /experiments/preview against the live server, and the setup summary panel reflects the new selection -- not just the bare task count."""
    form = experiments_page
    form.select_archetypes(["Detached"])  # blurs afterwards so the 'change' event actually fires
    form.wait_for_preview()

    assert "Detached" in form.preview_text()
    assert "Total iterations for this setup: 1" in form.preview_text()
