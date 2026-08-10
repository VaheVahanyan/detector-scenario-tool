"""Real adapters, via python-can.

A CANable ships with one of two firmwares and each appears differently to Linux:

* **candleLight / gs_usb** — a native SocketCAN interface::

      sudo ip link set can0 up type can bitrate 1000000

* **slcan** — a serial device speaking the Lawicel ASCII protocol, driven either through
  `slcand` or directly by python-can on `/dev/ttyACM0`.

`python-can` is an optional dependency: the import is deferred so the application still starts
without it, exactly as the serial log reader does with `pyserial`.
"""

from __future__ import annotations

from detector_scenario_tool.transport.backend import (
    CanBackend,
    ConnectionSettings,
    TransportError,
)
from detector_scenario_tool.transport.unican import CanFrame

#: python-can's name for each of our backends.
INTERFACE_BY_BACKEND = {
    "socketcan": "socketcan",
    "slcan": "slcan",
}


def python_can_available() -> bool:
    try:
        import can  # noqa: F401
    except Exception:
        return False
    return True


class PythonCanBackend(CanBackend):
    """Shared driver for every python-can interface; the settings pick which one."""

    def __init__(self, settings: ConnectionSettings) -> None:
        super().__init__(settings)
        self._bus = None

    @property
    def interface(self) -> str:
        return INTERFACE_BY_BACKEND.get(self.settings.backend, self.settings.backend)

    def open(self) -> None:
        try:
            import can
        except Exception as exc:  # pragma: no cover - depends on the environment
            raise TransportError(
                "python-can is not installed; install the 'can' extra to use a CAN adapter."
            ) from exc

        if not self.settings.channel:
            raise TransportError("No channel given (for example 'can0' or '/dev/ttyACM0').")

        try:
            self._bus = can.Bus(
                interface=self.interface,
                channel=self.settings.channel,
                bitrate=self.settings.bitrate,
            )
        except Exception as exc:
            raise TransportError(f"Could not open {self.settings.describe()}: {exc}") from exc

        self._open = True

    def close(self) -> None:
        self._open = False
        if self._bus is not None:
            try:
                self._bus.shutdown()
            finally:
                self._bus = None

    def send(self, frame: CanFrame) -> None:
        if self._bus is None:
            raise TransportError("The adapter is not open.")

        import can

        message = can.Message(
            arbitration_id=frame.can_id,
            data=frame.data,
            is_extended_id=frame.extended,
        )
        try:
            self._bus.send(message)
        except Exception as exc:
            raise TransportError(f"Send failed: {exc}") from exc

    def receive(self, timeout: float = 0.0) -> CanFrame | None:
        if self._bus is None:
            return None

        try:
            message = self._bus.recv(timeout=timeout)
        except Exception as exc:
            raise TransportError(f"Receive failed: {exc}") from exc

        if message is None:
            return None

        return CanFrame(
            can_id=message.arbitration_id,
            data=bytes(message.data),
            extended=bool(message.is_extended_id),
        )
