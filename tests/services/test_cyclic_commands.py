"""Cyclic telemetry commands.

Decision B5: repeating applies to telemetry commands (КТ) only, is on by default, and stops when
the run stops. Two things had to stay possible on top of that — sending a single КТ for bench
testing, and turning КТ off altogether.
"""

from __future__ import annotations

import pytest

from detector_scenario_tool.domain.scenario import (
    AckPolicy,
    CyclicPolicy,
    MessageRef,
    ScenarioDocument,
    ScenarioMetadata,
    SendMessageStep,
    StepKind,
    ValidationProfile,
    WaitTimeStep,
)
from detector_scenario_tool.protocol import registry
from detector_scenario_tool.services.scenario_runner import ScenarioRunner, StepOutcome
from detector_scenario_tool.transport.simulator import DetectorSimulator
from detector_scenario_tool.transport.virtual import VirtualBackend
from message_ids import STATUS_REQ, TLM_MAGFIELD, TLM_MCILWAIN

MCILWAIN = TLM_MCILWAIN


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, ms: float) -> None:
        self.now += ms


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def simulator():
    return DetectorSimulator()


@pytest.fixture
def backend(simulator):
    b = VirtualBackend(simulator=simulator)
    b.open()
    return b


def _document(*steps) -> ScenarioDocument:
    return ScenarioDocument(
        schema_version=2,
        metadata=ScenarioMetadata(name="cyclic"),
        validation=ValidationProfile(),
        steps=list(steps),
    )


def _tc(msg_id: int = MCILWAIN, sid: str = "s", cyclic: CyclicPolicy | None = None):
    spec = registry.find("KT", msg_id)
    return SendMessageStep(
        id=sid,
        kind=StepKind.SEND_KT,
        message=MessageRef(category="KT", msg_id=msg_id, name=""),
        payload=dict(spec.default_payload()),
        ack_policy=AckPolicy.NONE,
        cyclic=cyclic if cyclic is not None else CyclicPolicy(enabled=True, period_ms=20_000),
    )


def _cc(msg_id: int = STATUS_REQ, sid: str = "c"):
    spec = registry.find("KU", msg_id)
    return SendMessageStep(
        id=sid,
        kind=StepKind.SEND_KU,
        message=MessageRef(category="KU", msg_id=msg_id, name=""),
        payload=dict(spec.default_payload()),
        ack_policy=AckPolicy.EXPECT_ACK,
        ack_timeout_ms=1000,
    )


def _sent_ids(simulator) -> list[int]:
    return [msg_id for msg_id, _ in simulator.received]


class TestDefaults:
    def test_telemetry_commands_repeat_by_default(self):
        for spec in registry.by_category("KT"):
            assert spec.cyclic_default is not None
            assert spec.cyclic_default.enabled
            assert spec.cyclic_default.period_ms == 20_000

    def test_control_commands_never_repeat(self):
        for spec in registry.by_category("KU"):
            assert spec.cyclic_default is None

    def test_the_period_cannot_be_set_to_a_flood(self):
        assert CyclicPolicy(enabled=True, period_ms=0).period_ms >= 100


class TestRepeating:
    def test_a_cyclic_step_keeps_sending(self, backend, clock, simulator):
        document = _document(_tc(), WaitTimeStep(id="w", kind=StepKind.WAIT_TIME, delay_ms=70_000))
        runner = ScenarioRunner(backend, document, clock=clock)
        runner.start()

        runner.tick()                       # sends once and moves on
        assert _sent_ids(simulator) == [MCILWAIN]

        for _ in range(3):
            clock.advance(20_000)
            runner.tick()

        assert _sent_ids(simulator) == [MCILWAIN] * 4

    def test_it_does_not_block_the_scenario(self, backend, clock, simulator):
        """A КТ is never acknowledged, so its step completes at once and the run carries on."""
        document = _document(_tc(sid="s1"), _cc(sid="c1"))
        runner = ScenarioRunner(backend, document, clock=clock)
        runner.start()

        for _ in range(10):
            if not runner.state.is_active:
                break
            runner.tick()

        assert runner.summary.outcomes[0] is StepOutcome.OK
        assert runner.summary.outcomes[1] is StepOutcome.OK

    def test_repeats_stop_when_the_run_stops(self, backend, clock, simulator):
        document = _document(_tc(), WaitTimeStep(id="w", kind=StepKind.WAIT_TIME, delay_ms=90_000))
        runner = ScenarioRunner(backend, document, clock=clock)
        runner.start()
        runner.tick()
        clock.advance(20_000)
        runner.tick()

        runner.stop()
        before = len(simulator.received)

        clock.advance(100_000)
        runner.tick()

        assert len(simulator.received) == before

    def test_repeats_pause_with_the_run(self, backend, clock, simulator):
        document = _document(_tc(), WaitTimeStep(id="w", kind=StepKind.WAIT_TIME, delay_ms=90_000))
        runner = ScenarioRunner(backend, document, clock=clock)
        runner.start()
        runner.tick()

        runner.pause()
        before = len(simulator.received)
        clock.advance(60_000)
        runner.tick()
        assert len(simulator.received) == before

        runner.resume()
        runner.tick()
        assert len(simulator.received) > before

    def test_max_repeats_is_honoured(self, backend, clock, simulator):
        document = _document(
            _tc(cyclic=CyclicPolicy(enabled=True, period_ms=1000, max_repeats=3)),
            WaitTimeStep(id="w", kind=StepKind.WAIT_TIME, delay_ms=90_000),
        )
        runner = ScenarioRunner(backend, document, clock=clock)
        runner.start()
        runner.tick()

        for _ in range(10):
            clock.advance(1000)
            runner.tick()

        assert _sent_ids(simulator) == [MCILWAIN] * 3

    def test_several_cyclic_commands_run_independently(self, backend, clock, simulator):
        document = _document(
            _tc(TLM_MCILWAIN, "s1", CyclicPolicy(enabled=True, period_ms=1000)),
            _tc(TLM_MAGFIELD, "s2", CyclicPolicy(enabled=True, period_ms=3000)),
            WaitTimeStep(id="w", kind=StepKind.WAIT_TIME, delay_ms=90_000),
        )
        runner = ScenarioRunner(backend, document, clock=clock)
        runner.start()
        for _ in range(3):
            runner.tick()

        for _ in range(6):
            clock.advance(1000)
            runner.tick()

        sent = _sent_ids(simulator)
        assert sent.count(TLM_MCILWAIN) == 7      # once, then every second
        assert sent.count(TLM_MAGFIELD) == 3      # once, then every three seconds


