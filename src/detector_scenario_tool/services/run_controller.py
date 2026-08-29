"""Connects a backend and drives the runner from a Qt timer.

Everything below this line is synchronous and testable; everything above it is widgets. The
controller is the only place that knows about both.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal

from detector_scenario_tool.domain.scenario import ScenarioDocument
from detector_scenario_tool.services.bus_monitor import BusMonitor
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
    record_received = Signal(object)      # LogRecord, from the monitor between runs

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.backend: CanBackend | None = None
        self.runner: ScenarioRunner | None = None
        self.settings = ConnectionSettings()
        #: Reads the bus whenever no runner is doing it. See `_tick`.
        self.monitor: BusMonitor | None = None

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
        self.monitor = BusMonitor(
            extended=settings.extended_ids,
            board_log_id=settings.board_log_id,
        )
        # Being connected is enough to start listening. The bus does not wait for a run to begin,
        # and neither should the log: the board talks before, between and after runs.
        self._sync_timer()
        self.connection_changed.emit(True)
        return True

    def disconnect(self) -> None:
        self.stop()
        # The runner goes with the connection it was driving. Keeping it would leave `_tick`
        # servicing a runner bound to a closed backend, and the monitor would never get the bus
        # back after a reconnect.
        self.runner = None
        if self.backend is not None:
            self.backend.close()
            self.backend = None
            self.monitor = None
            self._sync_timer()
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
            na_address=self.settings.na_address,
            bvs_address=self.settings.bvs_address,
            stop_on_failure=stop_on_failure,
            send_telemetry_commands=send_telemetry_commands,
            parent=self,
        )
        self.runner.state_changed.connect(self._on_state_changed)
        self.runner.start()
        self._sync_timer()
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
        if self.runner is not None:
            self.runner.stop()
        # Stopping the run does not stop listening — a late answer is exactly what one wants in
        # the log after a step gave up on it.
        self._sync_timer()

    # -- the loop ----------------------------------------------------------------------

    def _tick(self) -> None:
        """One reader at a time.

        While a runner exists it services the bus itself, including after the run has finished: it
        keeps a reassembler with any half-received transfer in it, so handing the bus back to a
        second reader mid-frame would lose the rest of the message.
        """
        if self.runner is not None:
            self.runner.tick()
            return

        if self.backend is None or self.monitor is None:
            return

        for record in self.monitor.poll(self.backend):
            self.record_received.emit(record)

    def _sync_timer(self) -> None:
        """The timer runs for as long as there is an open backend to read."""
        if self.backend is not None and self.backend.is_open:
            self._timer.start()
        else:
            self._timer.stop()

    def _on_state_changed(self, state: str) -> None:
        if not RunState(state).is_active:
            self._sync_timer()
