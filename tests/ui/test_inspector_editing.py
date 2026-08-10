"""Regression tests for the editing bug fixed in phase 2.

Symptom: typing into any inspector field dropped out of edit mode after every character, so a
multi-digit value had to be clicked and retyped repeatedly.

Three independent causes, all exercised here:
  1. `_apply_message_page` reparented the payload editor on every keystroke (focus loss);
  2. it then called `set_payload()` on the widget being typed into (cursor jump / value reset);
  3. the resulting full refresh reset the table model, which cleared the table selection, which
     told the inspector to show its empty page.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from detector_scenario_tool.domain.scenario import MessageRef, SendMessageStep, StepKind

SET_TIME = 0x0002  # CMD_SET_TIME — a message whose editor is made of plain spin boxes


@pytest.fixture
def window(qtbot):
    from detector_scenario_tool.ui.main_window import MainWindow

    w = MainWindow()
    qtbot.addWidget(w)
    w.show()
    qtbot.waitExposed(w)
    return w


@pytest.fixture
def set_time_step(window):
    """A selected CMD_SET_TIME step with its payload editor on screen.

    Driven through the message combo rather than by mutating the step, so the panel goes through
    the same path a user does.
    """
    window._add_ku_step()
    window._select_row(0)

    selector = window.inspector_panel.msg_selector
    index = _selector_index_for(selector, SET_TIME)
    assert index >= 0, "CMD_SET_TIME missing from the message selector"
    selector.setCurrentIndex(index)

    step = window.document.steps[0]
    assert step.message.msg_id == SET_TIME
    return step


def _payload_editor(window):
    return window.inspector_panel.current_payload_editor


def _selector_index_for(selector, msg_id: int) -> int:
    """The combo stores (category, msg_id, name), so findData needs the exact tuple."""
    for i in range(selector.count()):
        data = selector.itemData(i)
        if data is not None and data[1] == msg_id:
            return i
    return -1


def test_typing_into_a_payload_field_keeps_the_step_selected(window, set_time_step, qtbot):
    editor = _payload_editor(window)
    assert editor is not None

    spin = editor.widget_for("board_time_s")
    spin.setFocus()
    spin.selectAll()

    QTest.keyClicks(spin, "12345")

    assert window.inspector_panel.current_step is set_time_step
    assert window.table_view.selectionModel().selectedRows(), "table selection was dropped"


def test_typing_does_not_reparent_the_payload_editor(window, set_time_step):
    editor = _payload_editor(window)
    parent_before = editor.parent()

    QTest.keyClicks(editor.widget_for("board_time_s"), "7")

    assert _payload_editor(window) is editor, "editor instance was swapped"
    assert editor.parent() is parent_before, "editor was reparented mid-edit"


def test_typing_does_not_write_the_payload_back_into_the_live_editor(
    window, set_time_step, monkeypatch
):
    editor = _payload_editor(window)
    calls = []
    monkeypatch.setattr(
        editor, "set_payload", lambda payload: calls.append(dict(payload)), raising=True
    )

    QTest.keyClicks(editor.widget_for("board_time_s"), "42")

    assert calls == [], "set_payload must not run while the user is typing"


def test_multi_digit_entry_reaches_the_step(window, set_time_step, qtbot):
    """Spin boxes commit on Enter, not per character (keyboard tracking is off)."""
    editor = _payload_editor(window)
    spin = editor.widget_for("board_time_s")
    spin.setFocus()
    spin.selectAll()

    QTest.keyClicks(spin, "12345")
    QTest.keyClick(spin, Qt.Key.Key_Return)

    assert spin.value() == 12345
    assert set_time_step.payload["board_time_s"] == 12345


def test_the_step_is_not_updated_with_half_typed_values(window, set_time_step):
    """The document used to walk through 1, 12, 123, 1234 while the user typed "12345"."""
    spin = _payload_editor(window).widget_for("board_time_s")
    spin.setFocus()
    spin.selectAll()

    QTest.keyClicks(spin, "12345")

    assert set_time_step.payload.get("board_time_s", 0) == 0, "committed mid-typing"

    QTest.keyClick(spin, Qt.Key.Key_Return)
    assert set_time_step.payload["board_time_s"] == 12345


def test_commit_pending_edits_flushes_an_unconfirmed_value(window, set_time_step):
    """Saving must not silently drop a value that was typed but never confirmed."""
    spin = _payload_editor(window).widget_for("board_time_s")
    spin.setFocus()
    spin.selectAll()
    QTest.keyClicks(spin, "999")

    window.inspector_panel.commit_pending_edits()

    assert set_time_step.payload["board_time_s"] == 999


def test_the_edited_field_keeps_focus(window, set_time_step):
    editor = _payload_editor(window)
    spin = editor.widget_for("board_time_s")
    spin.setFocus()
    assert spin.hasFocus()

    QTest.keyClicks(spin, "9")

    assert spin.hasFocus(), "focus left the field mid-edit"


def test_typing_in_the_title_field_keeps_focus_and_text(window, set_time_step):
    title = window.inspector_panel.msg_title_edit
    title.setFocus()
    title.clear()

    QTest.keyClicks(title, "power on")

    assert title.hasFocus()
    assert title.text() == "power on"
    assert set_time_step.title == "power on"


def test_row_status_updates_do_not_clear_the_table_selection(window, set_time_step):
    """The refresh path must not reset the model out from under the selection."""
    window._select_row(0)
    assert window.table_view.selectionModel().selectedRows()

    window.table_model.set_row_statuses({0: "warning"})

    assert window.table_view.selectionModel().selectedRows()
    assert window.inspector_panel.current_step is set_time_step


def test_wait_step_delay_survives_typing(window, qtbot):
    window._add_wait_step()
    window._select_row(0)
    step = window.document.steps[0]

    spin = window.inspector_panel.wait_delay_spin
    spin.setFocus()
    spin.selectAll()
    QTest.keyClicks(spin, "2500")
    QTest.keyClick(spin, Qt.Key.Key_Return)

    assert spin.hasFocus()
    assert spin.value() == 2500
    assert step.delay_ms == 2500


def test_survives_the_coalesced_refresh_actually_running(window, set_time_step, qtbot):
    """Coalescing must not merely postpone the problem past the end of the test.

    Type, then force the deferred full refresh (validation + timeline rebuild + log re-match)
    to run, and check the edit context is still intact.
    """
    editor = _payload_editor(window)
    spin = editor.widget_for("board_time_s")
    spin.setFocus()
    spin.selectAll()
    QTest.keyClicks(spin, "4321")
    QTest.keyClick(spin, Qt.Key.Key_Return)

    window.flush_pending_refresh()
    qtbot.wait(10)

    assert spin.hasFocus(), "focus lost when the deferred refresh ran"
    assert spin.value() == 4321
    assert window.inspector_panel.current_payload_editor is editor
    assert window.inspector_panel.current_step is set_time_step
    assert window.table_view.selectionModel().selectedRows()


def test_a_burst_of_keystrokes_triggers_one_refresh(window, set_time_step, qtbot, monkeypatch):
    """Every character used to run the whole validate/rebuild/re-match pipeline."""
    calls = []
    original = window._refresh_all_views
    monkeypatch.setattr(
        window, "_refresh_all_views", lambda: (calls.append(1), original())[1]
    )

    spin = _payload_editor(window).widget_for("board_time_s")
    spin.setFocus()
    spin.selectAll()
    QTest.keyClicks(spin, "123456")

    window.flush_pending_refresh()
    qtbot.wait(10)

    assert len(calls) <= 2, f"expected the burst to coalesce, got {len(calls)} refreshes"


def test_changing_the_selected_message_does_swap_the_editor(window, set_time_step):
    """The editor must still be replaced when the user picks a different message."""
    editor_before = _payload_editor(window)

    selector = window.inspector_panel.msg_selector
    index = _selector_index_for(selector, 0x0008)
    assert index >= 0
    selector.setCurrentIndex(index)

    assert _payload_editor(window) is not editor_before
    assert window.document.steps[0].message.msg_id == 0x0008


def test_switching_message_does_not_leave_stale_payload_keys(window, set_time_step):
    """The payload used to be written from the outgoing editor, leaving its keys behind."""
    assert set(set_time_step.payload) == {"board_time_ms", "board_time_s"}

    selector = window.inspector_panel.msg_selector
    selector.setCurrentIndex(_selector_index_for(selector, 0x0008))  # CMD_ERASE

    assert set(set_time_step.payload) == {"selected_nand_bank", "keep_power_after_erase"}
