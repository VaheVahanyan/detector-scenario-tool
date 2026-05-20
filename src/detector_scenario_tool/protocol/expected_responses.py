from __future__ import annotations

from dataclasses import dataclass

from detector_scenario_tool.domain.scenario import AckPolicy


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


_SEND_DEFAULTS: dict[tuple[str, int], SendDefaults] = {
    ("KU", 0x0000): SendDefaults(AckPolicy.NONE, None, 1, 0, False, False),
    ("KU", 0x0001): SendDefaults(AckPolicy.NONE, None, 1, 0, False, False),

    ("KU", 0x0002): SendDefaults(AckPolicy.EXPECT_ACK, 1000, 3, 0, True, False),
    ("KU", 0x0003): SendDefaults(AckPolicy.EXPECT_ACK, 1000, 3, 0, True, False),
    ("KU", 0x0004): SendDefaults(AckPolicy.EXPECT_ACK, 1000, 3, 0, True, False),
    ("KU", 0x0005): SendDefaults(AckPolicy.EXPECT_ACK, 1000, 3, 0, True, False),
    ("KU", 0x0006): SendDefaults(AckPolicy.EXPECT_ACK, 1000, 3, 0, True, False),
    ("KU", 0x0007): SendDefaults(AckPolicy.EXPECT_ACK, 1000, 3, 0, True, False),
    ("KU", 0x0008): SendDefaults(AckPolicy.EXPECT_ACK, 1000, 3, 0, True, False),
    ("KU", 0x0009): SendDefaults(AckPolicy.EXPECT_ACK, 1000, 3, 0, True, False),
    ("KU", 0x000A): SendDefaults(AckPolicy.EXPECT_ACK, 1000, 3, 0, True, False),
    ("KU", 0x000B): SendDefaults(AckPolicy.EXPECT_ACK, 1000, 3, 0, True, False),
    ("KU", 0x000C): SendDefaults(AckPolicy.EXPECT_ACK, 1000, 3, 0, True, False),

    ("KT", 0x0100): SendDefaults(AckPolicy.NONE, None, 1, 0, False, False),
    ("KT", 0x0101): SendDefaults(AckPolicy.NONE, None, 1, 0, False, False),
    ("KT", 0x0102): SendDefaults(AckPolicy.NONE, None, 1, 0, False, False),
    ("KT", 0x0103): SendDefaults(AckPolicy.NONE, None, 1, 0, False, False),
}

_EXPECTED_RESPONSES: dict[tuple[str, int], list[ExpectedResponseSpec]] = {
    # CMD_TELEM_REQ -> ACK + Telemetry
    ("KU", 0x0000): [
        ExpectedResponseSpec(
            "TS", 0x0201, timeout_ms=1000, is_ack=True,
            bind_to_previous_ku=True, require_ack_ok=True,
        ),
        ExpectedResponseSpec("TS", 0x0202, timeout_ms=1000, is_ack=False),
    ],

    # CMD_STATUS_REQ -> ACK + Status
    ("KU", 0x0001): [
        ExpectedResponseSpec(
            "TS", 0x0201, timeout_ms=1000, is_ack=True,
            bind_to_previous_ku=True, require_ack_ok=True,
        ),
        ExpectedResponseSpec("TS", 0x0200, timeout_ms=1000, is_ack=False),
    ],

    # CMD_SET_TIME -> ACK
    ("KU", 0x0002): [
        ExpectedResponseSpec(
            "TS", 0x0201, timeout_ms=1000, is_ack=True,
            bind_to_previous_ku=True, require_ack_ok=True,
        ),
    ],

    # CMD_OBSERVE_START -> ACK + Status
    ("KU", 0x0003): [
        ExpectedResponseSpec(
            "TS", 0x0201, timeout_ms=1000, is_ack=True,
            bind_to_previous_ku=True, require_ack_ok=True,
        ),
        ExpectedResponseSpec("TS", 0x0200, timeout_ms=1000, is_ack=False),
    ],

    # CMD_OBSERVE_CTRL -> ACK
    ("KU", 0x0004): [
        ExpectedResponseSpec(
            "TS", 0x0201, timeout_ms=1000, is_ack=True,
            bind_to_previous_ku=True, require_ack_ok=True,
        ),
    ],

    # CMD_DUTY -> ACK
    # Статус там не всегда гарантирован ("при выходе также"), поэтому автоматически не вставляем.
    ("KU", 0x0005): [
        ExpectedResponseSpec(
            "TS", 0x0201, timeout_ms=1000, is_ack=True,
            bind_to_previous_ku=True, require_ack_ok=True,
        ),
    ],

    # CMD_DUMP -> ACK + Status
    ("KU", 0x0006): [
        ExpectedResponseSpec(
            "TS", 0x0201, timeout_ms=1000, is_ack=True,
            bind_to_previous_ku=True, require_ack_ok=True,
        ),
        ExpectedResponseSpec("TS", 0x0200, timeout_ms=1000, is_ack=False),
    ],

    # CMD_SET_CFG -> ACK
    ("KU", 0x0007): [
        ExpectedResponseSpec(
            "TS", 0x0201, timeout_ms=1000, is_ack=True,
            bind_to_previous_ku=True, require_ack_ok=True,
        ),
    ],

    # CMD_ERASE -> ACK + Status
    ("KU", 0x0008): [
        ExpectedResponseSpec(
            "TS", 0x0201, timeout_ms=1000, is_ack=True,
            bind_to_previous_ku=True, require_ack_ok=True,
        ),
        ExpectedResponseSpec("TS", 0x0200, timeout_ms=1000, is_ack=False),
    ],

    # CMD_TEST -> ACK + Status
    ("KU", 0x0009): [
        ExpectedResponseSpec(
            "TS", 0x0201, timeout_ms=1000, is_ack=True,
            bind_to_previous_ku=True, require_ack_ok=True,
        ),
        ExpectedResponseSpec("TS", 0x0200, timeout_ms=1000, is_ack=False),
    ],

    # CMD_TEST_RESULT -> ACK + Test results
    ("KU", 0x000A): [
        ExpectedResponseSpec(
            "TS", 0x0201, timeout_ms=1000, is_ack=True,
            bind_to_previous_ku=True, require_ack_ok=True,
        ),
        ExpectedResponseSpec("TS", 0x0203, timeout_ms=2000, is_ack=False),
    ],

    # CMD_SHUTDOWN -> ACK + Status
    ("KU", 0x000B): [
        ExpectedResponseSpec(
            "TS", 0x0201, timeout_ms=1000, is_ack=True,
            bind_to_previous_ku=True, require_ack_ok=True,
        ),
        ExpectedResponseSpec("TS", 0x0200, timeout_ms=1000, is_ack=False),
    ],

    # CMD_RESET_ALARM -> ACK
    ("KU", 0x000C): [
        ExpectedResponseSpec(
            "TS", 0x0201, timeout_ms=1000, is_ack=True,
            bind_to_previous_ku=True, require_ack_ok=True,
        ),
    ],
}


def get_send_defaults(category: str, msg_id: int) -> SendDefaults | None:
    return _SEND_DEFAULTS.get((category, msg_id))


def get_expected_responses(category: str, msg_id: int) -> list[ExpectedResponseSpec]:
    return list(_EXPECTED_RESPONSES.get((category, msg_id), []))
