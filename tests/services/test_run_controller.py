"""When the bus is read, and by whom.

The rule is one reader at a time: a `ScenarioRunner` while a run exists, the `BusMonitor`
otherwise — and *something* reads for as long as the connection is open. Before this, the poll
timer started with a run and stopped with it, so a connected application was deaf.
"""

from __future__ import annotations

import pytest

from detector_scenario_tool.domain.scenario import (
    ScenarioDocument,
    ScenarioMetadata,
    ValidationProfile,
)
from detector_scenario_tool.services.run_controller import RunController
from detector_scenario_tool.transport.backend import ConnectionSettings
from detector_scenario_tool.transport.unican import encode
from message_ids import TM_ACK


@pytest.fixture
def controller(qapp):
    c = RunController()
    yield c
    c.disconnect()


@pytest.fixture
def connected(controller):
    assert controller.connect_to(ConnectionSettings(backend="virtual"))
    return controller


def _empty_document() -> ScenarioDocument:
    return ScenarioDocument(
        schema_version=3,
        metadata=ScenarioMetadata(name="run"),
        validation=ValidationProfile(),
        steps=[],
    )


def _inject(controller, msg_id: int, payload: bytes = b"") -> None:
    backend = controller.backend
    controller.backend.inject(
        encode(msg_id, payload, destination=backend.bvs_address, source=backend.na_address)
    )


class TestListening:
    def test_connecting_starts_the_poll_timer(self, connected):
        assert connected._timer.isActive()
        assert connected.monitor is not None

    def test_disconnecting_stops_it(self, connected):
        connected.disconnect()

        assert not connected._timer.isActive()
        assert connected.monitor is None

    def test_a_message_arriving_outside_a_run_reaches_the_log(self, connected):
        records = []
        connected.record_received.connect(records.append)

        _inject(connected, TM_ACK, bytes(6))
        connected._tick()

        assert [r.msg_id for r in records] == [TM_ACK]

    def test_board_output_arriving_outside_a_run_reaches_the_log(self, connected):
        records = []
        connected.record_received.connect(records.append)

        _inject(connected, 0x0123, b"boot\n")
        connected._tick()

        assert [r.payload for r in records] == [b"boot\n"]

    def test_nothing_is_read_before_connecting(self, controller):
        records = []
        controller.record_received.connect(records.append)

        controller._tick()

        assert records == []


class TestOneReaderAtATime:
    def test_the_runner_owns_the_bus_during_a_run(self, connected):
        from_monitor, from_runner = [], []
        connected.record_received.connect(from_monitor.append)

        runner = connected.start_run(_empty_document())
        runner.message_received.connect(from_runner.append)

        _inject(connected, TM_ACK, bytes(6))
        connected._tick()

        assert [r.msg_id for r in from_runner] == [TM_ACK]
        assert from_monitor == []

    def test_listening_survives_the_end_of_a_run(self, connected):
        records = []
        runner = connected.start_run(_empty_document())
        runner.message_received.connect(records.append)
        connected._tick()                       # an empty scenario finishes at once

        assert not runner.state.is_active
        assert connected._timer.isActive()

        _inject(connected, TM_ACK, bytes(6))
        connected._tick()

        assert [r.msg_id for r in records] == [TM_ACK]

    def test_stopping_a_run_does_not_stop_listening(self, connected):
        """A late answer is exactly what one wants in the log after a step gave up on it."""
        records = []
        runner = connected.start_run(_empty_document())
        runner.message_received.connect(records.append)

        connected.stop()

        assert connected._timer.isActive()

        _inject(connected, TM_ACK, bytes(6))
        connected._tick()

        assert [r.msg_id for r in records] == [TM_ACK]

    def test_reconnecting_hands_the_bus_back_to_the_monitor(self, connected):
        """A runner bound to a closed backend would otherwise keep the bus for ever."""
        connected.start_run(_empty_document())
        connected.disconnect()
        assert connected.runner is None

        assert connected.connect_to(ConnectionSettings(backend="virtual"))
        records = []
        connected.record_received.connect(records.append)

        _inject(connected, TM_ACK, bytes(6))
        connected._tick()

        assert [r.msg_id for r in records] == [TM_ACK]
