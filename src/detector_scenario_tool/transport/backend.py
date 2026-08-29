"""The interface every CAN adapter is driven through.

Deliberately tiny and synchronous: the Qt layer above polls it, so a backend never has to know
about threads or signals. `transport/registry.py` maps a name to a factory.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from detector_scenario_tool.transport.unican import CanFrame
from detector_scenario_tool.transport_defaults import (
    DEFAULT_BITRATE,
    DEFAULT_BOARD_LOG_ID,
    DEFAULT_BVS_ADDRESS,
    DEFAULT_NA_ADDRESS,
)


class TransportError(RuntimeError):
    """The adapter could not be opened, or failed while open."""


@dataclass(frozen=True)
class ConnectionSettings:
    backend: str = "virtual"
    channel: str = ""
    bitrate: int = DEFAULT_BITRATE
    #: UniCAN allows either identifier width; §B6 of the upgrade plan is still open, so this is a
    #: setting rather than a constant.
    extended_ids: bool = False
    #: Who we are and who we are talking to. Both are «предварительно» in the specification and a
    #: board on the bench may well have been given others, so they belong to the connection rather
    #: than to the protocol. `CMD_SET_DEST_ID` / `CMD_SET_DEVICE_ID` can still move them mid-run;
    #: these are the values the run starts from.
    na_address: int = DEFAULT_NA_ADDRESS
    bvs_address: int = DEFAULT_BVS_ADDRESS
    #: The identifier the controller prints its debug log on. Not an address pair and not UniCAN
    #: at all — see `DEFAULT_BOARD_LOG_ID`. Frames carrying it are taken out of the stream before
    #: reassembly, because `0x7DB` read as UniCAN is a *continuation frame from address 0x1E*, and
    #: 0x1E is the payload: the log would be appended into a long telemetry transfer and ruin it.
    board_log_id: int = DEFAULT_BOARD_LOG_ID

    def describe(self) -> str:
        parts = [self.backend]
        if self.channel:
            parts.append(self.channel)
        parts.append(f"{self.bitrate // 1000} kbit/s")
        parts.append("29-bit" if self.extended_ids else "11-bit")
        # Source→destination, the direction our own frames travel.
        parts.append(f"0x{self.bvs_address:02X}→0x{self.na_address:02X}")
        return " · ".join(parts)


class CanBackend(ABC):
    """A source and sink of CAN frames."""

    def __init__(self, settings: ConnectionSettings) -> None:
        self.settings = settings
        self._open = False

    @property
    def is_open(self) -> bool:
        return self._open

    @property
    def is_simulated(self) -> bool:
        """True when nothing physical is being driven — used to skip the safety prompt."""
        return False

    @abstractmethod
    def open(self) -> None:
        ...

    @abstractmethod
    def close(self) -> None:
        ...

    @abstractmethod
    def send(self, frame: CanFrame) -> None:
        ...

    @abstractmethod
    def receive(self, timeout: float = 0.0) -> CanFrame | None:
        """One frame, or None if none arrived within `timeout` seconds."""

    def drain(self, limit: int = 256) -> list[CanFrame]:
        """Every frame available right now, up to `limit`."""
        frames = []
        for _ in range(limit):
            frame = self.receive(timeout=0.0)
            if frame is None:
                break
            frames.append(frame)
        return frames
