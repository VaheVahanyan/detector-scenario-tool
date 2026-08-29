"""Reading the CAN bus when no run owns it, and building the log record for a received frame.

Three things live here, and they belong together:

* `record_for_message` / `record_for_problem` — the single definition of what an incoming frame
  looks like in the log. `ScenarioRunner` uses them too, so a message logged during a run and the
  same message logged while merely connected cannot drift apart (the board-log classification in
  particular has to apply to both).
* `BoardLogAssembler` — the controller's debug output, which is **not UniCAN**. See its docstring:
  those frames have to leave the stream before reassembly, or they corrupt telemetry.
* `BusMonitor` — a reassembler plus a poll loop, for the stretches when no `ScenarioRunner` is
  reading the bus. Until this existed, being connected did nothing on its own: the poll timer only
  ran during a run, so anything the board said before, between or after runs — its debug output
  included — was never read at all.

No Qt here: `services/run_controller.py` owns the timer and the signals.
"""

from __future__ import annotations

import time
from typing import Callable

from detector_scenario_tool.domain.log_roles import BOARD_SOURCE, DETECTOR_SOURCE
from detector_scenario_tool.domain.logs import LOG_CATEGORY, LogRecord
from detector_scenario_tool.protocol import legacy_v2
from detector_scenario_tool.protocol.log_decode import incoming_category
from detector_scenario_tool.transport.backend import CanBackend
from detector_scenario_tool.transport_defaults import DEFAULT_BOARD_LOG_ID
from detector_scenario_tool.transport.unican import (
    CanFrame,
    Reassembler,
    UniCanDecodeError,
    UniCanErrorFrame,
    UniCanMessage,
)


def record_for_message(
        message: UniCanMessage,
        timestamp_ms: int,
        can_id: int | None = None,
) -> LogRecord:
    """A reassembled message as a log row.

    The category decides the source too: telemetry comes from the payload, everything else is the
    controller talking on its own behalf.
    """
    category = incoming_category(message.msg_id)

    # A number the specification has since moved is still the payload answering, just a revision
    # behind — so it is not v2.1 telemetry (the category stays `LOG`), but it is not printf either.
    from_payload = category != LOG_CATEGORY or legacy_v2.recognise(message.msg_id) is not None

    return LogRecord(
        timestamp_ms=timestamp_ms,
        direction="rx",
        category=category,
        msg_id=message.msg_id,
        payload=message.payload,
        source=DETECTOR_SOURCE if from_payload else BOARD_SOURCE,
        can_id=can_id,
    )


def record_for_problem(problem, frame: CanFrame, timestamp_ms: int) -> LogRecord:
    """A frame that could not be reassembled, or an error frame the bus reported.

    Surfaced as a row rather than only as a status line: a frame that failed reassembly is exactly
    what the raw view exists to show, and letting it vanish is how a protocol bug stays invisible.
    """
    return LogRecord(
        timestamp_ms=timestamp_ms,
        direction="rx",
        category="TS",
        msg_id=getattr(problem, "failed_msg_id", None) or getattr(problem, "msg_id", 0) or 0,
        payload=bytes(frame.data),
        source=DETECTOR_SOURCE,
        note=getattr(problem, "detail", "") or str(getattr(problem, "code", "")),
        can_id=frame.can_id,
        valid=False,
    )


