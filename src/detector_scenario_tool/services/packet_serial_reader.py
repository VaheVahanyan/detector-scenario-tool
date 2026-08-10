"""Reads the science-data stream from a serial port.

DUMP output leaves the payload through the FTDI bridge on the control board (its signals are in
the "Статус НА" word: `PU_FTDI_PS`, `PU_FTDI_PSON`, `PU_FTDI_RES`), so on Linux the kernel's
`ftdi_sio` driver presents it as `/dev/ttyUSB0`.

This is deliberately separate from `serial_log_controller`: that one parses text `DSTLOG|` lines,
while science data is a binary stream that must be handed to the packet framer byte for byte.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal

from detector_scenario_tool.i18n import tr

try:
    import serial
except Exception:  # pragma: no cover - depends on the environment
    serial = None

#: FTDI's default latency timer is 16 ms, which throttles a stream of small reads. Polling faster
#: than that costs nothing and lets a lowered latency timer actually help.
POLL_INTERVAL_MS = 5

#: Read at most this much per poll, so a fast source cannot starve the event loop.
MAX_READ = 1 << 16

DEFAULT_PORT = "/dev/ttyUSB0"
DEFAULT_BAUDRATE = 921_600


class PacketSerialReader(QObject):
    data_received = Signal(bytes)
    status_changed = Signal(str)
    error_occurred = Signal(str)

    def __init__(
            self,
            port: str = DEFAULT_PORT,
            baudrate: int = DEFAULT_BAUDRATE,
            parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.port = port
        self.baudrate = baudrate

        self._serial = None
        self._timer = QTimer(self)
        self._timer.setInterval(POLL_INTERVAL_MS)
        self._timer.timeout.connect(self._poll)

    @property
    def is_running(self) -> bool:
        return self._serial is not None

    @staticmethod
    def is_available() -> bool:
        return serial is not None

    def start(self) -> bool:
        if serial is None:
            self.error_occurred.emit(tr("packets.serial.pyserial_missing"))
            return False

        self.stop()

        try:
            self._serial = serial.Serial(self.port, self.baudrate, timeout=0)
        except Exception as exc:
            self._serial = None
            self.error_occurred.emit(tr("packets.serial.open_failed", port=self.port, error=exc))
            return False

        self._timer.start()
        self.status_changed.emit(tr("packets.serial.reading", port=self.port))
        return True

    def stop(self) -> None:
        self._timer.stop()
        if self._serial is not None:
            try:
                self._serial.close()
            finally:
                self._serial = None
                self.status_changed.emit(tr("packets.serial.stopped"))

    def _poll(self) -> None:
        if self._serial is None:
            return

        try:
            waiting = self._serial.in_waiting
            if not waiting:
                return
            chunk = self._serial.read(min(waiting, MAX_READ))
        except Exception as exc:
            self.error_occurred.emit(tr("packets.serial.read_failed", error=exc))
            self.stop()
            return

        if chunk:
            self.data_received.emit(bytes(chunk))
