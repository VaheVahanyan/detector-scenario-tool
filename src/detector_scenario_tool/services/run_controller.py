"""Connects a backend and drives the runner from a Qt timer.

Everything below this line is synchronous and testable; everything above it is widgets. The
controller is the only place that knows about both.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal

from detector_scenario_tool.domain.scenario import ScenarioDocument
from detector_scenario_tool.services.scenario_runner import RunState, ScenarioRunner
from detector_scenario_tool.transport.backend import (
    CanBackend,
    ConnectionSettings,
    TransportError,
)
from detector_scenario_tool.transport.registry import create_backend

#: How often to service the bus. At 1 Mbit/s a short message takes well under a millisecond, so
#: this is about UI responsiveness rather than about keeping up.
TICK_INTERVAL_MS = 10


class RunController(QObject):
    connection_changed = Signal(bool)     # connected
    error = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.backend: CanBackend | None = None
        self.runner: ScenarioRunner | None = None
        self.settings = ConnectionSettings()

        self._timer = QTimer(self)
        self._timer.setInterval(TICK_INTERVAL_MS)
        self._timer.timeout.connect(self._tick)

    # -- connection --------------------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        return self.backend is not None and self.backend.is_open

    @property
    def is_simulated(self) -> bool:
        return self.backend is None or self.backend.is_simulated

    def connect_to(self, settings: ConnectionSettings) -> bool:
        self.disconnect()

        try:
            backend = create_backend(settings)
            backend.open()
        except (TransportError, ValueError) as exc:
            self.error.emit(str(exc))
            return False

        self.settings = settings
        self.backend = backend
        self.connection_changed.emit(True)
        return True

    def disconnect(self) -> None:
        self.stop()
        if self.backend is not None:
            self.backend.close()
            self.backend = None
            self.connection_changed.emit(False)

    # -- running -----------------------------------------------------------------------

    def start_run(
            self,
            document: ScenarioDocument,
            stop_on_failure: bool = True,
            send_telemetry_commands: bool = True,
    ) -> ScenarioRunner | None:
        if self.backend is None:
            self.error.emit("not connected")
            return None

        self.runner = ScenarioRunner(
            self.backend,
            document,
            stop_on_failure=stop_on_failure,
            send_telemetry_commands=send_telemetry_commands,
            parent=self,
        )
        self.runner.state_changed.connect(self._on_state_changed)
        self.runner.start()
        self._timer.start()
        return self.runner

    def pause(self) -> None:
        if self.runner is not None:
            self.runner.pause()

    def resume(self) -> None:
        if self.runner is not None:
            self.runner.resume()

    def step_once(self) -> None:
        if self.runner is not None:
            self.runner.step_once()

    def stop(self) -> None:
        self._timer.stop()
        if self.runner is not None:
            self.runner.stop()

    def _tick(self) -> None:
        if self.runner is None:
            return
        self.runner.tick()

    def _on_state_changed(self, state: str) -> None:
        if not RunState(state).is_active:
            self._timer.stop()
