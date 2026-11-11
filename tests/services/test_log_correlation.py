"""Lining a scenario up against a bench log (`services/log_correlation.py`).

The regression behind this module: a run that had received everything was painted red, because
every acknowledgement and status the scenario did not spell out as a wait step was "the next
unmatched record" and therefore "the first mismatch". These tests use what a real bench produces —
answers to every command, telemetry, repeats, the board's own text — and assert that only what is
actually wrong is reported as wrong.
"""

from __future__ import annotations

from detector_scenario_tool.domain.logs import LOG_CATEGORY, LogRecord
from detector_scenario_tool.domain.scenario import (
    AckPolicy,
    MessageRef,
    SendMessageStep,
    StepKind,
    WaitForTsStep,
    WaitTimeStep,
)
from detector_scenario_tool.protocol import registry
from detector_scenario_tool.protocol.errors import AckErrorCode
from detector_scenario_tool.protocol.fields import pack_message
from detector_scenario_tool.services.log_correlation import correlate
from message_ids import DUTY, STATUS_REQ, TELEM_REQ, TLM_MCILWAIN, TM_ACK, TM_STATUS, TM_TELEMETRY


# -- builders --------------------------------------------------------------------------

def _send(msg_id: int, category: str = "KU", ack_policy=AckPolicy.EXPECT_ACK) -> SendMessageStep:
    return SendMessageStep(
        id=f"s{msg_id:x}",
        kind=StepKind.SEND_KU if category == "KU" else StepKind.SEND_KT,
        message=MessageRef(category=category, msg_id=msg_id),
        ack_policy=ack_policy,
    )


def _wait(msg_id: int, require_ack_ok: bool = False, ack_for: int | None = None) -> WaitForTsStep:
    return WaitForTsStep(
        id=f"w{msg_id:x}",
        kind=StepKind.WAIT_FOR_TS,
        expected=MessageRef(category="TS", msg_id=msg_id),
        require_ack_ok=require_ack_ok,
        ack_for_msg_id=ack_for,
    )


def _pause() -> WaitTimeStep:
    return WaitTimeStep(id="p", kind=StepKind.WAIT_TIME, delay_ms=1000)


def _tx(msg_id: int, ts: int = 0, category: str = "KU", source: str = "host") -> LogRecord:
    return LogRecord(ts, "tx", category, msg_id, b"", source=source)


def _ack(for_id: int, ts: int = 0, rejected: bool = False, code: int = 0) -> LogRecord:
    spec = registry.find("TS", TM_ACK)
    values = dict(spec.default_payload())
    values.update(acknowledged_msg_id=for_id, rejected=int(rejected), error_code=code)
    return LogRecord(ts, "rx", "TS", TM_ACK, pack_message(spec, values), source="detector")


def _ts(msg_id: int, ts: int = 0) -> LogRecord:
    spec = registry.find("TS", msg_id)
    return LogRecord(ts, "rx", "TS", msg_id, pack_message(spec, spec.default_payload()), source="detector")


def _text(ts: int = 0, line: bytes = b"STATE IDLE -> DUTY") -> LogRecord:
    return LogRecord(ts, "rx", LOG_CATEGORY, 0x7DB, line, source="board", can_id=0x7DB)


# -- the bench -------------------------------------------------------------------------

class TestARealRunIsGreen:
    def test_answers_the_scenario_does_not_spell_out_are_not_errors(self):
        """Two commands with a pause between, no explicit wait steps: the shape that went red."""
        steps = [_send(STATUS_REQ), _pause(), _send(DUTY)]
        records = [
            _tx(STATUS_REQ, 10), _ack(STATUS_REQ, 12), _ts(TM_STATUS, 13), _text(14),
            _ts(TM_TELEMETRY, 500),
            _tx(DUTY, 1010), _ack(DUTY, 1012), _text(1013),
        ]

        result = correlate(steps, records)

        assert result.row_statuses == {0: "ok", 2: "ok"}
        assert result.first_mismatch_row is None
        assert result.problem_rows == set()

    def test_answers_are_attributed_to_the_command_they_answer(self):
        steps = [_send(STATUS_REQ), _send(DUTY)]
        records = [_tx(STATUS_REQ), _ack(STATUS_REQ), _ts(TM_STATUS), _tx(DUTY), _ack(DUTY)]

        result = correlate(steps, records)

        assert result.related_rows == {1: 0, 2: 0, 4: 1}
        assert result.explained_rows == {0, 1, 2, 3, 4}

    def test_answers_in_either_order_satisfy_their_wait_steps(self):
        """The status may overtake the acknowledgement; the runner buffers, so must this."""
        steps = [_send(STATUS_REQ), _wait(TM_ACK), _wait(TM_STATUS)]
        records = [_tx(STATUS_REQ), _ts(TM_STATUS), _ack(STATUS_REQ)]

        result = correlate(steps, records)

        assert result.row_statuses == {0: "ok", 1: "ok", 2: "ok"}
        assert result.step_to_log == {0: 0, 1: 2, 2: 1}

    def test_a_late_acknowledgement_after_the_next_command_still_counts(self):
        steps = [_send(STATUS_REQ), _wait(TM_ACK, ack_for=STATUS_REQ), _send(DUTY)]
        records = [_tx(STATUS_REQ), _tx(DUTY), _ack(STATUS_REQ)]

        result = correlate(steps, records)

        assert result.row_statuses == {0: "ok", 1: "ok", 2: "ok"}

    def test_repeats_of_a_cyclic_command_are_explained(self):
        steps = [_send(TLM_MCILWAIN, category="KT", ack_policy=AckPolicy.NONE)]
        records = [_tx(TLM_MCILWAIN, 0, "KT"), _tx(TLM_MCILWAIN, 20_000, "KT"), _tx(TLM_MCILWAIN, 40_000, "KT")]

        result = correlate(steps, records)

        assert result.row_statuses == {0: "ok"}
        assert result.related_rows == {1: 0, 2: 0}

    def test_the_payloads_own_log_of_a_received_command_matches_the_send(self):
        """`detector_log.c` writes the command it received as `dir=rx` — the payload's viewpoint."""
        steps = [_send(STATUS_REQ, ack_policy=AckPolicy.NONE)]
        records = [_tx(STATUS_REQ, source="detector")]
        records[0].direction = "rx"

        result = correlate(steps, records)

        assert result.row_statuses == {0: "ok"}


