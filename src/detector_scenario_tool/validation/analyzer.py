"""Scenario validation.

Field-level checks (ranges, reserved bits, AAh fillers, cross-field consistency) are derived from
the message definitions, so this module only holds the rules that are about the *scenario* —
sequencing of sends and waits, acknowledgement bindings, timeouts — plus mode tracking.
"""

from __future__ import annotations

from detector_scenario_tool.domain.scenario import (
    AckPolicy,
    ScenarioDocument,
    ScenarioStep,
    SendMessageStep,
    StepKind,
    WaitForTsStep,
)
from detector_scenario_tool.protocol import registry
from detector_scenario_tool.protocol.fields import AckBehaviour, validate_payload
from detector_scenario_tool.validation.diagnostics import Diagnostic, Severity
from detector_scenario_tool.validation.mode_analyzer import analyze_modes

ACK_MSG_ID = 0x0201
STATUS_MSG_ID = 0x0200


def analyze_scenario(document: ScenarioDocument) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []

    for index, step in enumerate(document.steps):
        if isinstance(step, SendMessageStep):
            _check_send_step(document, step, index, diagnostics)
        elif isinstance(step, WaitForTsStep):
            _check_wait_ts_step(step, index, diagnostics)

    diagnostics.extend(analyze_modes(document))
    diagnostics.sort(key=lambda d: (d.step_index, d.code))
    return diagnostics


# --------------------------------------------------------------------------------------
# Send steps
# --------------------------------------------------------------------------------------

def _check_send_step(
        document: ScenarioDocument,
        step: SendMessageStep,
        index: int,
        diagnostics: list[Diagnostic],
) -> None:
    if step.message is None or step.message.msg_id is None:
        diagnostics.append(
            Diagnostic(Severity.ERROR, index, "message.missing")
        )
        return

    spec = registry.find(step.message.category, step.message.msg_id)
    if spec is None:
        diagnostics.append(
            Diagnostic(
                Severity.ERROR,
                index,
                "message.unknown",
                {"category": step.message.category, "msg": f"0x{step.message.msg_id:04X}"},
            )
        )
        return

    if step.kind is StepKind.SEND_KU and spec.category != "KU":
        diagnostics.append(
            Diagnostic(
                Severity.ERROR, index, "message.category_mismatch",
                {"expected": "KU", "actual": spec.category},
            )
        )
    elif step.kind is StepKind.SEND_KT and spec.category != "KT":
        diagnostics.append(
            Diagnostic(
                Severity.ERROR, index, "message.category_mismatch",
                {"expected": "KT", "actual": spec.category},
            )
        )

    _check_custom(spec, index, diagnostics)
    _check_payload(spec, step, index, diagnostics)
    _check_cyclic(document, spec, step, index, diagnostics)
    _check_response_sequence(document, spec, step, index, diagnostics)


def _check_custom(spec, index: int, diagnostics: list[Diagnostic]) -> None:
    """A user-defined message is legitimate but unverifiable — say so once, as information."""
    if not spec.custom:
        return

    diagnostics.append(
        Diagnostic(
            Severity.INFO,
            index,
            "custom.unknown_to_protocol",
            {"symbol": spec.symbol, "msg": f"0x{spec.msg_id:04X}"},
        )
    )

    if spec.length > 6 and spec.forced_long is False:
        diagnostics.append(
            Diagnostic(
                Severity.ERROR, index, "custom.too_long_for_short",
                {"length": spec.length, "max": 6},
            )
        )


def _check_payload(spec, step: SendMessageStep, index: int, diagnostics: list[Diagnostic]) -> None:
    for issue in validate_payload(spec, step.payload):
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                step_index=index,
                code=issue.code,
                params={
                    "field_key": f"field.{issue.key}" if issue.key else "",
                    "symbol": spec.symbol,
                    **issue.params,
                },
            )
        )


def _remaining_duration_ms(document: ScenarioDocument, index: int) -> int:
    """How long the run still lasts after `index`, as far as the scenario itself decides."""
    total = 0
    for step in document.steps[index + 1:]:
        if not getattr(step, "enabled", True):
            continue
        total += getattr(step, "delay_ms", 0) or getattr(step, "timeout_ms", 0) or 0
    return total


def _check_cyclic(
        document: ScenarioDocument,
        spec,
        step: SendMessageStep,
        index: int,
        diagnostics: list[Diagnostic],
) -> None:
    if step.cyclic is None or not step.cyclic.enabled:
        return

    if spec.cyclic_default is None:
        diagnostics.append(
            Diagnostic(
                Severity.WARNING, index, "cyclic.not_supported", {"symbol": spec.symbol}
            )
        )
        return

    # Repeats stop when the run does, so a scenario that ends straight after the send never
    # actually repeats anything — an easy trap when the trailing wait is forgotten.
    remaining = _remaining_duration_ms(document, index)
    if remaining < step.cyclic.period_ms:
        diagnostics.append(
            Diagnostic(
                Severity.WARNING,
                index,
                "cyclic.no_time_to_repeat",
                {
                    "symbol": spec.symbol,
                    "period": step.cyclic.period_ms // 1000,
                    "remaining": remaining // 1000,
                },
            )
        )

    # A repeat outside the mode that accepts the message is dropped by the НА, silently for a КТ.
    if len(spec.allowed_modes) == 1:
        only_mode = next(iter(spec.allowed_modes))
        diagnostics.append(
            Diagnostic(
                Severity.INFO,
                index,
                "cyclic.mode_scope",
                {
                    "symbol": spec.symbol,
                    "mode_key": only_mode.label_key,
                    "period": step.cyclic.period_ms // 1000,
                },
            )
        )


