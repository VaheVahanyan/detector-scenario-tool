from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal

from detector_scenario_tool.storage.log_io import LogLoadError, parse_log_line
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
    ) -> None:
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.poll_interval_ms = poll_interval_ms
        self.reconnect_delay_ms = reconnect_delay_ms

        self._serial = None
        self._buffer = bytearray()

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

        self._buffer.clear()
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

        self._buffer.clear()
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
            if waiting <= 0:
                return

            chunk = self._serial.read(waiting)
            if not chunk:
                return

            self._buffer.extend(chunk)
            self._drain_lines()

        except Exception as exc:
            self._handle_disconnect(
                tr("serial.error.read_failed", port=self.port, error=str(exc))
            )

    def _drain_lines(self) -> None:
        while True:
            newline_pos = self._buffer.find(b"\n")
            if newline_pos < 0:
                break

            raw = self._buffer[:newline_pos]
            del self._buffer[: newline_pos + 1]

            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue

            try:
                record = parse_log_line(line)
            except LogLoadError as exc:
                self.error_occurred.emit(f"{self.port}: {exc}")
                continue

            if record is None:
                continue

            self.record_received.emit(record)
