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
from detector_scenario_tool.domain.logs import LOG_CATEGORY
from detector_scenario_tool.transport.simulator import DetectorSimulator
from detector_scenario_tool.transport.unican import CanFrame, encode
from detector_scenario_tool.transport.virtual import VirtualBackend
from message_ids import OBSERVE_CTRL, OBSERVE_START, SET_CFG, SET_DEST_ID, SET_TIME_BVS, STATUS_REQ, TLM_MCILWAIN, TM_ACK, TM_STATUS, TM_TELEMETRY


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
        document = _document(_send(STATUS_REQ, "s1"), _wait_ts(TM_STATUS, "w1"))
        runner = ScenarioRunner(backend, document, clock=clock)

        _run(runner, clock)

        assert runner.state is RunState.FINISHED
        assert runner.summary.outcomes == {0: StepOutcome.OK, 1: StepOutcome.OK}
        assert runner.summary.failures == 0

    def test_bytes_actually_reach_the_bus(self, backend, clock):
        document = _document(_send(STATUS_REQ, "s1"))
        runner = ScenarioRunner(backend, document, clock=clock)

        _run(runner, clock)

        assert backend.sent_frames
        assert backend.simulator.received[0][0] == STATUS_REQ

    def test_a_long_command_is_segmented_and_reassembled(self, backend, clock):
        """CMD_SET_CFG is 68 bytes in v2.1, so it crosses the UniCAN long-message path."""
        document = _document(_send(SET_CFG, "s1"))
        runner = ScenarioRunner(backend, document, clock=clock)

        _run(runner, clock)

        assert runner.summary.outcomes[0] is StepOutcome.OK
        # 68 content bytes + 2 CRC = 70, so a start frame plus nine data frames.
        assert len(backend.sent_frames) == 10
        assert len(backend.simulator.received[0][1]) == 68

    def test_comments_and_disabled_steps_are_skipped(self, backend, clock):
        disabled = _send(STATUS_REQ, "s1")
        disabled.enabled = False
        document = _document(
            CommentStep(id="c", kind=StepKind.COMMENT, text="note"),
            disabled,
            _send(STATUS_REQ, "s2"),
        )
        runner = ScenarioRunner(backend, document, clock=clock)

        _run(runner, clock)

        assert runner.summary.outcomes[0] is StepOutcome.SKIPPED
        assert runner.summary.outcomes[1] is StepOutcome.SKIPPED
        assert runner.summary.outcomes[2] is StepOutcome.OK

    def test_mode_transition_is_tracked_by_the_detector(self, backend, clock):
        """CMD_OBSERVE_CTRL is only valid once observation has been started."""
        document = _document(
            _send(OBSERVE_START, "s1"),
            _send(OBSERVE_CTRL, "s2"),
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
        document = _document(_send(OBSERVE_CTRL, "s1"))
        runner = ScenarioRunner(backend, document, clock=clock)

        _run(runner, clock)

        assert runner.state is RunState.FAILED
        assert runner.summary.outcomes[0] is StepOutcome.REJECTED
        assert "ERR_MODE" in runner.summary.detail

    def test_run_stops_at_the_first_failure_by_default(self, backend, clock):
        document = _document(_send(OBSERVE_CTRL, "s1"), _send(STATUS_REQ, "s2"))
        runner = ScenarioRunner(backend, document, clock=clock)

        _run(runner, clock)

        assert 1 not in runner.summary.outcomes

    def test_it_can_be_told_to_continue(self, backend, clock):
        document = _document(_send(OBSERVE_CTRL, "s1"), _send(STATUS_REQ, "s2"))
        runner = ScenarioRunner(backend, document, clock=clock, stop_on_failure=False)

        _run(runner, clock)

        assert runner.summary.outcomes[1] is StepOutcome.OK
        assert runner.summary.failures == 1

    def test_optional_ack_tolerates_rejection_being_absent(self, backend, clock, simulator):
        """CMD_SET_TIME_SPUTNIKS may be ignored entirely (§9.14)."""
        simulator.silent_for = {SET_TIME_BVS}
        document = _document(_send(SET_TIME_BVS, "s1", ack_policy=AckPolicy.OPTIONAL_ACK))
        runner = ScenarioRunner(backend, document, clock=clock)

        runner.start()
        runner.tick()
        clock.advance(1500)
        runner.tick()

        assert runner.summary.outcomes[0] is StepOutcome.OK


class TestTimeouts:
    def test_a_silent_detector_times_the_step_out(self, backend, clock, simulator):
        simulator.silent_for = {STATUS_REQ}
        document = _document(_send(STATUS_REQ, "s1"))
        runner = ScenarioRunner(backend, document, clock=clock)

        runner.start()
        runner.tick()
        clock.advance(1001)
        runner.tick()

        assert runner.summary.outcomes[0] is StepOutcome.TIMEOUT
        assert runner.state is RunState.FAILED

    def test_a_missing_telemetry_message_times_out(self, backend, clock):
        document = _document(_wait_ts(TM_TELEMETRY, "w1", timeout_ms=800))
        runner = ScenarioRunner(backend, document, clock=clock)

        runner.start()
        runner.tick()
        clock.advance(801)
        runner.tick()

        assert runner.summary.outcomes[0] is StepOutcome.TIMEOUT

    def test_retries_are_attempted_before_giving_up(self, backend, clock, simulator):
        simulator.silent_for = {STATUS_REQ}
        document = _document(
            _send(STATUS_REQ, "s1", retry=RetryPolicy(attempts=3, retry_on_timeout=True))
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
        simulator.silent_for = {STATUS_REQ}
        document = _document(
            _send(STATUS_REQ, "s1", retry=RetryPolicy(attempts=3, retry_on_timeout=True))
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
        document = _document(_send(STATUS_REQ, "s1"))
        runner = ScenarioRunner(backend, document, clock=clock)

        sent, received = [], []
        runner.message_sent.connect(sent.append)
        runner.message_received.connect(received.append)

        _run(runner, clock)

        assert [r.msg_id for r in sent] == [STATUS_REQ]
        assert [r.direction for r in sent] == ["tx"]
        assert TM_ACK in [r.msg_id for r in received]
        assert {r.direction for r in received} == {"rx"}

    def test_host_and_detector_are_distinguishable_sources(self, backend, clock):
        document = _document(_send(STATUS_REQ, "s1"))
        runner = ScenarioRunner(backend, document, clock=clock)

        records = []
        runner.message_sent.connect(records.append)
        runner.message_received.connect(records.append)

        _run(runner, clock)

        assert {r.source for r in records} == {"host", "detector"}

    def test_step_signals_report_progress(self, backend, clock):
        document = _document(_send(STATUS_REQ, "s1"), _wait_ts(TM_STATUS, "w1"))
        runner = ScenarioRunner(backend, document, clock=clock)

        started, finished = [], []
        runner.step_started.connect(started.append)
        runner.step_finished.connect(lambda row, outcome, detail: finished.append((row, outcome)))

        _run(runner, clock)

        assert started == [0, 1]
        assert finished == [(0, "ok"), (1, "ok")]

    def test_run_finished_carries_the_summary(self, backend, clock):
        document = _document(_send(STATUS_REQ, "s1"))
        runner = ScenarioRunner(backend, document, clock=clock)

        summaries = []
        runner.run_finished.connect(summaries.append)

        _run(runner, clock)

        assert len(summaries) == 1
        assert summaries[0].state is RunState.FINISHED
        assert summaries[0].steps_total == 1


class TestControl:
    def test_pause_and_resume(self, backend, clock):
        document = _document(_send(STATUS_REQ, "s1"), _send(STATUS_REQ, "s2"))
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
        document = _document(_send(STATUS_REQ, "s1"), _send(STATUS_REQ, "s2"))
        runner = ScenarioRunner(backend, document, clock=clock)

        runner.start()
        runner.tick()
        runner.stop()

        assert runner.state is RunState.STOPPED

    def test_single_stepping_pauses_after_each_step(self, backend, clock):
        document = _document(_send(STATUS_REQ, "s1"), _send(STATUS_REQ, "s2"))
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
        step = _send(SET_DEST_ID, "s1")
        step.payload["destination_id"] = 0x11
        document = _document(step)
        runner = ScenarioRunner(backend, document, clock=clock)

        _run(runner, clock)

        assert runner.summary.outcomes[0] is StepOutcome.OK
        assert runner.na_address == 0x11


class TestTelemetryCommands:
    def test_a_telemetry_command_needs_no_acknowledgement(self, backend, clock):
        """§2.3: КТ are never acknowledged, so the step must not wait for one."""
        document = _document(_send(TLM_MCILWAIN, "s1", category="KT"))
        runner = ScenarioRunner(backend, document, clock=clock)

        _run(runner, clock)

        assert runner.summary.outcomes[0] is StepOutcome.OK
        assert runner.state is RunState.FINISHED


class TestBoardLogOutput:
    """The МК also prints debug text onto the same bus in some configurations.

    Those frames carry identifiers of the firmware's own choosing. They must be captured — that is
    the point of watching the bus — but they answer nothing, so nothing about a run may depend on
    whether the board happened to be talkative.
    """

    @staticmethod
    def _log_frames(backend, text: bytes, msg_id: int = 0x0123):
        return encode(
            msg_id, text,
            destination=backend.bvs_address,
            source=backend.na_address,
            extended=backend.settings.extended_ids,
        )

    def test_it_is_captured_as_a_log_record(self, backend, clock):
        runner = ScenarioRunner(backend, _document(_wait_ts(TM_STATUS, "w1", timeout_ms=50)), clock=clock)
        received = []
        runner.message_received.connect(received.append)

        runner.start()
        backend.inject(self._log_frames(backend, b"boot\n"))
        runner.tick()

        assert [r.category for r in received] == [LOG_CATEGORY]
        assert received[0].payload == b"boot\n"
        assert received[0].source == "board"
        # Recorded, then dropped: nothing keeps it around to be matched against later.
        assert not runner._inbox

    def test_it_does_not_satisfy_a_wait(self, backend, clock):
        """The failure this prevents: a printf closing a step that never got its telemetry."""
        runner = ScenarioRunner(backend, _document(_wait_ts(TM_STATUS, "w1", timeout_ms=100)), clock=clock)

        runner.start()
        backend.inject(self._log_frames(backend, b"NAND1 ok\n"))
        runner.tick()

        assert runner.state is RunState.RUNNING
        assert runner.summary.outcomes == {}

        clock.advance(200)
        runner.tick()
        assert runner.summary.outcomes[0] is StepOutcome.TIMEOUT

    def test_it_does_not_answer_a_command_either(self, backend, clock, simulator):
        simulator.silent_for = {STATUS_REQ}
        document = _document(_send(STATUS_REQ, "s1", ack_timeout_ms=100))
        runner = ScenarioRunner(backend, document, clock=clock)

        runner.start()
        runner.tick()
        backend.inject(self._log_frames(backend, b"cmd seen\n"))
        runner.tick()

        assert runner.summary.outcomes == {}
        clock.advance(200)
        runner.tick()
        assert runner.summary.outcomes[0] is StepOutcome.TIMEOUT

    def test_chatter_does_not_push_telemetry_out_of_the_inbox(self, backend, clock):
        """Board logs are dropped after being recorded, so the inbox keeps only real messages.

        Telemetry that arrives before its wait step starts is buffered; if log lines were buffered
        too, a talkative МК would evict the answer the next step is about to look for.
        """
        document = _document(_send(STATUS_REQ, "s1"), _wait_ts(TM_STATUS, "w1"))
        runner = ScenarioRunner(backend, document, clock=clock)

        runner.start()
        runner.tick()                                     # sends, the simulator answers at once
        for i in range(80):                               # more than INBOX_LIMIT
            backend.inject(self._log_frames(backend, f"line {i}\n".encode()))
        for _ in range(200):
            if not runner.state.is_active:
                break
            runner.tick()

        assert runner.state is RunState.FINISHED
        assert runner.summary.outcomes == {0: StepOutcome.OK, 1: StepOutcome.OK}

    def test_a_real_telemetry_message_is_still_an_answer(self, backend, clock):
        """The guard rail: classification must not have made everything a log."""
        document = _document(_send(STATUS_REQ, "s1"), _wait_ts(TM_STATUS, "w1"))
        runner = ScenarioRunner(backend, document, clock=clock)

        received = []
        runner.message_received.connect(received.append)
        _run(runner, clock)

        assert runner.summary.outcomes == {0: StepOutcome.OK, 1: StepOutcome.OK}
        assert {r.category for r in received} == {"TS"}


class TestBoardLogFramesDuringARun:
    """`BSP/UART/src/log_backend_can.c` — raw text on one fixed identifier, no UniCAN framing.

    Read as UniCAN, `0x7DB` is a continuation frame from sender `0x1E`, which is the payload's own
    address. During a run that is not merely noise: the bytes land inside whatever long telemetry
    transfer is in flight.
    """

    @staticmethod
    def _log(text: bytes) -> CanFrame:
        return CanFrame(0x7DB, text)

    def test_a_line_is_recorded_as_one_record(self, backend, clock):
        runner = ScenarioRunner(backend, _document(_wait_ts(TM_STATUS, "w", timeout_ms=50)), clock=clock)
        received = []
        runner.message_received.connect(received.append)

        runner.start()
        backend.inject([self._log(b"NAND1 "), self._log(b"ok\r\n")])
        runner.tick()

        assert [r.payload for r in received] == [b"NAND1 ok\r\n"]
        assert received[0].category == LOG_CATEGORY
        assert received[0].frame_count == 2

    def test_it_still_satisfies_nothing(self, backend, clock):
        runner = ScenarioRunner(backend, _document(_wait_ts(TM_STATUS, "w", timeout_ms=100)), clock=clock)

        runner.start()
        backend.inject([self._log(b"ok\r\n")])
        runner.tick()

        assert runner.summary.outcomes == {}
        clock.advance(200)
        runner.tick()
        assert runner.summary.outcomes[0] is StepOutcome.TIMEOUT

    def test_it_does_not_break_the_telemetry_it_interrupts(self, backend, clock):
        """A 109-byte ТС spans a start frame and thirteen data frames; the log lands in the middle."""
        document = _document(_send(STATUS_REQ, "s1"), _wait_ts(TM_TELEMETRY, "w1"))
        runner = ScenarioRunner(backend, document, clock=clock)
        received = []
        runner.message_received.connect(received.append)

        runner.start()
        frames = encode(
            TM_TELEMETRY, bytes(109),
            destination=backend.bvs_address, source=backend.na_address,
        )
        runner.tick()                                   # sends, the simulator acknowledges
        backend.inject([frames[0], self._log(b"tick\r\n"), *frames[1:]])
        for _ in range(50):
            if not runner.state.is_active:
                break
            runner.tick()

        assert runner.summary.outcomes == {0: StepOutcome.OK, 1: StepOutcome.OK}
        assert all(r.valid for r in received)
        assert b"tick\r\n" in [r.payload for r in received]

    def test_the_identifier_comes_from_the_connection(self, clock):
        from detector_scenario_tool.transport.backend import ConnectionSettings

        other = VirtualBackend(ConnectionSettings(backend="virtual", board_log_id=0x321))
        other.open()
        runner = ScenarioRunner(other, _document(_wait_ts(TM_STATUS, "w", timeout_ms=50)), clock=clock)
        received = []
        runner.message_received.connect(received.append)

        runner.start()
        other.inject([CanFrame(0x321, b"hi\r\n")])
        runner.tick()

        assert [r.payload for r in received] == [b"hi\r\n"]
