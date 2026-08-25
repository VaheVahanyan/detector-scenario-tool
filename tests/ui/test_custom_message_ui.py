"""Authoring a message in the window and using it like any other."""

from __future__ import annotations

import pytest

from detector_scenario_tool.domain.custom_messages import CustomMessageSpec
from detector_scenario_tool.domain.scenario import CyclicPolicy
from detector_scenario_tool.transport.backend import ConnectionSettings
from detector_scenario_tool.ui.dialogs.custom_message_dialog import (
    LENGTH_MODE_LONG,
    LENGTH_MODE_SHORT,
    CustomMessageDialog,
)

CUSTOM_ID = 0x0FFF


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    from detector_scenario_tool.ui.main_window import MainWindow

    w = MainWindow()
    qtbot.addWidget(w)
    yield w
    w.custom_message_sync.clear()


def _define(window, **kwargs) -> CustomMessageSpec:
    spec = CustomMessageSpec(
        name=kwargs.pop("name", "Test command"),
        msg_id=kwargs.pop("msg_id", CUSTOM_ID),
        length=kwargs.pop("length", 6),
        content_hex=kwargs.pop("content_hex", "01 02 03"),
        **kwargs,
    )
    window.document.custom_messages = [spec]
    window._sync_custom_messages()
    window.inspector_panel.reload_message_catalog()
    return spec


def _select(window, msg_id: int) -> None:
    selector = window.inspector_panel.msg_selector
    for i in range(selector.count()):
        if selector.itemData(i)[1] == msg_id:
            selector.setCurrentIndex(i)
            return
    raise AssertionError(f"0x{msg_id:04X} is not offered")


class TestDialog:
    def test_it_produces_a_spec(self, qtbot):
        dialog = CustomMessageDialog()
        qtbot.addWidget(dialog)

        dialog.name_edit.setText("Мой пакет")
        dialog.msg_id_edit.setText("0x0FFD")
        dialog.length_spin.setValue(4)
        dialog.content_editor.hex_edit.setPlainText("DE AD BE EF")

        spec = dialog.result_spec()
        assert spec.name == "Мой пакет"
        assert spec.msg_id == 0x0FFD
        assert spec.content_bytes() == bytes([0xDE, 0xAD, 0xBE, 0xEF])

    def test_a_bare_hex_identifier_is_accepted(self, qtbot):
        dialog = CustomMessageDialog()
        qtbot.addWidget(dialog)
        dialog.msg_id_edit.setText("0FFD")

        assert dialog.result_spec().msg_id == 0x0FFD

    def test_a_framing_identifier_blocks_ok(self, qtbot):
        from PySide6.QtWidgets import QDialogButtonBox

        dialog = CustomMessageDialog()
        qtbot.addWidget(dialog)
        dialog.msg_id_edit.setText("0xFFFE")
        dialog._revalidate()

        assert not dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled()
        assert "FFFE" in dialog.problems_label.text()

    def test_bad_hex_blocks_ok(self, qtbot):
        from PySide6.QtWidgets import QDialogButtonBox

        dialog = CustomMessageDialog()
        qtbot.addWidget(dialog)
        dialog.content_editor.hex_edit.setPlainText("not hex")

        assert not dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled()

    def test_framing_can_be_forced(self, qtbot):
        dialog = CustomMessageDialog()
        qtbot.addWidget(dialog)
        dialog.length_spin.setValue(4)
        dialog.framing_combo.setCurrentIndex(dialog.framing_combo.findData(LENGTH_MODE_LONG))

        assert dialog.result_spec().is_long is True

    def test_forcing_short_on_a_long_payload_is_reported(self, qtbot):
        dialog = CustomMessageDialog()
        qtbot.addWidget(dialog)
        dialog.length_spin.setValue(20)
        dialog.framing_combo.setCurrentIndex(dialog.framing_combo.findData(LENGTH_MODE_SHORT))

        assert dialog.problems_label.text()

    def test_editing_keeps_the_identity(self, qtbot):
        original = CustomMessageSpec(name="A", msg_id=CUSTOM_ID, length=6)
        dialog = CustomMessageDialog(original)
        qtbot.addWidget(dialog)
        dialog.name_edit.setText("B")

        result = dialog.result_spec()
        assert result.id == original.id
        assert result.name == "B"

    def test_the_summary_states_the_framing(self, qtbot):
        dialog = CustomMessageDialog()
        qtbot.addWidget(dialog)
        dialog.length_spin.setValue(4)

        assert dialog.problems_label.text()


