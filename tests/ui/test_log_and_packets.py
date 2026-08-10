"""The reworked log panel and the DUMP packet monitor."""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt

from detector_scenario_tool.domain.logs import LogRecord
from detector_scenario_tool.logs.packet_stream import build_packet
from detector_scenario_tool.protocol import crc16
from detector_scenario_tool.transport.backend import ConnectionSettings
from detector_scenario_tool.ui.models.log_table_model import VIEW_DECODED, VIEW_RAW


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    from detector_scenario_tool.ui.main_window import MainWindow

    w = MainWindow()
    qtbot.addWidget(w)
    return w


def _records() -> list[LogRecord]:
    return [
        LogRecord(
            timestamp_ms=10, direction="tx", category="KU", msg_id=0x0001,
            payload=b"\xaa" * 6, source="host", can_id=0x0BE, frame_count=1,
        ),
        LogRecord(
            timestamp_ms=20, direction="rx", category="TS", msg_id=0x0201,
            payload=bytes([0x01, 0x00, 0x00, 0xAA, 0xAA, 0xAA]),
            source="detector", can_id=0x3C5,
        ),
        LogRecord(
            timestamp_ms=30, direction="rx", category="TS", msg_id=0x0000,
            payload=b"\x01\x02", source="detector", can_id=0x3C5,
            valid=False, note="CRC error",
        ),
    ]


def _headers(model) -> list[str]:
    return [
        model.headerData(c, Qt.Orientation.Horizontal) for c in range(model.columnCount())
    ]


class TestSinglePort:
    def test_only_one_port_is_offered(self, window):
        """The second port was for capturing the sender; the runner logs that itself now."""
        panel = window.log_panel
        assert hasattr(panel, "port_edit")
        assert not hasattr(panel, "port2_edit")

    def test_starting_live_capture_passes_one_port(self, window, qtbot):
        received = []
        window.log_panel.start_live_requested.connect(
            lambda port, baud: received.append((port, baud))
        )
        window.log_panel.port_edit.setText("/dev/ttyUSB0")
        window.log_panel._emit_start_live()

        assert received == [("/dev/ttyUSB0", 115200)]

    def test_the_host_side_is_logged_by_the_runner(self, window):
        window._add_ku_step()
        window.run_controller.connect_to(ConnectionSettings(backend="virtual"))
        window._start_run()
        runner = window.runner
        for _ in range(30):
            if not runner.state.is_active:
                break
            runner.tick()

        assert any(r.source == "host" and r.direction == "tx" for r in window.log_records)


class TestViewModes:
    def test_the_two_modes_have_different_columns(self, window):
        model = window.log_panel.model

        model.set_view_mode(VIEW_DECODED)
        decoded = _headers(model)
        model.set_view_mode(VIEW_RAW)
        raw = _headers(model)

        assert decoded != raw
        assert len(raw) > len(decoded)

    def test_raw_shows_the_wire_detail(self, window):
        window.log_panel.set_records(_records())
        window.log_panel.model.set_view_mode(VIEW_RAW)
        model = window.log_panel.model

        row = [model.data(model.index(0, c)) for c in range(model.columnCount())]
        assert "0x0BE" in row
        assert "host" in row

    def test_decoded_shows_the_message_name(self, window):
        window.log_panel.set_records(_records())
        window.log_panel.model.set_view_mode(VIEW_DECODED)
        model = window.log_panel.model

        assert "0x0201" in model.data(model.index(1, 3))

    def test_switching_modes_keeps_the_rows(self, window):
        window.log_panel.set_records(_records())
        model = window.log_panel.model

        model.set_view_mode(VIEW_RAW)
        assert model.rowCount() == 3
        model.set_view_mode(VIEW_DECODED)
        assert model.rowCount() == 3

    def test_a_broken_frame_is_shown_not_dropped(self, window):
        """A frame that failed reassembly is exactly what raw view exists for."""
        window.log_panel.set_records(_records())
        window.log_panel.model.set_view_mode(VIEW_RAW)
        model = window.log_panel.model

        row = [model.data(model.index(2, c)) for c in range(model.columnCount())]
        assert any("broken" in str(v) or "ошибка" in str(v) for v in row)

    def test_a_broken_frame_reports_why_instead_of_decoding(self, window):
        window.log_panel.set_records(_records())
        window.log_panel.model.set_view_mode(VIEW_DECODED)
        model = window.log_panel.model

        assert model.data(model.index(2, 4)) == "CRC error"

    def test_the_detail_pane_decodes_the_selected_row(self, window):
        window.log_panel.set_records(_records())
        window.log_panel.table.selectRow(1)
        window.log_panel._update_detail()

        text = window.log_panel.detail_view.toPlainText()
        assert "TM_ACK" in text
        assert "§4.2" in text

    def test_the_detail_pane_explains_a_broken_frame(self, window):
        window.log_panel.set_records(_records())
        window.log_panel.table.selectRow(2)
        window.log_panel._update_detail()

        assert "CRC error" in window.log_panel.detail_view.toPlainText()


