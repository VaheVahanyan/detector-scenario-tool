"""Bus addresses in the connection panel.

Both are «предварительно» in the specification and either can be changed on the board, so a fixed
`05h`/`1Eh` meant there was no way to tell the application which board it was talking to.
"""

from __future__ import annotations

import pytest

from detector_scenario_tool.transport.backend import ConnectionSettings
from detector_scenario_tool.transport.unican import decode_can_id
from detector_scenario_tool.transport_defaults import (
    DEFAULT_BOARD_LOG_ID,
    DEFAULT_BVS_ADDRESS,
    DEFAULT_NA_ADDRESS,
)
from message_ids import STATUS_REQ


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    from detector_scenario_tool.ui.main_window import MainWindow

    w = MainWindow()
    qtbot.addWidget(w)
    return w


@pytest.fixture
def panel(window):
    return window.run_panel


def _add_send(window, msg_id: int) -> None:
    window._add_ku_step()
    window._select_row(len(window.document.steps) - 1)
    selector = window.inspector_panel.msg_selector
    for i in range(selector.count()):
        if selector.itemData(i)[1] == msg_id:
            selector.setCurrentIndex(i)
            return
    raise AssertionError(f"0x{msg_id:04X} is not offered by the inspector")


class TestPanel:
    def test_the_defaults_are_the_protocol_defaults(self, panel):
        assert panel.settings().bvs_address == DEFAULT_BVS_ADDRESS
        assert panel.settings().na_address == DEFAULT_NA_ADDRESS

    def test_the_fields_are_read_back(self, panel):
        panel.bvs_address_spin.setValue(0x07)
        panel.na_address_spin.setValue(0x11)

        settings = panel.settings()

        assert (settings.bvs_address, settings.na_address) == (0x07, 0x11)

    def test_settings_are_applied_to_the_fields(self, panel):
        panel.apply_settings(ConnectionSettings(backend="virtual", na_address=0x0A, bvs_address=0x02))

        assert panel.na_address_spin.value() == 0x0A
        assert panel.bvs_address_spin.value() == 0x02

    def test_they_are_shown_in_hex_the_way_the_protocol_writes_them(self, panel):
        panel.na_address_spin.setValue(0x1E)

        assert panel.na_address_spin.text() == "0x1E"

    def test_hex_can_be_typed_in(self, panel):
        assert panel.na_address_spin.valueFromText("0x1F") == 0x1F
        assert panel.na_address_spin.valueFromText("1f") == 0x1F

    def test_the_fields_lock_while_connected(self, panel):
        panel.set_connected(True)
        assert not panel.na_address_spin.isEnabled()

        panel.set_connected(False)
        assert panel.na_address_spin.isEnabled()


class TestRangeFollowsTheIdentifierWidth:
    def test_five_bits_for_a_standard_identifier(self, panel):
        panel.extended_checkbox.setChecked(False)

        assert panel.na_address_spin.maximum() == 0x1F

    def test_fourteen_bits_for_an_extended_one(self, panel):
        panel.extended_checkbox.setChecked(True)

        assert panel.na_address_spin.maximum() == 0x3FFF

    def test_narrowing_the_identifier_clamps_an_address_that_no_longer_fits(self, panel):
        panel.extended_checkbox.setChecked(True)
        panel.na_address_spin.setValue(0x2000)

        panel.extended_checkbox.setChecked(False)

        assert panel.na_address_spin.value() <= 0x1F

    def test_a_wide_address_survives_being_applied(self, panel):
        """The range has to widen before the value is set, or the value is silently clamped."""
        panel.apply_settings(
            ConnectionSettings(backend="virtual", extended_ids=True, na_address=0x2000)
        )

        assert panel.na_address_spin.value() == 0x2000


class TestTheyReachTheBus:
    def test_the_frame_is_addressed_as_configured(self, window):
        _add_send(window, STATUS_REQ)
        window.run_panel.bvs_address_spin.setValue(0x07)
        window.run_panel.na_address_spin.setValue(0x11)
        window._connect_transport(window.run_panel.settings())

        window._start_run()
        window.runner.tick()

        frame = window.run_controller.backend.sent_frames[0]
        destination, source, _ = decode_can_id(frame.can_id, extended=False)
        assert (source, destination) == (0x07, 0x11)

    def test_the_runner_starts_from_them(self, window):
        window.run_panel.na_address_spin.setValue(0x11)
        window._connect_transport(window.run_panel.settings())

        window._start_run()

        assert window.runner.na_address == 0x11

    def test_they_are_remembered_between_sessions(self, window):
        from detector_scenario_tool.app import settings as app_settings

        window.run_panel.bvs_address_spin.setValue(0x07)
        window.run_panel.na_address_spin.setValue(0x11)
        window._connect_transport(window.run_panel.settings())

        restored = app_settings.load_connection_settings()
        assert (restored.bvs_address, restored.na_address) == (0x07, 0x11)

    def test_the_confirmation_says_who_is_being_addressed(self):
        """The LIVE prompt describes the connection; the addresses are part of what is at stake."""
        described = ConnectionSettings(backend="socketcan", channel="can0").describe()

        assert "0x05→0x1E" in described


class TestBoardLogIdentifier:
    """Not an address: the CAN identifier the firmware's debug log goes out on.

    A firmware constant (`LOG_BACKEND_CAN_DEBUG_ID`), so another build may use another number.
    """

    def test_the_default_is_the_firmware_constant(self, panel):
        assert panel.settings().board_log_id == DEFAULT_BOARD_LOG_ID == 0x7DB

    def test_it_is_three_hex_digits_wide(self, panel):
        assert panel.board_log_spin.text() == "0x7DB"

    def test_the_whole_standard_range_is_allowed(self, panel):
        """It is a raw identifier, not an address inside one, so 11 bits are available."""
        assert panel.board_log_spin.maximum() == 0x7FF

    def test_it_does_not_follow_the_address_width(self, panel):
        panel.extended_checkbox.setChecked(True)

        assert panel.board_log_spin.maximum() == 0x7FF

    def test_it_is_read_back_and_applied(self, panel):
        panel.board_log_spin.setValue(0x321)
        assert panel.settings().board_log_id == 0x321

        panel.apply_settings(ConnectionSettings(backend="virtual", board_log_id=0x123))
        assert panel.board_log_spin.value() == 0x123

    def test_it_locks_while_connected(self, panel):
        panel.set_connected(True)
        assert not panel.board_log_spin.isEnabled()

    def test_it_reaches_the_reader(self, window):
        window.run_panel.board_log_spin.setValue(0x321)
        window._connect_transport(window.run_panel.settings())

        assert window.run_controller.monitor.board_log.identifier == 0x321

    def test_it_is_remembered_between_sessions(self, window):
        from detector_scenario_tool.app import settings as app_settings

        window.run_panel.board_log_spin.setValue(0x321)
        window._connect_transport(window.run_panel.settings())

        assert app_settings.load_connection_settings().board_log_id == 0x321

    def test_a_line_arriving_while_merely_connected_reaches_the_log(self, window):
        from detector_scenario_tool.transport.unican import CanFrame

        window._connect_transport(window.run_panel.settings())
        window.run_controller.backend.inject([CanFrame(DEFAULT_BOARD_LOG_ID, b"boot ok\r\n")])
        window.run_controller._tick()

        assert [r.payload for r in window.log_records] == [b"boot ok\r\n"]
        assert window.log_records[0].is_board_log
