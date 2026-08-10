"""The scenario runner, driven against the simulated detector.

Time is injected, so nothing here sleeps and timeout behaviour is exact rather than flaky.
"""

from __future__ import annotations

import pytest

from detector_scenario_tool.domain.scenario import (
    AckPolicy,
    CommentStep,
    MessageRef,
    RetryPolicy,
    ScenarioDocument,
    ScenarioMetadata,
    SendMessageStep,
    StepKind,
    ValidationProfile,
    WaitForTsStep,
    WaitTimeStep,
)
from detector_scenario_tool.protocol import registry
from detector_scenario_tool.protocol.errors import AckErrorCode
from detector_scenario_tool.services.scenario_runner import (
    RunState,
    ScenarioRunner,
    StepOutcome,
)
from detector_scenario_tool.transport.simulator import DetectorSimulator
from detector_scenario_tool.transport.virtual import VirtualBackend


class FakeClock:
    """Milliseconds, advanced only by the test."""

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
        metadata=ScenarioMetadata(name="run"),
        validation=ValidationProfile(),
        steps=list(steps),
    )


def _send(msg_id: int, sid: str = "s", category: str = "KU", **kw) -> SendMessageStep:
    spec = registry.find(category, msg_id)
    return SendMessageStep(
        id=sid,
        kind=StepKind.SEND_KU if category == "KU" else StepKind.SEND_KT,
        message=MessageRef(category=category, msg_id=msg_id, name=""),
        payload=dict(kw.pop("payload", None) or spec.default_payload()),
        ack_policy=kw.pop("ack_policy", AckPolicy.EXPECT_ACK if category == "KU" else AckPolicy.NONE),
        ack_timeout_ms=kw.pop("ack_timeout_ms", 1000),
        retry=kw.pop("retry", RetryPolicy(attempts=1)),
    )


def _wait_ts(msg_id: int, sid: str = "w", timeout_ms: int = 1000) -> WaitForTsStep:
    return WaitForTsStep(
        id=sid,
        kind=StepKind.WAIT_FOR_TS,
        expected=MessageRef(category="TS", msg_id=msg_id, name=""),
        timeout_ms=timeout_ms,
    )


def _run(runner: ScenarioRunner, clock: FakeClock, max_ticks: int = 200) -> None:
    runner.start()
    for _ in range(max_ticks):
        if not runner.state.is_active:
            return
        runner.tick()
    raise AssertionError(f"runner did not finish; state={runner.state}")


class TestHappyPath:
    def test_status_request_completes(self, backend, clock):
        document = _document(_send(0x0001, "s1"), _wait_ts(0x0200, "w1"))
        runner = ScenarioRunner(backend, document, clock=clock)

        _run(runner, clock)

        assert runner.state is RunState.FINISHED
        assert runner.summary.outcomes == {0: StepOutcome.OK, 1: StepOutcome.OK}
        assert runner.summary.failures == 0

    def test_bytes_actually_reach_the_bus(self, backend, clock):
        document = _document(_send(0x0001, "s1"))
        runner = ScenarioRunner(backend, document, clock=clock)

        _run(runner, clock)

        assert backend.sent_frames
        assert backend.simulator.received[0][0] == 0x0001

    def test_a_long_command_is_segmented_and_reassembled(self, backend, clock):
        """CMD_SET_CFG is 66 bytes, so it crosses the UniCAN long-message path."""
        document = _document(_send(0x0007, "s1"))
        runner = ScenarioRunner(backend, document, clock=clock)

        _run(runner, clock)

        assert runner.summary.outcomes[0] is StepOutcome.OK
        assert len(backend.sent_frames) == 10
        assert len(backend.simulator.received[0][1]) == 66

    def test_comments_and_disabled_steps_are_skipped(self, backend, clock):
        disabled = _send(0x0001, "s1")
        disabled.enabled = False
        document = _document(
            CommentStep(id="c", kind=StepKind.COMMENT, text="note"),
            disabled,
            _send(0x0001, "s2"),
        )
        runner = ScenarioRunner(backend, document, clock=clock)

        _run(runner, clock)

        assert runner.summary.outcomes[0] is StepOutcome.SKIPPED
        assert runner.summary.outcomes[1] is StepOutcome.SKIPPED
        assert runner.summary.outcomes[2] is StepOutcome.OK

    def test_mode_transition_is_tracked_by_the_detector(self, backend, clock):
        """CMD_OBSERVE_CTRL is only valid once observation has been started."""
        document = _document(
            _send(0x0003, "s1"),
            _send(0x0004, "s2"),
        )
        runner = ScenarioRunner(backend, document, clock=clock)

        _run(runner, clock)

        assert runner.summary.outcomes == {0: StepOutcome.OK, 1: StepOutcome.OK}


