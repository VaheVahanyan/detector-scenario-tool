"""Scenario-level validation rules.

Field ranges are covered by tests/protocol/test_definitions.py; this file is about the rules that
concern the *sequence* of steps and the mode the scenario is in.
"""

from __future__ import annotations

import pytest

from detector_scenario_tool.domain.scenario import (
    AckPolicy,
    MessageRef,
    ScenarioDocument,
    ScenarioMetadata,
    SendMessageStep,
    StepKind,
    ValidationProfile,
    WaitForTsStep,
)
from detector_scenario_tool.protocol import registry
from detector_scenario_tool.validation.analyzer import analyze_scenario
from detector_scenario_tool.validation.diagnostics import Severity
from detector_scenario_tool.validation.mode_analyzer import mode_at_step
from detector_scenario_tool.protocol.modes import Mode


def _document(*steps) -> ScenarioDocument:
    return ScenarioDocument(
        schema_version=2,
        metadata=ScenarioMetadata(name="t"),
        validation=ValidationProfile(),
        steps=list(steps),
    )


def _send(msg_id: int, category: str = "KU", payload: dict | None = None, sid: str = "s"):
    spec = registry.find(category, msg_id)
    return SendMessageStep(
        id=sid,
        kind=StepKind.SEND_KU if category == "KU" else StepKind.SEND_KT,
        message=MessageRef(category=category, msg_id=msg_id, name=""),
        payload=dict(payload if payload is not None else spec.default_payload()),
        ack_policy=AckPolicy.EXPECT_ACK if category == "KU" else AckPolicy.NONE,
        ack_timeout_ms=1000 if category == "KU" else None,
    )


def _wait(msg_id: int = 0x0201, sid: str = "w", **kw):
    # Acknowledgement options only make sense on a wait for ТС «Квитанция».
    is_ack = msg_id == 0x0201
    return WaitForTsStep(
        id=sid,
        kind=StepKind.WAIT_FOR_TS,
        expected=MessageRef(category="TS", msg_id=msg_id, name=""),
        timeout_ms=kw.pop("timeout_ms", 1000),
        bind_to_previous_ku=kw.pop("bind_to_previous_ku", is_ack),
        require_ack_ok=kw.pop("require_ack_ok", is_ack),
        **kw,
    )


def _codes(document) -> list[str]:
    return [d.code for d in analyze_scenario(document)]


class TestWellFormedScenarios:
    def test_status_request_with_its_responses_is_clean(self):
        document = _document(
            _send(0x0001, sid="s1"),
            _wait(0x0201, sid="w1"),
            _wait(0x0200, sid="w2"),
        )
        assert _codes(document) == []

    def test_missing_message_is_an_error(self):
        step = _send(0x0001)
        step.message = None
        diagnostics = analyze_scenario(_document(step))
        assert diagnostics[0].code == "message.missing"
        assert diagnostics[0].severity is Severity.ERROR


class TestAcknowledgementRules:
    def test_missing_ack_wait_is_flagged(self):
        assert "ack.wait_missing" in _codes(_document(_send(0x0001)))

    def test_telemetry_command_followed_by_an_ack_wait_is_an_error(self):
        """§2.3: КТ are never acknowledged, so such a wait can only time out."""
        document = _document(_send(0x0100, category="KT", sid="s1"), _wait(0x0201, sid="w1"))
        diagnostics = analyze_scenario(document)
        codes = {d.code: d for d in diagnostics}
        assert "ack.wait_after_kt" in codes
        assert codes["ack.wait_after_kt"].severity is Severity.ERROR

    def test_telemetry_command_expecting_an_ack_is_flagged(self):
        step = _send(0x0100, category="KT", sid="s1")
        step.ack_policy = AckPolicy.EXPECT_ACK
        assert "ack.not_expected_for_kt" in _codes(_document(step))

    def test_sputniks_time_missing_ack_is_only_informational(self):
        """§9.14: the command may be ignored entirely, so a missing ack is legitimate."""
        diagnostics = analyze_scenario(_document(_send(0x0401, sid="s1")))
        by_code = {d.code: d for d in diagnostics}
        assert by_code["ack.wait_missing"].severity is Severity.INFO

    def test_ack_bound_to_the_wrong_command_is_an_error(self):
        document = _document(
            _send(0x0001, sid="s1"),
            _wait(0x0201, sid="w1", bind_to_previous_ku=False, ack_for_msg_id=0x0009),
        )
        codes = {d.code: d for d in analyze_scenario(document)}
        assert "ack.binding_mismatch" in codes
        assert codes["ack.binding_mismatch"].severity is Severity.ERROR

    def test_ack_requiring_acceptance_without_a_binding_is_flagged(self):
        document = _document(
            _send(0x0001, sid="s1"),
            _wait(0x0201, sid="w1", bind_to_previous_ku=False, ack_for_msg_id=None),
        )
        assert "ack.binding_missing" in _codes(document)


