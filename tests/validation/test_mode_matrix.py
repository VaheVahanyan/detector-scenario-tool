"""Command validity per mode, table-driven from the specification.

Source: Обработка_команд_CAN_NATALIA.md §5 (identical to Таблица_состояний_и_переходов §8 and to
Протокол_CAN_ГС_v2 §5.2.10).

The specification uses two different mode numberings — §4.1 for the telemetry mode byte
(TEST=2, ERASE=3) and §5.2 for these validity tables (ERASE=2, TEST=3). This test works with
symbolic names only, never with the numbers.
"""

from __future__ import annotations

import pytest

from detector_scenario_tool.protocol.modes import (
    COMMAND_TABLE_MODE_CODES,
    MODE_BY_TELEMETRY_CODE,
    TELEMETRY_MODE_CODES,
    Mode,
    decode_mode_byte,
    encode_mode_byte,
)
from detector_scenario_tool.validation.mode_analyzer import ALLOWED_KU_BY_MODE, KT_ALLOWED_MODES

SPEC_MODES = [
    Mode.DUTY,
    Mode.ERASE,
    Mode.TEST,
    Mode.OBSERVE,
    Mode.DUMP,
    Mode.ALARM,
    Mode.SHUTDOWN,
]

ALL = set(SPEC_MODES)

#: msg_id -> (symbol, modes where the command is allowed — the "+" cells of the doc table).
VALIDITY: dict[int, tuple[str, set[Mode]]] = {
    0x0000: ("CMD_TELEM_REQ", {Mode.DUTY, Mode.OBSERVE, Mode.ALARM}),
    0x0001: ("CMD_STATUS_REQ", ALL),
    0x0002: ("CMD_SET_TIME", {Mode.DUTY}),
    0x0003: ("CMD_OBSERVE_START", {Mode.DUTY}),
    0x0004: ("CMD_OBSERVE_CTRL", {Mode.OBSERVE}),
    0x0005: ("CMD_DUTY", {Mode.DUTY, Mode.ERASE, Mode.TEST, Mode.OBSERVE, Mode.DUMP}),
    0x0006: ("CMD_DUMP", {Mode.DUTY}),
    0x0007: ("CMD_SET_CFG", {Mode.DUTY, Mode.ALARM}),
    0x0008: ("CMD_ERASE", {Mode.DUTY}),
    0x0009: ("CMD_TEST", {Mode.DUTY}),
    0x000A: ("CMD_TEST_RESULT", {Mode.DUTY}),
    0x000B: (
        "CMD_SHUTDOWN",
        {Mode.DUTY, Mode.ERASE, Mode.TEST, Mode.OBSERVE, Mode.DUMP, Mode.ALARM},
    ),
    0x000C: ("CMD_RESET_ALARM", {Mode.ALARM}),
    0x0401: ("CMD_SET_TIME_SPUTNIKS", {Mode.DUTY}),
    0x0A61: ("CMD_SET_DEST_ID", ALL),
    0x0A62: ("CMD_SET_DEVICE_ID", ALL),
}


def _cases() -> list:
    return [
        pytest.param(
            msg_id,
            mode,
            mode in allowed,
            id=f"{symbol}-in-{mode.name}",
        )
        for msg_id, (symbol, allowed) in VALIDITY.items()
        for mode in SPEC_MODES
    ]


@pytest.mark.parametrize(("msg_id", "mode", "expected"), _cases())
def test_command_validity_per_mode(msg_id, mode, expected):
    assert (msg_id in ALLOWED_KU_BY_MODE[mode]) is expected


def test_every_control_command_is_covered_by_this_table():
    from detector_scenario_tool.protocol import registry

    known = {spec.msg_id for spec in registry.by_category("KU")}
    assert known == set(VALIDITY), "the matrix and the catalogue disagree"


def test_no_commands_are_permitted_in_init():
    """КУ and КТ received before the state machine leaves INIT are not processed (§6.1 note 3)."""
    assert ALLOWED_KU_BY_MODE[Mode.INIT] == set()


def test_telemetry_commands_are_observe_only():
    """§6: КТ/TC are ignored without an acknowledgement outside OBSERVE."""
    assert KT_ALLOWED_MODES == {Mode.OBSERVE}


def test_shutdown_only_accepts_status_and_address_commands():
    """§10.3: «в SHUTDOWN разрешены CMD_STATUS_REQ, CMD_SET_DEST_ID и CMD_SET_DEVICE_ID»."""
    assert ALLOWED_KU_BY_MODE[Mode.SHUTDOWN] == {0x0001, 0x0A61, 0x0A62}


class TestModeNumbering:
    """The two numbering schemes must not be confused (Таблица_состояний §3.1 note 2)."""

    def test_telemetry_encoding_puts_test_before_erase(self):
        assert TELEMETRY_MODE_CODES[Mode.TEST] == 2
        assert TELEMETRY_MODE_CODES[Mode.ERASE] == 3

    def test_command_table_numbering_puts_erase_before_test(self):
        assert COMMAND_TABLE_MODE_CODES[Mode.ERASE] == 2
        assert COMMAND_TABLE_MODE_CODES[Mode.TEST] == 3

    def test_the_two_schemes_really_do_differ(self):
        assert TELEMETRY_MODE_CODES[Mode.TEST] != COMMAND_TABLE_MODE_CODES[Mode.TEST]

    def test_mode_byte_round_trip(self):
        """Bits 0-2 previous, bits 3-5 current, bits 6-7 reserved."""
        value = encode_mode_byte(previous=Mode.DUTY, current=Mode.OBSERVE)
        assert value == 0b0100_001
        assert decode_mode_byte(value) == (Mode.DUTY, Mode.OBSERVE)

    def test_every_telemetry_code_decodes_back(self):
        for mode, code in TELEMETRY_MODE_CODES.items():
            assert MODE_BY_TELEMETRY_CODE[code] is mode
