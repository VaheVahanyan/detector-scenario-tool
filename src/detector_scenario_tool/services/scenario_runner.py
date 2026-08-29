"""Executes a scenario against a live (or simulated) CAN bus.

Stepping is explicit: `tick()` does one slice of work and returns. The UI drives it from a QTimer,
tests drive it directly with a fake clock, and neither needs the other. Nothing here sleeps.

Every frame sent and every message received is emitted as a `LogRecord`, so the existing log panel,
row-status colouring and timeline highlighting light up during a run with no changes of their own.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

from PySide6.QtCore import QObject, Signal

from detector_scenario_tool.domain.log_roles import HOST_SOURCE
from detector_scenario_tool.domain.logs import LOG_CATEGORY, LogRecord
from detector_scenario_tool.domain.scenario import (
    AckPolicy,
    CommentStep,
    ScenarioDocument,
    SendMessageStep,
    WaitForTsStep,
    WaitTimeStep,
)
from detector_scenario_tool.protocol import registry, well_known
from detector_scenario_tool.protocol.errors import AckErrorCode, decode_ack_status
from detector_scenario_tool.protocol.fields import PackingError, pack_message, unpack_message
from detector_scenario_tool.services.bus_monitor import (
    BoardLogAssembler,
    record_for_message,
    record_for_problem,
)
from detector_scenario_tool.transport.backend import CanBackend
from detector_scenario_tool.transport.unican import (
    Reassembler,
    UniCanDecodeError,
    UniCanErrorFrame,
    UniCanMessage,
    encode,
)
from detector_scenario_tool.transport_defaults import DEFAULT_BVS_ADDRESS, DEFAULT_NA_ADDRESS

#: How many unclaimed messages to keep for a later wait step.
INBOX_LIMIT = 64


class RunState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    FINISHED = "finished"
    STOPPED = "stopped"
    FAILED = "failed"

    @property
    def is_active(self) -> bool:
        return self in (RunState.RUNNING, RunState.PAUSED)


class StepOutcome(str, Enum):
    OK = "ok"
    TIMEOUT = "timeout"
    REJECTED = "rejected"
    ERROR = "error"
    SKIPPED = "skipped"


@dataclass
class RunSummary:
    state: RunState = RunState.IDLE
    steps_total: int = 0
    steps_done: int = 0
    outcomes: dict[int, StepOutcome] = field(default_factory=dict)
    failed_step: int | None = None
    detail: str = ""

    @property
    def failures(self) -> int:
        return sum(1 for o in self.outcomes.values() if o not in (StepOutcome.OK, StepOutcome.SKIPPED))


@dataclass
class _CyclicTask:
    """A send that keeps repeating alongside the linear scenario."""

    row: int
    category: str
    msg_id: int
    payload: bytes
    period_ms: int
    next_due_ms: float
    sends: int = 1
    max_repeats: int | None = None

    @property
    def exhausted(self) -> bool:
        return self.max_repeats is not None and self.sends >= self.max_repeats


@dataclass
class _Pending:
    """What the runner is currently waiting for."""

    kind: str                       # "ack" | "ts" | "time"
    deadline_ms: float
    created_ms: float = 0.0
    msg_id: int | None = None
    sent_msg_id: int | None = None
    require_ack_ok: bool = False
    attempts_left: int = 1
    retry_delay_until_ms: float = 0.0


class ScenarioRunner(QObject):
    step_started = Signal(int)
    step_finished = Signal(int, str, str)          # row, StepOutcome value, detail
    message_received = Signal(object)              # LogRecord
    message_sent = Signal(object)                  # LogRecord
    bus_error = Signal(object)                     # UniCanErrorFrame | UniCanDecodeError
    state_changed = Signal(str)
    run_finished = Signal(object)                  # RunSummary

    def __init__(
            self,
            backend: CanBackend,
            document: ScenarioDocument,
            clock: Callable[[], float] | None = None,
            na_address: int = DEFAULT_NA_ADDRESS,
            bvs_address: int = DEFAULT_BVS_ADDRESS,
            stop_on_failure: bool = True,
            send_telemetry_commands: bool = True,
            parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.backend = backend
        self.document = document
        self._clock = clock or (lambda: time.monotonic() * 1000.0)
        self.na_address = na_address
        self.bvs_address = bvs_address
        self.stop_on_failure = stop_on_failure
        #: Master switch for КТ. Off means every telemetry-command step is skipped, one-shot and
        #: cyclic alike, so a scenario can be exercised without the БВС data pushes.
        self.send_telemetry_commands = send_telemetry_commands

        self.state = RunState.IDLE
        self.summary = RunSummary()
        self._cursor = 0
        self._pending: _Pending | None = None
        self._single_step = False
        self._reassembler = Reassembler(extended=backend.settings.extended_ids)
        # The controller's debug log shares the bus but not the framing, and must never reach the
        # reassembler — see `BoardLogAssembler`.
        self._board_log = BoardLogAssembler(backend.settings.board_log_id, clock=self._clock)
        # Telemetry can arrive faster than the runner advances — the acknowledgement and the
        # status that follows it come back-to-back — so messages nothing is waiting for yet are
        # held here until the step that wants them starts.
        self._inbox: deque[tuple[float, UniCanMessage]] = deque(maxlen=INBOX_LIMIT)
        self._cyclic: list[_CyclicTask] = []
        self._last_frame_id: int | None = None

    # -- control -----------------------------------------------------------------------

    def start(self) -> None:
        self._cursor = 0
        self._pending = None
        self._inbox.clear()
        self._cyclic.clear()
        self._reassembler.reset()
        self._board_log.reset()
        self.summary = RunSummary(steps_total=len(self.document.steps))
        self._set_state(RunState.RUNNING)

    def pause(self) -> None:
        if self.state is RunState.RUNNING:
            self._set_state(RunState.PAUSED)

    def resume(self) -> None:
        if self.state is RunState.PAUSED:
            self._single_step = False
            self._set_state(RunState.RUNNING)
            # Anything that arrived during the pause was buffered rather than matched.
            self._satisfy_from_inbox()

    def stop(self) -> None:
        if self.state.is_active:
            self._finish(RunState.STOPPED)

    def step_once(self) -> None:
        """Run exactly one scenario step, then pause again."""
        if self.state is RunState.IDLE:
            self.start()
        self._single_step = True
        self._set_state(RunState.RUNNING)

    # -- the loop ----------------------------------------------------------------------

    def tick(self) -> None:
        """One slice of work: read the bus, service repeats, then advance if possible."""
        self._read_bus()

        if self.state is not RunState.RUNNING:
            return

        self._service_cyclic()

        if self._pending is not None:
            self._check_pending()
            return

        self._begin_next_step()

    # -- cyclic sends ------------------------------------------------------------------

    @property
    def cyclic_tasks(self) -> list[_CyclicTask]:
        return list(self._cyclic)

    def _service_cyclic(self) -> None:
        """Repeats run alongside the scenario and stop only when the run does (decision B5)."""
        now = self._now()
        for task in self._cyclic:
            if task.exhausted or now < task.next_due_ms:
                continue
            self._transmit(task.category, task.msg_id, task.payload)
            task.sends += 1
            task.next_due_ms = now + task.period_ms

    def _register_cyclic(self, step: SendMessageStep, payload: bytes) -> None:
        policy = step.cyclic
        if policy is None or not policy.enabled or policy.max_repeats == 1:
            return

        self._cyclic.append(
            _CyclicTask(
                row=self._cursor,
                category=step.message.category,
                msg_id=step.message.msg_id,
                payload=payload,
                period_ms=policy.period_ms,
                next_due_ms=self._now() + policy.period_ms,
                max_repeats=policy.max_repeats,
            )
        )

    def _begin_next_step(self) -> None:
        while self._cursor < len(self.document.steps):
            step = self.document.steps[self._cursor]

            if not getattr(step, "enabled", True) or isinstance(step, CommentStep):
                self._complete_step(StepOutcome.SKIPPED, "")
                continue

            self.step_started.emit(self._cursor)

            if isinstance(step, SendMessageStep):
                self._execute_send(step)
            elif isinstance(step, WaitForTsStep):
                self._execute_wait_ts(step)
            elif isinstance(step, WaitTimeStep):
                self._pending = _Pending("time", self._now() + max(0, step.delay_ms))
            else:
                self._complete_step(StepOutcome.SKIPPED, "")
                continue
            return

        self._finish(RunState.FINISHED)

    # -- step kinds --------------------------------------------------------------------

    def _execute_send(self, step: SendMessageStep) -> None:
        if step.message is not None and step.message.category == "KT" and not self.send_telemetry_commands:
            self._complete_step(StepOutcome.SKIPPED, "telemetry commands disabled")
            return

        try:
            payload = self._pack(step)
        except (PackingError, ValueError) as exc:
            self._complete_step(StepOutcome.ERROR, str(exc))
            return

        msg_id = step.message.msg_id
        self._transmit(step.message.category, msg_id, payload)
        self._register_cyclic(step, payload)

        if step.ack_policy is AckPolicy.NONE:
            self._complete_step(StepOutcome.OK, "")
            return

        timeout = step.ack_timeout_ms if step.ack_timeout_ms is not None else 1000
        self._pending = _Pending(
            kind="ack",
            deadline_ms=self._now() + timeout,
            created_ms=self._now(),
            msg_id=well_known.msg_id(well_known.ACK),
            sent_msg_id=msg_id,
            require_ack_ok=step.ack_policy is AckPolicy.EXPECT_ACK,
            attempts_left=max(1, step.retry.attempts) - 1,
        )

    def _execute_wait_ts(self, step: WaitForTsStep) -> None:
        if step.expected is None or step.expected.msg_id is None:
            self._complete_step(StepOutcome.ERROR, "no telemetry message selected")
            return

        self._pending = _Pending(
            kind="ts",
            deadline_ms=self._now() + max(0, step.timeout_ms),
            created_ms=self._now(),
            msg_id=step.expected.msg_id,
            require_ack_ok=step.require_ack_ok,
            sent_msg_id=step.ack_for_msg_id or self._previous_sent_msg_id(),
        )
        self._satisfy_from_inbox()

    def _satisfy_from_inbox(self) -> None:
        """Let the current step claim a message that arrived before it could be handled.

        A wait-for-message step accepts anything buffered — the telemetry it wants is usually
        produced by the command just before it. An acknowledgement wait only accepts messages that
        arrived *after* its command went out, so a stale acknowledgement cannot satisfy it.
        """
        pending = self._pending
        if pending is None or pending.kind not in ("ack", "ts"):
            return

        for _ in range(len(self._inbox)):
            received_ms, message = self._inbox.popleft()
            if pending.kind == "ack" and received_ms < pending.created_ms:
                continue
            if self._try_satisfy(message):
                return

    def _pack(self, step: SendMessageStep) -> bytes:
        if step.message is None or step.message.msg_id is None:
            raise ValueError("no message selected")

        spec = registry.find(step.message.category, step.message.msg_id)
        if spec is None:
            raise ValueError(f"unknown message 0x{step.message.msg_id:04X}")
        return pack_message(spec, step.payload)

    def _transmit(self, category: str, msg_id: int, payload: bytes) -> None:
        # A user-defined message may deliberately target other addresses, to test how the payload
        # reacts to traffic that is not addressed to it.
        spec = registry.find(category, msg_id)
        destination = self.na_address
        source = self.bvs_address
        if spec is not None:
            destination = spec.destination_override if spec.destination_override is not None else destination
            source = spec.source_override if spec.source_override is not None else source

        frames = encode(
            msg_id,
            payload,
            destination=destination,
            source=source,
            extended=self.backend.settings.extended_ids,
        )
        for frame in frames:
            self.backend.send(frame)

        record = LogRecord(
            timestamp_ms=int(self._now()),
            direction="tx",
            category=category,
            msg_id=msg_id,
            payload=payload,
            source=HOST_SOURCE,
            can_id=frames[0].can_id if frames else None,
            frame_count=len(frames),
        )
        self.message_sent.emit(record)

    # -- bus ---------------------------------------------------------------------------

    def _read_bus(self) -> None:
        if not self.backend.is_open:
            return

        for frame in self.backend.drain():
            if self._board_log.owns(frame):
                self._emit_board_log(self._board_log.feed(frame))
                continue

            self._last_frame_id = frame.can_id
            decoded = self._reassembler.feed(frame)

            if isinstance(decoded, UniCanMessage):
                self._on_message(decoded)
            elif isinstance(decoded, (UniCanErrorFrame, UniCanDecodeError)):
                self._on_bus_problem(decoded, frame)

        self._emit_board_log(self._board_log.flush())

    def _emit_board_log(self, records) -> None:
        """Log lines are recorded and go no further: they answer nothing and satisfy no step."""
        for record in records:
            self.message_received.emit(record)

    def _on_bus_problem(self, problem, frame) -> None:
        """Surface a framing failure as a log row too, not only as a status line."""
        self.bus_error.emit(problem)
        self.message_received.emit(record_for_problem(problem, frame, int(self._now())))

    def _on_message(self, message: UniCanMessage) -> None:
        record = record_for_message(message, int(self._now()), can_id=self._last_frame_id)
        self.message_received.emit(record)

        if record.category == LOG_CATEGORY:
            # The board's own debug output, not an answer. It is worth showing — hence the record
            # above — but it must not satisfy the current step, and it must not sit in the inbox
            # either: a run where the МК chatters would otherwise push real telemetry out of it.
            return

        # Paused means "stop advancing", not "stop listening": the log stays live and anything
        # that arrives is kept for whenever the run resumes.
        if self.state is RunState.RUNNING and self._pending is not None:
            if self._pending.kind in ("ack", "ts") and self._try_satisfy(message):
                return

        self._inbox.append((self._now(), message))

    def _try_satisfy(self, message: UniCanMessage) -> bool:
        """Returns True when the message completed the current step."""
        pending = self._pending
        if pending is None or message.msg_id != pending.msg_id:
            return False

        if well_known.is_ack("TS", message.msg_id):
            acknowledged, rejected, code = self._decode_ack(message.payload)

            if pending.sent_msg_id is not None and acknowledged != pending.sent_msg_id:
                # An acknowledgement for a different command; keep waiting for ours.
                return False

            if rejected and pending.require_ack_ok:
                name = code.name if code is not None else "unknown"
                self._complete_step(StepOutcome.REJECTED, f"rejected: {name}")
                return True

            self._apply_address_change(pending.sent_msg_id)

        self._complete_step(StepOutcome.OK, "")
        return True

    @staticmethod
    def _decode_ack(payload: bytes) -> tuple[int | None, bool, AckErrorCode | None]:
        spec = well_known.definition(well_known.ACK)
        values = unpack_message(spec, payload)
        acknowledged = values.get("acknowledged_msg_id")
        status_byte = (values.get("rejected", 0) & 1) | ((values.get("error_code", 0) & 0x7F) << 1)
        rejected, code = decode_ack_status(status_byte)
        return acknowledged, rejected, code

    def _apply_address_change(self, msg_id: int | None) -> None:
        """CMD_SET_DEST_ID / CMD_SET_DEVICE_ID move the bus addresses under us."""
        which = well_known.is_address_command("KU", msg_id)
        if which is None:
            return

        step = self._current_step()
        if not isinstance(step, SendMessageStep):
            return

        if which == well_known.SET_DEST_ID:
            new = step.payload.get("destination_id")
            if isinstance(new, int):
                self.na_address = new
        else:
            new = step.payload.get("device_id")
            if isinstance(new, int):
                self.na_address = new

    # -- pending -----------------------------------------------------------------------

    def _check_pending(self) -> None:
        pending = self._pending
        if pending is None:
            return

        now = self._now()

        if pending.retry_delay_until_ms and now < pending.retry_delay_until_ms:
            return

        if now < pending.deadline_ms:
            return

        if pending.kind == "time":
            self._complete_step(StepOutcome.OK, "")
            return

        step = self._current_step()
        if (
                pending.kind == "ack"
                and pending.attempts_left > 0
                and isinstance(step, SendMessageStep)
                and step.retry.retry_on_timeout
        ):
            self._retry_send(step, pending)
            return

        if pending.kind == "ack" and isinstance(step, SendMessageStep):
            if step.ack_policy is AckPolicy.OPTIONAL_ACK:
                # §9.14: CMD_SET_TIME_SPUTNIKS may be ignored on purpose, so silence is allowed.
                self._complete_step(StepOutcome.OK, "no acknowledgement (optional)")
                return

        self._complete_step(StepOutcome.TIMEOUT, f"no reply within {int(pending.deadline_ms - 0)} ms")

    def _retry_send(self, step: SendMessageStep, pending: _Pending) -> None:
        try:
            payload = self._pack(step)
        except (PackingError, ValueError) as exc:
            self._complete_step(StepOutcome.ERROR, str(exc))
            return

        self._transmit(step.message.category, step.message.msg_id, payload)

        timeout = step.ack_timeout_ms if step.ack_timeout_ms is not None else 1000
        now = self._now()
        pending.attempts_left -= 1
        pending.retry_delay_until_ms = now + step.retry.retry_delay_ms
        pending.deadline_ms = now + step.retry.retry_delay_ms + timeout

    # -- bookkeeping -------------------------------------------------------------------

    def _complete_step(self, outcome: StepOutcome, detail: str) -> None:
        row = self._cursor
        self._pending = None
        self.summary.outcomes[row] = outcome
        self.summary.steps_done += 1
        self._cursor += 1

        self.step_finished.emit(row, outcome.value, detail)

        failed = outcome not in (StepOutcome.OK, StepOutcome.SKIPPED)
        if failed and self.summary.failed_step is None:
            self.summary.failed_step = row
            self.summary.detail = detail

        if failed and self.stop_on_failure:
            self._finish(RunState.FAILED)
            return

        if self._single_step:
            self._single_step = False
            self._set_state(RunState.PAUSED)

    def _finish(self, state: RunState) -> None:
        self._pending = None
        self.summary.state = state
        self._set_state(state)
        self.run_finished.emit(self.summary)

    def _set_state(self, state: RunState) -> None:
        if self.state is state:
            return
        self.state = state
        self.summary.state = state
        self.state_changed.emit(state.value)

    def _current_step(self):
        if 0 <= self._cursor < len(self.document.steps):
            return self.document.steps[self._cursor]
        return None

    def _previous_sent_msg_id(self) -> int | None:
        for index in range(self._cursor - 1, -1, -1):
            step = self.document.steps[index]
            if isinstance(step, SendMessageStep) and step.message is not None:
                return step.message.msg_id
        return None

    def _now(self) -> float:
        return self._clock()
