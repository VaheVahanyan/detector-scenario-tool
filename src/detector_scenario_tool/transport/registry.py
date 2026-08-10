"""Which backends the UI can offer, and how to build one.

Registering rather than branching keeps adding an adapter to a single call, and lets a test
substitute a backend without touching the window.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from detector_scenario_tool.transport.backend import CanBackend, ConnectionSettings
from detector_scenario_tool.transport.pycan import PythonCanBackend, python_can_available
from detector_scenario_tool.transport.virtual import VirtualBackend

BackendFactory = Callable[[ConnectionSettings], CanBackend]


@dataclass(frozen=True)
class BackendInfo:
    name: str
    label_key: str
    factory: BackendFactory
    needs_channel: bool
    #: A hint shown next to the channel field, e.g. `can0`.
    channel_example: str = ""
    availability: Callable[[], bool] = lambda: True

    @property
    def available(self) -> bool:
        return self.availability()


_BACKENDS: dict[str, BackendInfo] = {}


def register_backend(info: BackendInfo) -> None:
    _BACKENDS[info.name] = info


def available_backends() -> list[BackendInfo]:
    return list(_BACKENDS.values())


def get_backend_info(name: str) -> BackendInfo | None:
    return _BACKENDS.get(name)


def create_backend(settings: ConnectionSettings) -> CanBackend:
    info = _BACKENDS.get(settings.backend)
    if info is None:
        raise ValueError(f"Unknown transport backend: {settings.backend!r}")
    return info.factory(settings)


register_backend(
    BackendInfo(
        name="virtual",
        label_key="transport.backend.virtual",
        factory=VirtualBackend,
        needs_channel=False,
    )
)
register_backend(
    BackendInfo(
        name="socketcan",
        label_key="transport.backend.socketcan",
        factory=PythonCanBackend,
        needs_channel=True,
        channel_example="can0",
        availability=python_can_available,
    )
)
register_backend(
    BackendInfo(
        name="slcan",
        label_key="transport.backend.slcan",
        factory=PythonCanBackend,
        needs_channel=True,
        channel_example="/dev/ttyACM0",
        availability=python_can_available,
    )
)