class TestIntegration:
    def test_a_custom_command_appears_in_the_selector(self, window):
        _define(window)
        window._add_ku_step()
        window._select_row(0)

        selector = window.inspector_panel.msg_selector
        ids = [selector.itemData(i)[1] for i in range(selector.count())]
        assert CUSTOM_ID in ids

    def test_it_gets_a_payload_editor(self, window):
        _define(window)
        window._add_ku_step()
        window._select_row(0)
        _select(window, CUSTOM_ID)

        editor = window.inspector_panel.current_payload_editor
        assert editor is not None
        assert editor.widget_for("content") is not None

    def test_it_packs_to_the_declared_length(self, window):
        from detector_scenario_tool.protocol.packers import pack_send_message_step

        _define(window, length=10, content_hex="01 02 03 04 05 06 07 08 09 0A")
        window._add_ku_step()
        window._select_row(0)
        _select(window, CUSTOM_ID)

        packed = pack_send_message_step(window.document.steps[0])
        assert len(packed) == 10

    def test_the_scenario_table_names_it(self, window):
        _define(window, name="Проба")
        window._add_ku_step()
        window._select_row(0)
        _select(window, CUSTOM_ID)

        assert "Проба" in window.table_model.data(window.table_model.index(0, 3))

    def test_the_name_is_not_translated(self, window):
        """A user-supplied name is not a translation key, so it must survive a language switch."""
        _define(window, name="Проба")
        window._add_ku_step()
        window._select_row(0)
        _select(window, CUSTOM_ID)

        window._set_ui_language("en")
        assert "Проба" in window.table_model.data(window.table_model.index(0, 3))

    def test_it_is_flagged_as_unknown_to_the_protocol(self, window):
        _define(window)
        window._add_ku_step()
        window._select_row(0)
        _select(window, CUSTOM_ID)
        window.flush_pending_refresh()

        codes = [
            window.warnings_model.items[i].code
            for i in range(window.warnings_model.rowCount())
        ]
        assert "custom.unknown_to_protocol" in codes

    def test_it_can_be_run(self, window):
        _define(window)
        window._add_ku_step()
        window._select_row(0)
        _select(window, CUSTOM_ID)

        window.run_controller.connect_to(ConnectionSettings(backend="virtual"))
        window._start_run()
        runner = window.runner
        for _ in range(50):
            if not runner.state.is_active:
                break
            runner.tick()

        assert CUSTOM_ID in [msg_id for msg_id, _ in window.run_controller.backend.simulator.received]

    def test_an_unknown_command_is_rejected_by_the_detector(self, window):
        """Which is the point: sending one is how the ERR_MSG_ID path gets tested."""
        _define(window)
        window._add_ku_step()
        window._select_row(0)
        _select(window, CUSTOM_ID)

        window.run_controller.connect_to(ConnectionSettings(backend="virtual"))
        window._start_run()
        runner = window.runner
        for _ in range(50):
            if not runner.state.is_active:
                break
            runner.tick()

        assert "ERR_MSG_ID" in runner.summary.detail

    def test_addresses_can_be_overridden(self, window):
        from detector_scenario_tool.transport.unican import decode_can_id

        _define(window, destination_id=0x09)
        window._add_ku_step()
        window._select_row(0)
        _select(window, CUSTOM_ID)

        window.run_controller.connect_to(ConnectionSettings(backend="virtual"))
        window._start_run()
        window.runner.tick()

        frame = window.run_controller.backend.sent_frames[0]
        destination, _, _ = decode_can_id(frame.can_id, extended=False)
        assert destination == 0x09

    def test_a_custom_telemetry_command_can_repeat(self, window):
        _define(
            window,
            category="KT",
            msg_id=0x0FFE,
            cyclic=CyclicPolicy(enabled=True, period_ms=1000),
        )
        window._add_kt_step()
        window._select_row(0)
        _select(window, 0x0FFE)

        assert window.document.steps[0].cyclic is not None
        assert window.document.steps[0].cyclic.enabled

    def test_opening_a_document_swaps_the_registered_set(self, window, tmp_path):
        from detector_scenario_tool.protocol import registry

        _define(window)
        assert registry.find("KU", CUSTOM_ID) is not None

        window._new_document()

        assert registry.find("KU", CUSTOM_ID) is None