class TestWaitingIsNotFailing:
    def test_a_step_with_no_record_yet_is_current(self):
        steps = [_send(STATUS_REQ), _send(DUTY)]
        records = [_tx(STATUS_REQ), _ack(STATUS_REQ), _ts(TM_STATUS)]

        result = correlate(steps, records)

        assert result.row_statuses == {0: "ok", 1: "current"}
        assert result.current_step_row == 1

    def test_an_unsolicited_answer_does_not_fail_a_step_that_has_not_run(self):
        steps = [_send(STATUS_REQ)]

        result = correlate(steps, [_text(), _ack(STATUS_REQ)])

        assert result.row_statuses == {0: "current"}
        assert result.first_mismatch_row is None

    def test_steps_after_an_unsent_command_are_pending(self):
        steps = [_send(STATUS_REQ), _wait(TM_ACK), _send(DUTY)]

        result = correlate(steps, [_ts(TM_TELEMETRY)])

        assert result.row_statuses == {0: "current", 1: "pending", 2: "pending"}

    def test_live_with_nothing_logged_marks_the_first_step_current(self):
        result = correlate([_pause(), _send(STATUS_REQ), _send(DUTY)], [], live=True)

        assert result.row_statuses == {1: "current", 2: "pending"}


class TestRealProblemsAreStillReported:
    def test_a_skipped_wait_step_is_an_error_once_the_scenario_moved_on(self):
        steps = [_send(TELEM_REQ), _wait(TM_TELEMETRY), _send(DUTY)]
        records = [_tx(TELEM_REQ), _ack(TELEM_REQ), _tx(DUTY)]

        result = correlate(steps, records)

        assert result.row_statuses[1] == "error"
        assert result.first_mismatch_row == 1
        assert result.row_statuses[2] == "ok"

    def test_a_rejected_command_is_an_error(self):
        steps = [_send(DUTY)]
        records = [_tx(DUTY), _ack(DUTY, rejected=True, code=int(AckErrorCode.ERR_MODE))]

        result = correlate(steps, records)

        assert result.row_statuses == {0: "error"}
        assert result.problem_rows == {1}

    def test_a_rejection_is_not_an_error_when_no_acknowledgement_was_demanded(self):
        steps = [_send(DUTY, ack_policy=AckPolicy.NONE)]
        records = [_tx(DUTY), _ack(DUTY, rejected=True, code=int(AckErrorCode.ERR_MODE))]

        assert correlate(steps, records).row_statuses == {0: "ok"}

    def test_a_wait_step_demanding_acceptance_fails_on_a_rejection(self):
        steps = [_send(DUTY, ack_policy=AckPolicy.NONE), _wait(TM_ACK, require_ack_ok=True)]
        records = [_tx(DUTY), _ack(DUTY, rejected=True, code=int(AckErrorCode.ERR_MODE))]

        assert correlate(steps, records).row_statuses[1] == "error"

    def test_an_acknowledgement_of_another_command_does_not_satisfy_the_wait(self):
        steps = [_send(DUTY), _wait(TM_ACK)]
        records = [_tx(DUTY), _ack(STATUS_REQ)]

        result = correlate(steps, records)

        assert result.row_statuses[1] == "current"

    def test_a_broken_frame_matches_nothing_and_is_a_problem(self):
        steps = [_send(STATUS_REQ, ack_policy=AckPolicy.NONE), _wait(TM_STATUS)]
        broken = _ts(TM_STATUS)
        broken.valid = False
        records = [_tx(STATUS_REQ), broken]

        result = correlate(steps, records)

        assert result.row_statuses[1] == "current"
        assert result.problem_rows == {1}


class TestBoardOutput:
    def test_board_text_never_matches_and_is_never_a_problem(self):
        steps = [_send(STATUS_REQ, ack_policy=AckPolicy.NONE)]
        records = [_text(1), _tx(STATUS_REQ, 2), _text(3)]

        result = correlate(steps, records)

        assert result.step_to_log == {0: 1}
        assert result.problem_rows == set()
        assert 0 not in result.explained_rows