class TestFollowUpResponses:
    def test_missing_status_wait_is_flagged(self):
        """CMD_ERASE produces ТС «Статус» after the acknowledgement."""
        document = _document(_send(0x0008, sid="s1"), _wait(0x0201, sid="w1"))
        assert "response.wait_missing" in _codes(document)

    def test_status_wait_may_come_after_the_ack(self):
        document = _document(
            _send(0x0008, sid="s1"), _wait(0x0201, sid="w1"), _wait(0x0200, sid="w2")
        )
        assert "response.wait_missing" not in _codes(document)

    def test_optional_status_after_cmd_duty_is_not_demanded(self):
        """§9.6 only promises a status when the mode actually changes."""
        document = _document(_send(0x0005, sid="s1"), _wait(0x0201, sid="w1"))
        assert "response.wait_missing" not in _codes(document)


class TestWaitSteps:
    def test_wait_without_a_message_is_an_error(self):
        step = _wait(0x0201)
        step.expected = None
        assert "wait_ts.expected_missing" in _codes(_document(step))

    def test_waiting_for_a_control_command_is_an_error(self):
        step = _wait(0x0201)
        step.expected = MessageRef(category="KU", msg_id=0x0001, name="")
        assert "wait_ts.not_a_telemetry_message" in _codes(_document(step))

    def test_ack_options_on_a_status_wait_are_flagged(self):
        step = _wait(0x0200, bind_to_previous_ku=True, require_ack_ok=True)
        assert "wait_ts.ack_options_on_non_ack" in _codes(_document(step))


class TestModeTracking:
    def test_observe_ctrl_outside_observation_is_an_error(self):
        document = _document(_send(0x0004, sid="s1"))
        codes = {d.code: d for d in analyze_scenario(document)}
        assert codes["mode.ku_not_allowed"].severity is Severity.ERROR

    def test_observe_ctrl_after_observe_start_is_allowed(self):
        document = _document(
            _send(0x0003, sid="s1"),
            _wait(0x0201, sid="w1"),
            _wait(0x0200, sid="w2"),
            _send(0x0004, sid="s2"),
            _wait(0x0201, sid="w3"),
        )
        assert "mode.ku_not_allowed" not in _codes(document)

    def test_telemetry_command_outside_observation_is_a_warning_not_an_error(self):
        """The НА drops it silently, so the scenario still runs — it just loses the data."""
        document = _document(_send(0x0100, category="KT", sid="s1"))
        codes = {d.code: d for d in analyze_scenario(document)}
        assert codes["mode.kt_ignored"].severity is Severity.WARNING

    def test_telemetry_command_during_observation_is_clean(self):
        document = _document(
            _send(0x0003, sid="s1"),
            _wait(0x0201, sid="w1"),
            _wait(0x0200, sid="w2"),
            _send(0x0100, category="KT", sid="s2"),
        )
        assert "mode.kt_ignored" not in _codes(document)

    @pytest.mark.parametrize(
        ("command", "expected_mode"),
        [
            (0x0003, Mode.OBSERVE),
            (0x0006, Mode.DUMP),
            (0x0008, Mode.ERASE),
            (0x0009, Mode.TEST),
            (0x000B, Mode.SHUTDOWN),
        ],
    )
    def test_mode_transitions(self, command, expected_mode):
        document = _document(_send(command, sid="s1"))
        assert mode_at_step(document, 1) is expected_mode

    def test_cmd_duty_returns_from_a_long_mode(self):
        document = _document(_send(0x0008, sid="s1"), _send(0x0005, sid="s2"))
        assert mode_at_step(document, 2) is Mode.DUTY

    def test_disabled_steps_do_not_change_the_mode(self):
        erase = _send(0x0008, sid="s1")
        erase.enabled = False
        document = _document(erase, _send(0x0002, sid="s2"))
        assert mode_at_step(document, 2) is Mode.DUTY

    def test_a_rejected_command_does_not_change_the_mode(self):
        """CMD_OBSERVE_CTRL is refused outside OBSERVE, so it cannot move the state machine."""
        document = _document(_send(0x0004, sid="s1"), _send(0x0002, sid="s2"))
        assert mode_at_step(document, 2) is Mode.DUTY
        assert "mode.ku_not_allowed" in _codes(document)


class TestPayloadValidation:
    def test_out_of_range_field_is_reported_against_the_step(self):
        document = _document(
            _send(0x0002, payload={"board_time_ms": 5000, "board_time_s": 0}, sid="s1")
        )
        diagnostics = [d for d in analyze_scenario(document) if d.code == "field.out_of_range"]
        assert len(diagnostics) == 1
        assert diagnostics[0].step_index == 0
        assert diagnostics[0].params["field_key"] == "field.board_time_ms"

    def test_cross_field_rule_is_reported(self):
        payload = registry.find("KU", 0x0003).default_payload()
        payload["event_format_mode"] = 1  # events on, but Nmax stays 0
        assert "observation.events_nmax_mismatch" in _codes(
            _document(_send(0x0003, payload=payload, sid="s1"))
        )

    def test_spectrum_without_histogram_bins_is_reported(self):
        payload = registry.find("KU", 0x0003).default_payload()
        payload["spectrum_mode"] = 1  # Спектр-1 requires a non-zero Nhist
        assert "observation.spectrum_nhist_mismatch" in _codes(
            _document(_send(0x0003, payload=payload, sid="s1"))
        )
