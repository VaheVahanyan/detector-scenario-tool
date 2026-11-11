"""Lining a scenario up against a captured log.

This used to live inside `MainWindow` and reasoned strictly in sequence: a step with no matching
record, while *any* other protocol record was still unconsumed, was "the first mismatch" and turned
red. On a real bench that is almost always the case — every command is answered by an
acknowledgement *and* a status, telemetry keeps arriving, a repeated КТ goes out again — so a run
that had in fact received everything was painted red from the second step on, and every answer the
scenario did not spell out as a wait step was painted red in the log as well.

The rules now:

* **A record matches a step by category and identifier**, never by direction. The category already
  says which way a message travels (КУ/КТ to the payload, ТС from it), and the direction a log line
  states depends on who wrote it: the payload's own serial log calls a command it received `rx`.
  Board log output (`LOG`) and frames that failed reassembly never match anything.
* **An acknowledgement only matches the wait step it is for**: the one bound to `ack_for_msg_id`,
  or to the command sent just before — the same rule `ScenarioRunner` applies live.
* **Searching restarts after the last matched command**, not after the last match. The answers to a
  command may arrive in any order (status before acknowledgement), and a late acknowledgement may
  arrive after the next command went out; neither is a failure.
* **A step with no record yet is waiting, not wrong.** It becomes an error only when the scenario
  demonstrably moved past it — a later command is in the log — or when the record that matched it
  says so (an acknowledgement with the rejection bit set).
* **Traffic the scenario did not spell out is not a problem.** An acknowledgement or status that
  answers a sent command, or a repeat of a command already matched, is annotated with the step it
  belongs to; anything else is merely "outside the scenario". Only broken frames, rejections and
  suspicious sources are problems.

No Qt here; `MainWindow` renders the result.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from detector_scenario_tool.domain.log_roles import HOST_SOURCE, normalize_log_source
from detector_scenario_tool.domain.logs import LogRecord
from detector_scenario_tool.domain.scenario import (
    AckPolicy,
    SendMessageStep,
    WaitForTsStep,
    WaitTimeStep,
)
from detector_scenario_tool.i18n import tr
from detector_scenario_tool.protocol import registry, well_known
from detector_scenario_tool.protocol.errors import AckErrorCode
from detector_scenario_tool.protocol.fields import unpack_message
from detector_scenario_tool.utils.labels import category_short

#: Who may legitimately have produced each kind of record.
SEND_SOURCES = frozenset({"board", HOST_SOURCE, ""})
WAIT_SOURCES = frozenset({"detector", ""})


@dataclass
class Correlation:
    row_statuses: dict[int, str] = field(default_factory=dict)
    step_to_log: dict[int, int] = field(default_factory=dict)
    log_to_step: dict[int, int] = field(default_factory=dict)
    step_details: dict[int, str] = field(default_factory=dict)
    log_details: dict[int, str] = field(default_factory=dict)
    current_step_row: int | None = None
    first_mismatch_row: int | None = None
    #: Matched rows whose source looked wrong for the step.
    source_problem_rows: set[int] = field(default_factory=set)
    #: Log rows worth a second look: broken frames, rejections, odd sources.
    problem_rows: set[int] = field(default_factory=set)
    #: Log rows not matched to a step but explained by one: answers and repeats.
    related_rows: dict[int, int] = field(default_factory=dict)

    @property
    def explained_rows(self) -> set[int]:
        return set(self.log_to_step) | set(self.related_rows)

    def as_tuple(self):
        return (
            self.row_statuses,
            self.step_to_log,
            self.log_to_step,
            self.step_details,
            self.log_details,
            self.current_step_row,
            self.first_mismatch_row,
        )


@dataclass(frozen=True)
class _Expectation:
    category: str
    msg_id: int
    #: For an acknowledgement: the command it must acknowledge, if known.
    ack_for: int | None
    is_send: bool


def is_protocol_record(record: LogRecord) -> bool:
    """A record that can take part in matching at all."""
    return record.valid and not record.is_board_log


def decode_ack(record: LogRecord) -> tuple[int | None, bool, int | None]:
    """(acknowledged identifier, rejected, error code) — Nones when the payload does not unpack."""
    spec = well_known.definition(well_known.ACK)
    if spec is None:
        return None, False, None
    try:
        values = unpack_message(spec, record.payload)
    except Exception:
        return None, False, None
    return (
        values.get("acknowledged_msg_id"),
        bool(values.get("rejected", 0)),
        values.get("error_code"),
    )


def _ack_code_name(code: int | None) -> str:
    if code is None:
        return "?"
    try:
        return tr(AckErrorCode(code).label_key)
    except ValueError:
        return str(code)


def _is_ack_record(record: LogRecord) -> bool:
    return well_known.is_ack(record.category, record.msg_id)


def correlate(steps, records: list[LogRecord], live: bool = False) -> Correlation:
    result = Correlation()

    if not records:
        if live:
            first = next(
                (row for row, step in enumerate(steps) if _is_actionable(step)), None
            )
            if first is not None:
                result.row_statuses[first] = "current"
                result.current_step_row = first
                result.step_details[first] = tr("execution.current_first_live", step=first + 1)
                _mark_pending(steps, result, first + 1)
        return result

    used: set[int] = set()
    expectations: dict[int, _Expectation] = {}
    #: For each wait step, the send step it follows (None at the start of the scenario).
    owner: dict[int, int | None] = {}
    previous_send_row: int | None = None
    previous_send_id: int | None = None

    for row, step in enumerate(steps):
        if not _is_actionable(step):
            if isinstance(step, WaitTimeStep):
                result.step_details[row] = tr("execution.wait_not_matched", step=row + 1)
            continue

        expectation = _expectation_for(step, previous_send_id)
        if isinstance(step, SendMessageStep):
            previous_send_id = step.message.msg_id if step.message is not None else None
        if expectation is None:
            result.step_details[row] = (
                tr("execution.no_message_selected")
                if isinstance(step, SendMessageStep)
                else tr("execution.no_expected_ts", category=category_short("TS"))
            )
            continue

        expectations[row] = expectation
        if expectation.is_send:
            previous_send_row = row
        else:
            owner[row] = previous_send_row

    # Commands first, in order: they are what the scenario's progress is measured by. A command
    # missing from the log does not stop the search, so a later one can still show that the
    # scenario moved on without it.
    anchor = 0
    for row, expectation in expectations.items():
        if not expectation.is_send:
            continue
        match = _find(records, used, anchor, expectation)
        if match is not None:
            used.add(match)
            result.step_to_log[row] = match
            anchor = match + 1

    # Then each wait, in the window after its own command — answers may arrive in any order and
    # even after the next command went out. A wait whose command never went out has no window.
    for row, expectation in expectations.items():
        if expectation.is_send:
            continue
        send_row = owner[row]
        if send_row is not None and send_row not in result.step_to_log:
            continue
        start = 0 if send_row is None else result.step_to_log[send_row] + 1
        match = _find(records, used, start, expectation)
        if match is not None:
            used.add(match)
            result.step_to_log[row] = match

    result.step_to_log = dict(sorted(result.step_to_log.items()))
    result.log_to_step = {log_row: row for row, log_row in result.step_to_log.items()}

    for row, match in result.step_to_log.items():
        _judge_match(result, steps[row], row, records, match, expectations[row])

    # A step with no record is waiting — unless a later command is in the log, which proves the
    # scenario got past it without it.
    matched_sends = [row for row in result.step_to_log if expectations[row].is_send]
    last_matched_send = max(matched_sends, default=-1)
    waiting = [row for row in expectations if row not in result.step_to_log]

    for row in waiting:
        if row < last_matched_send:
            _mark_missing(result, row, expectations[row])

    still_waiting = [row for row in waiting if row > last_matched_send]
    if still_waiting:
        first_row = still_waiting[0]
        first = expectations[first_row]
        result.row_statuses[first_row] = "current"
        result.current_step_row = first_row
        key = "execution.current_waiting_send" if first.is_send else "execution.current_waiting_ts"
        result.step_details[first_row] = tr(
            key,
            step=first_row + 1,
            direction=tr("log.direction.tx" if first.is_send else "log.direction.rx"),
            category=category_short(first.category),
            msg_id=first.msg_id,
        )
        for row in still_waiting[1:]:
            result.row_statuses[row] = "pending"
            result.step_details[row] = tr("execution.pending_not_reached", step=row + 1)

    _annotate_records(steps, records, result)
    return result


# --------------------------------------------------------------------------------------
# Steps
# --------------------------------------------------------------------------------------

def _is_actionable(step) -> bool:
    return isinstance(step, (SendMessageStep, WaitForTsStep)) and getattr(step, "enabled", True)


def _expectation_for(step, previous_send: int | None) -> _Expectation | None:
    if isinstance(step, SendMessageStep):
        if step.message is None or step.message.msg_id is None:
            return None
        return _Expectation(step.message.category, step.message.msg_id, None, True)

    if step.expected is None or step.expected.msg_id is None:
        return None
    ack_for = None
    if well_known.is_ack(step.expected.category, step.expected.msg_id):
        ack_for = step.ack_for_msg_id if step.ack_for_msg_id is not None else previous_send
    return _Expectation(step.expected.category, step.expected.msg_id, ack_for, False)


def _find(records, used, start, expectation: _Expectation) -> int | None:
    for index in range(start, len(records)):
        if index in used:
            continue
        record = records[index]
        if not is_protocol_record(record):
            continue
        if record.category != expectation.category or record.msg_id != expectation.msg_id:
            continue
        if expectation.ack_for is not None and _is_ack_record(record):
            acknowledged, _, _ = decode_ack(record)
            if acknowledged is not None and acknowledged != expectation.ack_for:
                continue
        return index
    return None


def _mark_pending(steps, result: Correlation, start_row: int) -> None:
    for row in range(start_row, len(steps)):
        step = steps[row]
        if not _is_actionable(step):
            if isinstance(step, WaitTimeStep):
                result.step_details.setdefault(
                    row, tr("execution.wait_not_matched", step=row + 1)
                )
            continue
        if row not in result.row_statuses:
            result.row_statuses[row] = "pending"
            result.step_details[row] = tr("execution.pending_not_reached", step=row + 1)


def _mark_missing(result: Correlation, row: int, expectation: _Expectation) -> None:
    result.row_statuses[row] = "error"
    result.step_details[row] = tr(
        "execution.step_missing",
        step=row + 1,
        category=category_short(expectation.category),
        msg_id=expectation.msg_id,
    )
    if result.first_mismatch_row is None or row < result.first_mismatch_row:
        result.first_mismatch_row = row


def _expected_sources(record: LogRecord, is_send: bool) -> frozenset[str]:
    if is_send:
        # The payload's own log of a command it received is as good as our record of sending it.
        if record.direction == "rx":
            return SEND_SOURCES | {"detector"}
        return SEND_SOURCES
    return WAIT_SOURCES


def _judge_match(result: Correlation, step, row: int, records, match: int, expectation) -> None:
    record = records[match]
    source = normalize_log_source(record.source)
    expected = _expected_sources(record, expectation.is_send)
    category = category_short(record.category)

    if source not in expected:
        result.row_statuses[row] = "warning"
        result.source_problem_rows.add(match)
        result.step_details[row] = tr(
            "execution.source_unusual_step",
            step=row + 1,
            log_row=match + 1,
            source=source or tr("log.source.empty"),
            expected=sorted(expected),
        )
        result.log_details[match] = tr("execution.source_unusual_log", step=row + 1)
        return

    result.row_statuses[row] = "ok"
    common = dict(
        step=row + 1,
        log_row=match + 1,
        direction=tr(f"log.direction.{record.direction}"),
        category=category,
        msg_id=record.msg_id,
        source=source or tr("log.source.empty"),
        time=record.timestamp_ms,
    )
    if expectation.is_send:
        result.step_details[row] = tr("execution.matched_send", **common)
        result.log_details[match] = tr(
            "execution.matched_to_step", step=row + 1, category=category, msg_id=record.msg_id
        )
        if step.ack_policy is AckPolicy.EXPECT_ACK:
            _check_send_was_accepted(result, row, records, match, expectation.msg_id)
        return

    result.step_details[row] = tr("execution.matched_wait_ts", **common)
    result.log_details[match] = tr(
        "execution.matched_to_wait_ts", step=row + 1, category=category, msg_id=record.msg_id
    )
    if step.require_ack_ok and _is_ack_record(record):
        _, rejected, code = decode_ack(record)
        if rejected:
            _mark_rejected(result, row, match, code)


def _check_send_was_accepted(result: Correlation, row: int, records, sent: int, msg_id: int) -> None:
    """A command the payload refused is a failure, whether or not a wait step spells it out."""
    for index in range(sent + 1, len(records)):
        record = records[index]
        if not is_protocol_record(record):
            continue
        if record.category in ("KU", "KT") and record.msg_id == msg_id:
            return  # sent again before any answer: the retry's answer is the one that counts
        if not _is_ack_record(record):
            continue
        acknowledged, rejected, code = decode_ack(record)
        if acknowledged != msg_id:
            continue
        if rejected:
            _mark_rejected(result, row, index, code)
        return


def _mark_rejected(result: Correlation, row: int, log_row: int, code: int | None) -> None:
    result.row_statuses[row] = "error"
    result.step_details[row] = tr(
        "execution.ack_rejected_step", step=row + 1, log_row=log_row + 1, code=_ack_code_name(code)
    )
    result.problem_rows.add(log_row)
    if result.first_mismatch_row is None or row < result.first_mismatch_row:
        result.first_mismatch_row = row


# --------------------------------------------------------------------------------------
# Records the scenario did not consume
# --------------------------------------------------------------------------------------

def _annotate_records(steps, records: list[LogRecord], result: Correlation) -> None:
    #: The most recent command matched so far, by log position: (step row, category, msg id).
    sends_by_log = sorted(
        (log_row, step_row)
        for step_row, log_row in result.step_to_log.items()
        if isinstance(steps[step_row], SendMessageStep)
    )

    for index, record in enumerate(records):
        if not record.valid:
            result.problem_rows.add(index)
            continue

        if record.is_board_log:
            result.log_details.setdefault(index, _board_log_detail(index, record))
            continue

        if index in result.log_to_step:
            continue

        earlier = [step_row for log_row, step_row in sends_by_log if log_row < index]
        related = _related_step(steps, record, earlier)

        if related is not None:
            step_row, detail = related
            result.related_rows[index] = step_row
            result.log_details.setdefault(index, detail)
            continue

        result.log_details.setdefault(
            index,
            tr(
                "execution.unmatched_log",
                log_row=index + 1,
                direction=tr(f"log.direction.{record.direction}"),
                category=category_short(record.category),
                msg_id=record.msg_id,
                source=normalize_log_source(record.source) or tr("log.source.empty"),
                time=record.timestamp_ms,
            ),
        )

    result.problem_rows |= result.source_problem_rows


def _related_step(steps, record: LogRecord, earlier_sends: list[int]):
    """The step an unconsumed record belongs to, with the sentence that says so."""
    category = category_short(record.category)

    if record.category in ("KU", "KT"):
        for step_row in reversed(earlier_sends):
            message = steps[step_row].message
            if message.category == record.category and message.msg_id == record.msg_id:
                return step_row, tr(
                    "execution.repeat_of_step",
                    step=step_row + 1,
                    category=category,
                    msg_id=record.msg_id,
                )
        return None

    if _is_ack_record(record):
        acknowledged, rejected, code = decode_ack(record)
        for step_row in reversed(earlier_sends):
            if steps[step_row].message.msg_id == acknowledged:
                verdict = (
                    tr("execution.ack_verdict_rejected", code=_ack_code_name(code))
                    if rejected
                    else tr("execution.ack_verdict_accepted")
                )
                return step_row, tr(
                    "execution.response_to_step", step=step_row + 1, verdict=verdict
                )
        return None

    # Any other answer: the follow-ups the specification lists for the most recent command.
    for step_row in reversed(earlier_sends):
        message = steps[step_row].message
        spec = registry.find(message.category, message.msg_id)
        follow_ups = {(r.category, r.msg_id) for r in (spec.follow_up if spec else ())}
        if (record.category, record.msg_id) in follow_ups:
            return step_row, tr(
                "execution.follow_up_of_step",
                step=step_row + 1,
                category=category,
                msg_id=record.msg_id,
            )
        break  # only the latest command's answers are attributed to it
    return None


def _board_log_detail(index: int, record: LogRecord) -> str:
    if record.can_id is None and record.msg_id == 0:
        return tr("execution.board_log_text", log_row=index + 1, time=record.timestamp_ms)
    return tr(
        "execution.board_log", log_row=index + 1, msg_id=record.msg_id, time=record.timestamp_ms
    )