class TestSingleShot:
    def test_a_telemetry_command_can_be_sent_once(self, backend, clock, simulator):
        """Needed for bench testing one command in isolation."""
        document = _document(
            _tc(cyclic=CyclicPolicy(enabled=False)),
            WaitTimeStep(id="w", kind=StepKind.WAIT_TIME, delay_ms=90_000),
        )
        runner = ScenarioRunner(backend, document, clock=clock)
        runner.start()
        runner.tick()

        for _ in range(5):
            clock.advance(20_000)
            runner.tick()

        assert _sent_ids(simulator) == [MCILWAIN]
        assert runner.cyclic_tasks == []

    def test_max_repeats_of_one_is_also_a_single_shot(self, backend, clock, simulator):
        document = _document(
            _tc(cyclic=CyclicPolicy(enabled=True, period_ms=1000, max_repeats=1)),
            WaitTimeStep(id="w", kind=StepKind.WAIT_TIME, delay_ms=90_000),
        )
        runner = ScenarioRunner(backend, document, clock=clock)
        runner.start()
        runner.tick()
        for _ in range(5):
            clock.advance(1000)
            runner.tick()

        assert _sent_ids(simulator) == [MCILWAIN]

    def test_a_step_with_no_policy_sends_once(self, backend, clock, simulator):
        step = _tc()
        step.cyclic = None
        document = _document(step, WaitTimeStep(id="w", kind=StepKind.WAIT_TIME, delay_ms=90_000))
        runner = ScenarioRunner(backend, document, clock=clock)
        runner.start()
        runner.tick()
        clock.advance(60_000)
        runner.tick()

        assert _sent_ids(simulator) == [MCILWAIN]


class TestMasterSwitch:
    def test_telemetry_commands_can_be_disabled_entirely(self, backend, clock, simulator):
        document = _document(_tc(sid="s1"), _cc(sid="c1"))
        runner = ScenarioRunner(backend, document, clock=clock, send_telemetry_commands=False)

        runner.start()
        for _ in range(10):
            if not runner.state.is_active:
                break
            runner.tick()

        assert MCILWAIN not in _sent_ids(simulator)
        assert STATUS_REQ in _sent_ids(simulator), "control commands must still go out"

    def test_a_disabled_telemetry_step_is_marked_skipped_not_failed(self, backend, clock):
        document = _document(_tc(sid="s1"))
        runner = ScenarioRunner(backend, document, clock=clock, send_telemetry_commands=False)

        runner.start()
        for _ in range(5):
            if not runner.state.is_active:
                break
            runner.tick()

        assert runner.summary.outcomes[0] is StepOutcome.SKIPPED
        assert runner.summary.failures == 0

    def test_disabling_also_stops_the_repeats(self, backend, clock, simulator):
        document = _document(_tc(), WaitTimeStep(id="w", kind=StepKind.WAIT_TIME, delay_ms=90_000))
        runner = ScenarioRunner(backend, document, clock=clock, send_telemetry_commands=False)
        runner.start()
        runner.tick()

        for _ in range(4):
            clock.advance(20_000)
            runner.tick()

        assert simulator.received == []
        assert runner.cyclic_tasks == []