class BoardLogAssembler:
    """The controller's debug log: raw text on one fixed CAN identifier.

    `BSP/UART/src/log_backend_can.c` sends a log line as a run of frames that carry **no UniCAN
    framing at all** — the identifier is the constant `LOG_BACKEND_CAN_DEBUG_ID` (`0x7DB`) rather
    than a sender/receiver pair, and the data bytes are the text itself, with no MSG_ID in front.

    Taking such a frame out of the stream is not cosmetic. Read as a UniCAN identifier, `0x7DB` is
    ``data bit = 1, sender = 0x1E, receiver = 0x1B``: a *continuation frame of a long message from
    address 0x1E* — and 0x1E is the payload's own address. On its own the reassembler answers
    `DATA_WITHOUT_START` and the line is logged as a broken frame; arriving during a long telemetry
    transfer, its bytes are appended into that transfer and destroy it. So the identifier is
    matched **before** reassembly, and the frames never reach it.

    Lines are put back together here because the firmware does tell us where they end: `debug_log.c`
    writes `\r\n` for every newline. Frames are 8 bytes and a line is cut at 32-byte boundaries
    first, so frame boundaries mean nothing at all — one record per line is both the useful unit and
    the one this side can actually identify. A run of frames becomes one record with `frame_count`
    set, exactly as a long UniCAN message already does.
    """

    #: Nothing arrived for this long: whatever is buffered was the end of a line after all. The
    #: firmware paces frames 1 ms apart, and `debug_log_write_u32_inline` can leave a line hanging
    #: with no newline at all, so an unterminated tail has to come out eventually.
    LINE_TIMEOUT_MS = 250

    #: A firmware printing without newlines must not accumulate for ever.
    MAX_LINE_BYTES = 512

    def __init__(
            self,
            identifier: int = DEFAULT_BOARD_LOG_ID,
            clock: Callable[[], float] | None = None,
    ) -> None:
        self.identifier = identifier
        self._clock = clock or (lambda: time.monotonic() * 1000.0)
        self._buffer = bytearray()
        self._frames = 0
        self._started_ms = 0
        self._last_ms = 0.0

    def owns(self, frame: CanFrame) -> bool:
        """Whether this frame is board log output rather than anything the protocol describes."""
        return not frame.extended and frame.can_id == self.identifier

    def reset(self) -> None:
        self._buffer.clear()
        self._frames = 0

    def feed(self, frame: CanFrame) -> list[LogRecord]:
        now = self._clock()
        if not self._buffer:
            # The line is timestamped when its first byte arrived, not when it ended: that is the
            # moment to line up against the scenario.
            self._started_ms = int(now)
        self._last_ms = now

        self._frames += 1
        self._buffer.extend(frame.data)

        records = []
        while True:
            end = self._buffer.find(b"\n")
            if end < 0:
                break
            # Trim first: `_emit` decides whether any frame is still outstanding by looking at
            # what is left, so the line has to be gone by then.
            line = bytes(self._buffer[:end + 1])
            del self._buffer[:end + 1]
            records.append(self._emit(line))
            self._started_ms = int(now)

        if len(self._buffer) >= self.MAX_LINE_BYTES:
            line = bytes(self._buffer)
            self._buffer.clear()
            records.append(self._emit(line))

        return records

    def flush(self, force: bool = False) -> list[LogRecord]:
        """Emit an unterminated tail once the board has clearly stopped talking."""
        if not self._buffer:
            return []
        if not force and (self._clock() - self._last_ms) < self.LINE_TIMEOUT_MS:
            return []

        line = bytes(self._buffer)
        self._buffer.clear()
        return [self._emit(line)]

    def _emit(self, payload: bytes) -> LogRecord:
        record = LogRecord(
            timestamp_ms=self._started_ms,
            direction="rx",
            category=LOG_CATEGORY,
            # There is no MSG_ID in these frames, so the identifier column carries the CAN
            # identifier they arrived on. It is the only number they have.
            msg_id=self.identifier,
            payload=payload,
            source=BOARD_SOURCE,
            can_id=self.identifier,
            frame_count=max(1, self._frames),
        )
        self._frames = 1 if self._buffer else 0
        return record


class BusMonitor:
    """Turns whatever is on the bus into log records. Owns its own reassembler."""

    def __init__(
            self,
            extended: bool = False,
            clock: Callable[[], float] | None = None,
            board_log_id: int = DEFAULT_BOARD_LOG_ID,
    ) -> None:
        self._reassembler = Reassembler(extended=extended)
        self._clock = clock or (lambda: time.monotonic() * 1000.0)
        self.board_log = BoardLogAssembler(board_log_id, clock=self._clock)
        #: Set for the caller that wants to report framing failures as well as log them.
        self.problems: list = []

    def reset(self) -> None:
        self._reassembler.reset()
        self.board_log.reset()
        self.problems.clear()

    def poll(self, backend: CanBackend) -> list[LogRecord]:
        if backend is None or not backend.is_open:
            return []

        records: list[LogRecord] = []
        for frame in backend.drain():
            if self.board_log.owns(frame):
                # Never handed to the reassembler: see `BoardLogAssembler`.
                records.extend(self.board_log.feed(frame))
                continue

            decoded = self._reassembler.feed(frame)
            now = int(self._clock())

            if isinstance(decoded, UniCanMessage):
                records.append(record_for_message(decoded, now, can_id=frame.can_id))
            elif isinstance(decoded, (UniCanErrorFrame, UniCanDecodeError)):
                self.problems.append(decoded)
                records.append(record_for_problem(decoded, frame, now))

        records.extend(self.board_log.flush())
        return records
