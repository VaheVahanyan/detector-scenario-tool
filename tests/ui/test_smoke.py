"""Smoke tests: the window must build and survive the basic edit operations.

These are deliberately shallow. Their job is to catch "the app no longer starts" during the
phase 2 and phase 4 UI work, cheaply and headlessly.
"""

from __future__ import annotations

import pytest

from detector_scenario_tool.domain.scenario import SendMessageStep, StepKind


@pytest.fixture
def window(qtbot):
    from detector_scenario_tool.ui.main_window import MainWindow

    w = MainWindow()
    qtbot.addWidget(w)
    return w


def test_main_window_builds(window):
    assert window.document.steps == []
    assert window.table_model.rowCount() == 0


def test_adding_steps_updates_the_model_and_the_timeline(window):
    window._add_ku_step()
    window._add_wait_step()

    assert len(window.document.steps) == 2
    assert window.table_model.rowCount() == 2
    assert isinstance(window.document.steps[0], SendMessageStep)
    assert window.document.steps[0].kind == StepKind.SEND_KU


def test_selecting_a_step_populates_the_inspector(window):
    window._add_ku_step()
    window._select_row(0)

    assert window.inspector_panel.current_step is window.document.steps[0]


def test_step_reordering_keeps_the_document_and_view_in_step(window):
    window._add_ku_step()
    window._add_wait_step()
    first_id = window.document.steps[0].id

    window._select_row(0)
    window._move_selected_step_down()

    assert window.document.steps[1].id == first_id
    assert window.table_model.rowCount() == 2


def test_deleting_the_last_step_clears_the_inspector(window):
    window._add_ku_step()
    window._select_row(0)
    window._delete_selected_step()

    assert window.document.steps == []
    assert window.inspector_panel.current_step is None


def test_language_switch_retranslates_without_error(window):
    window._set_ui_language("en")
    window._set_ui_language("ru")


def test_new_document_resets_state(window):
    window._add_ku_step()
    window._new_document()

    assert window.document.steps == []
    assert window.current_path is None


class TestLanguageSwitch:
    """Message names now come from the translation layer, so they must follow the switch."""

    def test_message_names_are_translated(self, window):
        window._add_ku_step()
        window._select_row(0)
        selector = window.inspector_panel.msg_selector

        window._set_ui_language("ru")
        russian = selector.currentText()
        window._set_ui_language("en")
        english = selector.currentText()

        assert russian and english
        assert russian != english

    def test_selector_is_not_emptied_by_a_language_switch(self, window):
        """Regression: retranslating cleared the combo and set_step() no longer refilled it."""
        window._add_ku_step()
        window._select_row(0)
        selector = window.inspector_panel.msg_selector
        count_before = selector.count()

        window._set_ui_language("en")
        window._set_ui_language("ru")

        assert selector.count() == count_before
        assert selector.currentText()

    def test_wait_step_selector_survives_a_language_switch(self, window):
        window._add_wait_ts_step()
        window._select_row(0)
        selector = window.inspector_panel.wait_ts_selector
        count_before = selector.count()

        window._set_ui_language("en")

        assert selector.count() == count_before
        assert selector.currentText()

    def test_diagnostics_are_rendered_in_the_active_language(self, window):
        window._add_ku_step()
        window.flush_pending_refresh()
        model = window.warnings_model
        assert model.rowCount() > 0

        window._set_ui_language("ru")
        russian = model.data(model.index(0, 3))
        window._set_ui_language("en")
        english = model.data(model.index(0, 3))

        assert russian and english
        assert russian != english
        assert not russian.startswith("diag."), "diagnostic code leaked into the UI"


class TestFullUiTranslation:
    """Sweep every visible widget after a language switch and look for untranslated text."""

    def _visible_texts(self, window) -> dict[str, str]:
        from PySide6.QtWidgets import QAbstractButton, QGroupBox, QLabel

        # findChildren takes one type at a time in PySide6.
        texts = {}
        for widget_type in (QLabel, QAbstractButton, QGroupBox):
            for widget in window.findChildren(widget_type):
                value = widget.title() if isinstance(widget, QGroupBox) else widget.text()
                if value and value.strip():
                    texts[f"{type(widget).__name__}:{id(widget)}"] = value
        return texts

    def test_no_untranslated_keys_leak_into_widgets(self, window):
        window._add_ku_step()
        window._select_row(0)

        for language in ("ru", "en"):
            window._set_ui_language(language)
            for name, value in self._visible_texts(window).items():
                assert not value.startswith(("field.", "msg.", "diag.", "category.", "choice.")), (
                    f"{name} shows a raw translation key in {language}: {value}"
                )
                assert "{" not in value, f"{name} has an unformatted placeholder: {value}"

    def test_switching_language_changes_the_visible_text(self, window):
        window._add_ku_step()
        window._select_row(0)

        window._set_ui_language("ru")
        russian = set(self._visible_texts(window).values())
        window._set_ui_language("en")
        english = set(self._visible_texts(window).values())

        # Not everything differs (numbers, "100%"), but the bulk must.
        assert len(russian - english) > 10, "language switch barely changed anything"