def _check_response_sequence(
        document: ScenarioDocument,
        spec,
        step: SendMessageStep,
        index: int,
        diagnostics: list[Diagnostic],
) -> None:
    next_step = _step_at(document, index + 1)

    if spec.ack is AckBehaviour.NONE:
        # §2.3: телеметрические команды не квитируются. A wait for an acknowledgement after one
        # will always time out.
        if step.ack_policy is not AckPolicy.NONE:
            diagnostics.append(
                Diagnostic(
                    Severity.WARNING, index, "ack.not_expected_for_kt", {"symbol": spec.symbol}
                )
            )
        if _is_ack_wait(next_step):
            diagnostics.append(
                Diagnostic(
                    Severity.ERROR, index + 1, "ack.wait_after_kt", {"symbol": spec.symbol}
                )
            )
        return

    if spec.ack is AckBehaviour.ACK_MAY_BE_SUPPRESSED:
        # §9.14: silently ignored when bit 1 of the CAN control word is set, so a missing
        # acknowledgement is legitimate and must not be treated as a failure.
        if step.ack_policy is AckPolicy.EXPECT_ACK:
            diagnostics.append(
                Diagnostic(
                    Severity.WARNING, index, "ack.may_be_suppressed", {"symbol": spec.symbol}
                )
            )

    if step.ack_policy is not AckPolicy.NONE and step.ack_timeout_ms is None:
        diagnostics.append(
            Diagnostic(Severity.WARNING, index, "ack.timeout_missing", {"symbol": spec.symbol})
        )

    if not _is_ack_wait(next_step):
        severity = (
            Severity.INFO
            if spec.ack is AckBehaviour.ACK_MAY_BE_SUPPRESSED
            else Severity.WARNING
        )
        diagnostics.append(
            Diagnostic(severity, index, "ack.wait_missing", {"symbol": spec.symbol})
        )
    else:
        _check_ack_binding(spec, next_step, index + 1, diagnostics)

    _check_follow_up_waits(document, spec, index, diagnostics)


def _check_ack_binding(spec, wait_step: WaitForTsStep, index: int, diagnostics) -> None:
    if wait_step.require_ack_ok and not wait_step.bind_to_previous_ku:
        if wait_step.ack_for_msg_id is None:
            diagnostics.append(
                Diagnostic(Severity.WARNING, index, "ack.binding_missing")
            )
        elif wait_step.ack_for_msg_id != spec.msg_id:
            diagnostics.append(
                Diagnostic(
                    Severity.ERROR, index, "ack.binding_mismatch",
                    {
                        "expected": f"0x{spec.msg_id:04X}",
                        "actual": f"0x{wait_step.ack_for_msg_id:04X}",
                    },
                )
            )


def _check_follow_up_waits(
        document: ScenarioDocument,
        spec,
        index: int,
        diagnostics: list[Diagnostic],
) -> None:
    """Warn when a guaranteed telemetry message is never waited for.

    The acknowledgement may be followed by ТС «Статус», «Телеметрия» or «Результаты теста», and the
    protocol allows either ordering of the wait steps, so look a few steps ahead rather than
    demanding an exact position.
    """
    expected = [r for r in spec.follow_up if not r.is_ack and r.guaranteed]
    if not expected:
        return

    lookahead = [
        _step_at(document, index + offset) for offset in range(1, 4)
    ]
    waited_ids = {
        s.expected.msg_id
        for s in lookahead
        if isinstance(s, WaitForTsStep) and s.expected is not None
    }

    for response in expected:
        if response.msg_id not in waited_ids:
            diagnostics.append(
                Diagnostic(
                    Severity.WARNING,
                    index,
                    "response.wait_missing",
                    {"symbol": spec.symbol, "response": f"0x{response.msg_id:04X}"},
                )
            )


# --------------------------------------------------------------------------------------
# Wait steps
# --------------------------------------------------------------------------------------

def _check_wait_ts_step(step: WaitForTsStep, index: int, diagnostics: list[Diagnostic]) -> None:
    if step.expected is None or step.expected.msg_id is None:
        diagnostics.append(Diagnostic(Severity.ERROR, index, "wait_ts.expected_missing"))
        return

    spec = registry.find(step.expected.category, step.expected.msg_id)
    if spec is None:
        diagnostics.append(
            Diagnostic(
                Severity.ERROR, index, "wait_ts.unknown_message",
                {"category": step.expected.category, "msg": f"0x{step.expected.msg_id:04X}"},
            )
        )
        return

    if spec.category != "TS":
        diagnostics.append(
            Diagnostic(
                Severity.ERROR, index, "wait_ts.not_a_telemetry_message",
                {"symbol": spec.symbol},
            )
        )

    if step.timeout_ms <= 0:
        diagnostics.append(Diagnostic(Severity.WARNING, index, "wait_ts.timeout_zero"))

    if step.expected.msg_id != ACK_MSG_ID and (
            step.bind_to_previous_ku or step.require_ack_ok or step.ack_for_msg_id is not None
    ):
        diagnostics.append(
            Diagnostic(
                Severity.WARNING, index, "wait_ts.ack_options_on_non_ack",
                {"symbol": spec.symbol},
            )
        )


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------

def _step_at(document: ScenarioDocument, index: int) -> ScenarioStep | None:
    if 0 <= index < len(document.steps):
        return document.steps[index]
    return None


def _is_ack_wait(step: ScenarioStep | None) -> bool:
    return (
        isinstance(step, WaitForTsStep)
        and step.expected is not None
        and step.expected.category == "TS"
        and step.expected.msg_id == ACK_MSG_ID
    )