class TestWaitTime:
    def test_a_pause_waits_for_its_delay(self, backend, clock):
        document = _document(WaitTimeStep(id="w", kind=StepKind.WAIT_TIME, delay_ms=500))
        runner = ScenarioRunner(backend, document, clock=clock)
        runner.start()

        runner.tick()
        assert runner.state is RunState.RUNNING

        clock.advance(499)
        runner.tick()
        assert runner.summary.steps_done == 0

        clock.advance(2)
        runner.tick()
        assert runner.summary.outcomes[0] is StepOutcome.OK


class TestRejection:
    def test_a_rejected_command_fails_the_step(self, backend, clock):
        """CMD_OBSERVE_CTRL outside OBSERVE gets ERR_MODE."""
        document = _document(_send(0x0004, "s1"))
        runner = ScenarioRunner(backend, document, clock=clock)

        _run(runner, clock)

        assert runner.state is RunState.FAILED
        assert runner.summary.outcomes[0] is StepOutcome.REJECTED
        assert "ERR_MODE" in runner.summary.detail

    def test_run_stops_at_the_first_failure_by_default(self, backend, clock):
        document = _document(_send(0x0004, "s1"), _send(0x0001, "s2"))
        runner = ScenarioRunner(backend, document, clock=clock)

        _run(runner, clock)

        assert 1 not in runner.summary.outcomes

    def test_it_can_be_told_to_continue(self, backend, clock):
        document = _document(_send(0x0004, "s1"), _send(0x0001, "s2"))
        runner = ScenarioRunner(backend, document, clock=clock, stop_on_failure=False)

        _run(runner, clock)

        assert runner.summary.outcomes[1] is StepOutcome.OK
        assert runner.summary.failures == 1

    def test_optional_ack_tolerates_rejection_being_absent(self, backend, clock, simulator):
        """CMD_SET_TIME_SPUTNIKS may be ignored entirely (§9.14)."""
        simulator.silent_for = {0x0401}
        document = _document(_send(0x0401, "s1", ack_policy=AckPolicy.OPTIONAL_ACK))
        runner = ScenarioRunner(backend, document, clock=clock)

        runner.start()
        runner.tick()
        clock.advance(1500)
        runner.tick()

        assert runner.summary.outcomes[0] is StepOutcome.OK


class TestTimeouts:
    def test_a_silent_detector_times_the_step_out(self, backend, clock, simulator):
        simulator.silent_for = {0x0001}
        document = _document(_send(0x0001, "s1"))
        runner = ScenarioRunner(backend, document, clock=clock)

        runner.start()
        runner.tick()
        clock.advance(1001)
        runner.tick()

        assert runner.summary.outcomes[0] is StepOutcome.TIMEOUT
        assert runner.state is RunState.FAILED

    def test_a_missing_telemetry_message_times_out(self, backend, clock):
        document = _document(_wait_ts(0x0202, "w1", timeout_ms=800))
        runner = ScenarioRunner(backend, document, clock=clock)

        runner.start()
        runner.tick()
        clock.advance(801)
        runner.tick()

        assert runner.summary.outcomes[0] is StepOutcome.TIMEOUT

    def test_retries_are_attempted_before_giving_up(self, backend, clock, simulator):
        simulator.silent_for = {0x0001}
        document = _document(
            _send(0x0001, "s1", retry=RetryPolicy(attempts=3, retry_on_timeout=True))
        )
        runner = ScenarioRunner(backend, document, clock=clock)

        runner.start()
        runner.tick()
        for _ in range(4):
            clock.advance(1001)
            runner.tick()

        assert len(simulator.received) == 3, "three attempts, per §5.4"
        assert runner.summary.outcomes[0] is StepOutcome.TIMEOUT

    def test_a_retry_succeeds_when_the_detector_starts_answering(
            self, backend, clock, simulator
    ):
        simulator.silent_for = {0x0001}
        document = _document(
            _send(0x0001, "s1", retry=RetryPolicy(attempts=3, retry_on_timeout=True))
        )
        runner = ScenarioRunner(backend, document, clock=clock)

        runner.start()
        runner.tick()
        clock.advance(1001)
        simulator.silent_for = set()
        runner.tick()          # retransmits
        runner.tick()          # picks up the reply

        assert runner.summary.outcomes[0] is StepOutcome.OK


