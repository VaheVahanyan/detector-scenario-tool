"""Live capture of the board's serial output: LPUART1, USART2 or the FTDI bridge.

Every line is kept. A `DSTLOG|` line becomes the protocol record it describes; anything else is
the board's own text — `STATE IDLE -> DUTY`, a driver's bring-up report — and becomes a `LOG`
record, exactly as the same text does when the firmware prints it onto CAN. Until this, every
line that was not `DSTLOG` was silently dropped, which on the LPUART and FTDI backends was all
of them.

Binary data is the exception: the FTDI port carries science packets in DUMP, and those are the
packet monitor's business. Such lines are counted and reported, not logged.
"""

from __future__ import annotations

import time

from PySide6.QtCore import QObject, QTimer, Signal

from detector_scenario_tool.domain.log_roles import BOARD_SOURCE
from detector_scenario_tool.logs.text_lines import TextLineSplitter
from detector_scenario_tool.storage.log_io import record_from_line
from detector_scenario_tool.i18n import tr

try:
    import serial
except Exception:
    serial = None


class SerialLogController(QObject):
    record_received = Signal(object)  # LogRecord
    status_changed = Signal(str)
    error_occurred = Signal(str)

    def __init__(
            self,
            port: str,
            baudrate: int = 115200,
            poll_interval_ms: int = 30,
            reconnect_delay_ms: int = 1500,
            clock=None,
    ) -> None:
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.poll_interval_ms = poll_interval_ms
        self.reconnect_delay_ms = reconnect_delay_ms

        #: Same clock as the CAN reader (`time.monotonic`), so text from this port and frames
        #: from the bus interleave by time in one log.
        self._clock = clock or (lambda: time.monotonic() * 1000.0)
        self._serial = None
        self._lines = TextLineSplitter(clock=self._clock)
        self.binary_bytes_skipped = 0

        self._desired_running = False
        self._paused = False

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)

        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setSingleShot(True)
        self._reconnect_timer.timeout.connect(self._attempt_reconnect)

    def start(self) -> None:
        self._desired_running = True
        self._paused = False
        self._attempt_open()

    def stop(self) -> None:
        self._desired_running = False
        self._paused = False

        self._timer.stop()
        self._reconnect_timer.stop()
        self._close_serial()

        self._lines.reset()
        self.status_changed.emit(tr("serial.status.disconnected", port=self.port))

    def pause(self) -> None:
        if not self._desired_running:
            return

        self._paused = True
        self._timer.stop()
        self.status_changed.emit(tr("serial.status.paused", port=self.port))

    def resume(self) -> None:
        if not self._desired_running:
            return

        self._paused = False

        if self._serial is None:
            self._attempt_open()
            return

        if not self._timer.isActive():
            self._timer.start(self.poll_interval_ms)

        self.status_changed.emit(tr("serial.status.resumed", port=self.port))

    def _attempt_open(self) -> None:
        if serial is None:
            self.error_occurred.emit(tr("serial.error.pyserial_missing"))
            return

        if not self._desired_running or self._paused:
            return

        if self._serial is not None:
            return

        try:
            self._serial = serial.Serial(self.port, self.baudrate, timeout=0)
        except Exception as exc:
            self._serial = None
            self.error_occurred.emit(
                tr("serial.error.open_failed", port=self.port, error=str(exc))
            )
            self._schedule_reconnect()
            return

        self._lines.reset()
        self._timer.start(self.poll_interval_ms)
        self.status_changed.emit(
            tr("serial.status.connected", port=self.port, baudrate=self.baudrate)
        )

    def _attempt_reconnect(self) -> None:
        if not self._desired_running or self._paused:
            return
        self.status_changed.emit(tr("serial.status.reconnecting", port=self.port))
        self._attempt_open()

    def _schedule_reconnect(self) -> None:
        if not self._desired_running or self._paused:
            return

        if not self._reconnect_timer.isActive():
            self._reconnect_timer.start(self.reconnect_delay_ms)

    def _close_serial(self) -> None:
        if self._serial is not None:
            try:
                self._serial.close()
            except Exception:
                pass
            self._serial = None

    def _handle_disconnect(self, message: str) -> None:
        self.error_occurred.emit(message)
        self._timer.stop()
        self._close_serial()
        self._schedule_reconnect()

    def _poll(self) -> None:
        if self._serial is None or self._paused:
            return

        try:
            waiting = getattr(self._serial, "in_waiting", 0) or 0
            chunk = self._serial.read(waiting) if waiting > 0 else b""
        except Exception as exc:
            self._handle_disconnect(
                tr("serial.error.read_failed", port=self.port, error=str(exc))
            )
            return

        self.feed(chunk)

    def feed(self, chunk: bytes) -> None:
        """Bytes from the port. Public so tests can drive it without a serial device."""
        lines = self._lines.feed(chunk) if chunk else []
        # A number printed with no newline after it still has to come out eventually.
        lines.extend(self._lines.flush())
        for line in lines:
            self._emit_line(line)

    def _emit_line(self, line: bytes) -> None:
        record = record_from_line(line, int(self._clock()), source=BOARD_SOURCE)
        if record is not None:
            self.record_received.emit(record)
            return

        if line.strip():
            self.binary_bytes_skipped += len(line)
            self.status_changed.emit(
                tr("serial.status.binary_skipped", port=self.port, count=self.binary_bytes_skipped)
            )
