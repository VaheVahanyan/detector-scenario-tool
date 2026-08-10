"""Send defaults and the responses a message is expected to produce.

Both are derived from the message definitions: `MessageDef.ack` decides whether an acknowledgement
is expected at all, `MessageDef.follow_up` lists the telemetry messages that follow it.
"""

from __future__ import annotations

from dataclasses import dataclass

from detector_scenario_tool.domain.scenario import AckPolicy
from detector_scenario_tool.protocol import registry
from detector_scenario_tool.protocol.fields import AckBehaviour, ExpectedResponse

DEFAULT_ACK_TIMEOUT_MS = 1000
#: §5.4 of the CAN protocol: at least three retransmissions on a UniCAN error.
DEFAULT_ATTEMPTS = 3


@dataclass(frozen=True)
class SendDefaults:
    ack_policy: AckPolicy
    ack_timeout_ms: int | None
    attempts: int
    retry_delay_ms: int
    retry_on_timeout: bool
    retry_on_reject: bool


@dataclass(frozen=True)
class ExpectedResponseSpec:
    category: str
    msg_id: int
    timeout_ms: int = 1000
    is_ack: bool = False
    bind_to_previous_ku: bool = False
    require_ack_ok: bool = False
    guaranteed: bool = True


def _to_spec(response: ExpectedResponse) -> ExpectedResponseSpec:
    return ExpectedResponseSpec(
        category=response.category,
        msg_id=response.msg_id,
        timeout_ms=response.timeout_ms,
        is_ack=response.is_ack,
        bind_to_previous_ku=response.bind_to_previous_ku,
        require_ack_ok=response.require_ack_ok,
        guaranteed=response.guaranteed,
    )


def get_send_defaults(category: str, msg_id: int) -> SendDefaults | None:
    spec = registry.find(category, msg_id)
    if spec is None or not spec.sendable:
        return None

    if spec.ack is AckBehaviour.NONE:
        # Телеметрия: «на КТ ТС «Квитанция» не выдается» (§2.3).
        return SendDefaults(AckPolicy.NONE, None, 1, 0, False, False)

    if spec.ack is AckBehaviour.ACK_MAY_BE_SUPPRESSED:
        # CMD_SET_TIME_SPUTNIKS may be ignored entirely, so a missing acknowledgement is not a
        # failure and must not be retried.
        return SendDefaults(
            AckPolicy.OPTIONAL_ACK, DEFAULT_ACK_TIMEOUT_MS, 1, 0, False, False
        )

    return SendDefaults(
        AckPolicy.EXPECT_ACK,
        DEFAULT_ACK_TIMEOUT_MS,
        DEFAULT_ATTEMPTS,
        0,
        True,
        False,
    )


def get_expected_responses(category: str, msg_id: int) -> list[ExpectedResponseSpec]:
    spec = registry.find(category, msg_id)
    if spec is None:
        return []
    return [_to_spec(response) for response in spec.follow_up]


def get_guaranteed_responses(category: str, msg_id: int) -> list[ExpectedResponseSpec]:
    """Only the responses the protocol always produces, for auto-inserting scenario steps."""
    return [r for r in get_expected_responses(category, msg_id) if r.guaranteed]