class TestSignals:
    def test_sent_and_received_messages_are_emitted_as_log_records(self, backend, clock):
        document = _document(_send(0x0001, "s1"))
        runner = ScenarioRunner(backend, document, clock=clock)

        sent, received = [], []
        runner.message_sent.connect(sent.append)
        runner.message_received.connect(received.append)

        _run(runner, clock)

        assert [r.msg_id for r in sent] == [0x0001]
        assert [r.direction for r in sent] == ["tx"]
        assert 0x0201 in [r.msg_id for r in received]
        assert {r.direction for r in received} == {"rx"}

    def test_host_and_detector_are_distinguishable_sources(self, backend, clock):
        document = _document(_send(0x0001, "s1"))
        runner = ScenarioRunner(backend, document, clock=clock)

        records = []
        runner.message_sent.connect(records.append)
        runner.message_received.connect(records.append)

        _run(runner, clock)

        assert {r.source for r in records} == {"host", "detector"}

    def test_step_signals_report_progress(self, backend, clock):
        document = _document(_send(0x0001, "s1"), _wait_ts(0x0200, "w1"))
        runner = ScenarioRunner(backend, document, clock=clock)

        started, finished = [], []
        runner.step_started.connect(started.append)
        runner.step_finished.connect(lambda row, outcome, detail: finished.append((row, outcome)))

        _run(runner, clock)

        assert started == [0, 1]
        assert finished == [(0, "ok"), (1, "ok")]

    def test_run_finished_carries_the_summary(self, backend, clock):
        document = _document(_send(0x0001, "s1"))
        runner = ScenarioRunner(backend, document, clock=clock)

        summaries = []
        runner.run_finished.connect(summaries.append)

        _run(runner, clock)

        assert len(summaries) == 1
        assert summaries[0].state is RunState.FINISHED
        assert summaries[0].steps_total == 1


class TestControl:
    def test_pause_and_resume(self, backend, clock):
        document = _document(_send(0x0001, "s1"), _send(0x0001, "s2"))
        runner = ScenarioRunner(backend, document, clock=clock)

        runner.start()
        runner.tick()
        runner.tick()
        runner.pause()

        done_when_paused = runner.summary.steps_done
        runner.tick()
        assert runner.summary.steps_done == done_when_paused

        runner.resume()
        for _ in range(20):
            if not runner.state.is_active:
                break
            runner.tick()

        assert runner.state is RunState.FINISHED

    def test_stop_ends_the_run(self, backend, clock):
        document = _document(_send(0x0001, "s1"), _send(0x0001, "s2"))
        runner = ScenarioRunner(backend, document, clock=clock)

        runner.start()
        runner.tick()
        runner.stop()

        assert runner.state is RunState.STOPPED

    def test_single_stepping_pauses_after_each_step(self, backend, clock):
        document = _document(_send(0x0001, "s1"), _send(0x0001, "s2"))
        runner = ScenarioRunner(backend, document, clock=clock)

        runner.step_once()
        for _ in range(10):
            if runner.state is not RunState.RUNNING:
                break
            runner.tick()

        assert runner.state is RunState.PAUSED
        assert runner.summary.steps_done == 1


class TestAddressChanges:
    def test_set_dest_id_moves_the_target_address(self, backend, clock):
        step = _send(0x0A61, "s1")
        step.payload["destination_id"] = 0x11
        document = _document(step)
        runner = ScenarioRunner(backend, document, clock=clock)

        _run(runner, clock)

        assert runner.summary.outcomes[0] is StepOutcome.OK
        assert runner.na_address == 0x11


class TestTelemetryCommands:
    def test_a_telemetry_command_needs_no_acknowledgement(self, backend, clock):
        """§2.3: КТ are never acknowledged, so the step must not wait for one."""
        document = _document(_send(0x0100, "s1", category="KT"))
        runner = ScenarioRunner(backend, document, clock=clock)

        _run(runner, clock)

        assert runner.summary.outcomes[0] is StepOutcome.OK
        assert runner.state is RunState.FINISHED