class TestPacketsPanel:
    def test_packets_are_counted(self, window):
        panel = window.packets_panel
        panel.feed(b"".join(build_packet(7, n, bytes([n])) for n in range(4)))

        assert panel.received_label.text() == "4"
        assert panel.session_label.text() == "7"

    def test_the_checksum_is_reported_as_unchecked_while_unconfigured(self, window):
        """Printing "0 passed" would read as "none are good", which is not what is known."""
        panel = window.packets_panel
        panel.feed(build_packet(1, 0, b"\x01"))

        assert panel.valid_label.text() not in ("0", "")
        assert panel.crc_notice.isVisibleTo(panel)

    def test_the_checksum_is_counted_once_configured(self, window, monkeypatch):
        monkeypatch.setattr(crc16, "NI_PACKET_CRC", crc16.VARIANTS_BY_NAME["ccitt-false"])
        panel = window.packets_panel
        panel.feed(build_packet(1, 0, b"\x01"))

        assert panel.valid_label.text() == "1"
        assert not panel.crc_notice.isVisibleTo(panel)

    def test_storage_is_off_by_default(self, window):
        panel = window.packets_panel
        panel.feed(build_packet(1, 0, b"\x01"))

        assert panel.stream.packets == []

    def test_storage_can_be_switched_on(self, window):
        panel = window.packets_panel
        panel.store_checkbox.setChecked(True)
        panel.feed(build_packet(1, 0, b"\x01"))

        assert len(panel.stream.packets) == 1

    def test_switching_storage_off_releases_the_packets(self, window):
        panel = window.packets_panel
        panel.store_checkbox.setChecked(True)
        panel.feed(build_packet(1, 0, b"\x01"))
        panel.store_checkbox.setChecked(False)

        assert panel.stream.packets == []

    def test_stored_packets_can_be_written_out(self, window, tmp_path):
        panel = window.packets_panel
        panel.store_checkbox.setChecked(True)
        panel.feed(build_packet(7, 3, b"\x01"))

        written = panel.save_stored_packets(tmp_path)

        assert written == 1
        files = list(tmp_path.glob("*.bin"))
        assert len(files) == 1
        assert "session00007" in files[0].name
        assert len(files[0].read_bytes()) == 2048

    def test_a_capture_file_can_be_loaded(self, window, tmp_path):
        capture = tmp_path / "dump.bin"
        capture.write_bytes(b"".join(build_packet(2, n, bytes([n])) for n in range(3)))

        window.packets_panel.load_capture(capture)

        assert window.packets_panel.received_label.text() == "3"

    def test_clearing_resets_the_counters(self, window):
        panel = window.packets_panel
        panel.feed(build_packet(1, 0, b"\x01"))
        panel.clear()

        assert panel.received_label.text() == "0"

    def test_crc_detection_reports_a_match(self, window, monkeypatch):
        """The way out of B2 without guessing: work the variant back from a real capture."""
        variant = crc16.VARIANTS_BY_NAME["modbus"]
        monkeypatch.setattr(crc16, "NI_PACKET_CRC", variant)
        raw = build_packet(1, 0, b"\x01\x02\x03")
        monkeypatch.setattr(crc16, "NI_PACKET_CRC", None)

        panel = window.packets_panel
        panel.store_checkbox.setChecked(True)
        panel.feed(raw)
        panel._detect_crc_variant()

        assert "modbus" in panel.detect_result.text()

    def test_crc_detection_says_so_when_nothing_matches(self, window):
        panel = window.packets_panel
        panel.store_checkbox.setChecked(True)
        panel.feed(build_packet(1, 0, b"\x01", crc=0x0001))
        panel._detect_crc_variant()

        assert panel.detect_result.text()


class TestExpectedCount:
    def test_the_dump_acknowledgement_sets_the_progress_target(self, window):
        """§4.2 note 1: bytes 5-7 of the CMD_DUMP acknowledgement carry the packet count."""
        window._add_ku_step()
        window._select_row(0)
        selector = window.inspector_panel.msg_selector
        for i in range(selector.count()):
            if selector.itemData(i)[1] == 0x0006:
                selector.setCurrentIndex(i)
                break
        window.document.steps[0].payload["requested_packet_count"] = 5

        window.run_controller.connect_to(ConnectionSettings(backend="virtual"))
        window._start_run()
        runner = window.runner
        for _ in range(30):
            if not runner.state.is_active:
                break
            runner.tick()

        assert window.packets_panel._expected_packets == 5

    def test_an_ordinary_acknowledgement_does_not_set_it(self, window):
        window._add_ku_step()          # CMD_TELEM_REQ by default
        window.run_controller.connect_to(ConnectionSettings(backend="virtual"))
        window._start_run()
        runner = window.runner
        for _ in range(30):
            if not runner.state.is_active:
                break
            runner.tick()

        assert window.packets_panel._expected_packets is None
