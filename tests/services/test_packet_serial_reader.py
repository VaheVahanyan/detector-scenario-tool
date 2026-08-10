"""Reading the science-data stream from the FTDI bridge.

Binary, unlike the debug-log reader next to it, and wired straight into the packet framer.
"""

from __future__ import annotations

import pytest

from detector_scenario_tool.logs.packet_stream import build_packet
from detector_scenario_tool.services import packet_serial_reader
from detector_scenario_tool.services.packet_serial_reader import (
    DEFAULT_BAUDRATE,
    DEFAULT_PORT,
    PacketSerialReader,
)


class FakeSerial:
    """Hands out a scripted stream in the chunks a real port would."""

    def __init__(self, port, baudrate, timeout=0):
        self.port = port
        self.baudrate = baudrate
        self.closed = False
        self.pending = bytearray()
        self.fail_on_read = False

    @property
    def in_waiting(self) -> int:
        return len(self.pending)

    def read(self, size: int) -> bytes:
        if self.fail_on_read:
            raise OSError("device disconnected")
        chunk = bytes(self.pending[:size])
        del self.pending[:size]
        return chunk

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def fake_serial(monkeypatch):
    created = []

    class Module:
        @staticmethod
        def Serial(port, baudrate, timeout=0):
            port_obj = FakeSerial(port, baudrate, timeout)
            created.append(port_obj)
            return port_obj

    monkeypatch.setattr(packet_serial_reader, "serial", Module)
    return created


class TestDefaults:
    def test_the_ftdi_bridge_is_the_default_port(self):
        """The board's science-data output goes through FTDI, which Linux shows as ttyUSB0."""
        assert DEFAULT_PORT == "/dev/ttyUSB0"

    def test_the_reader_starts_stopped(self, qapp):
        assert not PacketSerialReader().is_running


class TestReading:
    def test_starting_opens_the_requested_port(self, qapp, fake_serial):
        reader = PacketSerialReader(port="/dev/ttyUSB3", baudrate=460_800)
        assert reader.start()

        assert fake_serial[0].port == "/dev/ttyUSB3"
        assert fake_serial[0].baudrate == 460_800
        assert reader.is_running

    def test_bytes_are_emitted_as_they_arrive(self, qapp, fake_serial):
        reader = PacketSerialReader()
        reader.start()

        chunks = []
        reader.data_received.connect(chunks.append)

        fake_serial[0].pending.extend(b"\x01\x02\x03")
        reader._poll()

        assert chunks == [b"\x01\x02\x03"]

    def test_nothing_is_emitted_when_the_port_is_quiet(self, qapp, fake_serial):
        reader = PacketSerialReader()
        reader.start()

        chunks = []
        reader.data_received.connect(chunks.append)
        reader._poll()

        assert chunks == []

    def test_stopping_closes_the_port(self, qapp, fake_serial):
        reader = PacketSerialReader()
        reader.start()
        reader.stop()

        assert fake_serial[0].closed
        assert not reader.is_running

    def test_a_read_failure_stops_the_reader_and_reports(self, qapp, fake_serial):
        reader = PacketSerialReader()
        reader.start()

        errors = []
        reader.error_occurred.connect(errors.append)

        fake_serial[0].pending.extend(b"\x01")
        fake_serial[0].fail_on_read = True
        reader._poll()

        assert errors
        assert not reader.is_running

    def test_a_failed_open_is_reported_not_raised(self, qapp, monkeypatch):
        class Failing:
            @staticmethod
            def Serial(*a, **kw):
                raise OSError("No such file or directory")

        monkeypatch.setattr(packet_serial_reader, "serial", Failing)
        reader = PacketSerialReader()

        errors = []
        reader.error_occurred.connect(errors.append)

        assert reader.start() is False
        assert errors
        assert not reader.is_running

    def test_it_degrades_without_pyserial(self, qapp, monkeypatch):
        """The application must keep working when the optional dependency is absent."""
        monkeypatch.setattr(packet_serial_reader, "serial", None)
        reader = PacketSerialReader()

        errors = []
        reader.error_occurred.connect(errors.append)

        assert not PacketSerialReader.is_available()
        assert reader.start() is False
        assert errors


class TestIntoTheFramer:
    def test_a_streamed_dump_reaches_the_packet_counters(self, qapp, fake_serial):
        """The point of the reader: bytes off the port become counted packets."""
        from detector_scenario_tool.ui.panels.packets_panel import PacketsPanel

        panel = PacketsPanel()
        panel.port_edit.setText("/dev/ttyUSB0")
        assert panel.start_reading()

        raw = b"".join(build_packet(9, n, bytes([n])) for n in range(3))
        # Arrive in chunks that do not line up with packet boundaries.
        for i in range(0, len(raw), 700):
            fake_serial[0].pending.extend(raw[i:i + 700])
            panel.reader._poll()

        assert panel.received_label.text() == "3"
        assert panel.session_label.text() == "9"

        panel.stop_reading()
        assert not panel.reader.is_running

    def test_the_controls_follow_the_reader_state(self, qapp, fake_serial):
        from detector_scenario_tool.ui.panels.packets_panel import PacketsPanel

        panel = PacketsPanel()
        assert panel.start_button.isEnabled()

        panel.start_reading()
        assert not panel.start_button.isEnabled()
        assert panel.stop_button.isEnabled()
        assert not panel.port_edit.isEnabled()

        panel.stop_reading()
        assert panel.start_button.isEnabled()
        assert not panel.stop_button.isEnabled()

    def test_an_invalid_baud_rate_falls_back_to_the_default(self, qapp, fake_serial):
        from detector_scenario_tool.ui.panels.packets_panel import PacketsPanel

        panel = PacketsPanel()
        panel.baud_combo.setCurrentText("not a number")
        panel.start_reading()

        assert panel.reader.baudrate == DEFAULT_BAUDRATE
