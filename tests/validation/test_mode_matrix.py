"""Command validity per mode, table-driven from the specification.

Source: Обработка_команд_CAN_NATALIA.md §5 (identical to Таблица_состояний_и_переходов §8 and to
Протокол_CAN_ГС_v2_1_Спутникс §5.2.10).

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

#: symbol -> the modes where the command is allowed, i.e. the "+" cells of the doc table.
#:
#: Keyed by symbol rather than by MSG_ID: the specification has renumbered the catalogue twice, and
#: the matrix itself was unchanged both times. Identifiers belong in the conformance test that
#: checks them, not scattered through the behavioural ones.
VALIDITY: dict[str, set[Mode]] = {
    "CMD_TELEM_REQ": {Mode.DUTY, Mode.OBSERVE, Mode.ALARM},
    "CMD_STATUS_REQ": ALL,
    "CMD_SET_TIME": {Mode.DUTY},
    "CMD_OBSERVE_START": {Mode.DUTY},
    "CMD_OBSERVE_CTRL": {Mode.OBSERVE},
    "CMD_DUTY": {Mode.DUTY, Mode.ERASE, Mode.TEST, Mode.OBSERVE, Mode.DUMP},
    "CMD_DUMP": {Mode.DUTY},
    "CMD_SET_CFG": {Mode.DUTY, Mode.ALARM},
    "CMD_ERASE": {Mode.DUTY},
    "CMD_TEST": {Mode.DUTY},
    "CMD_TEST_RESULT": {Mode.DUTY},
    "CMD_SHUTDOWN": {Mode.DUTY, Mode.ERASE, Mode.TEST, Mode.OBSERVE, Mode.DUMP, Mode.ALARM},
    "CMD_RESET_ALARM": {Mode.ALARM},
    "CMD_SET_TIME_BVS": {Mode.DUTY},
    "CMD_SET_DEST_ID": ALL,
    "CMD_SET_DEVICE_ID": ALL,
    # v2.1 КУ 17 — allowed in every mode (§5.2.10 row 17).
    "CMD_GET_VERSION": ALL,
}


def _cases() -> list:
    return [
        pytest.param(symbol, mode, mode in allowed, id=f"{symbol}-in-{mode.name}")
        for symbol, allowed in VALIDITY.items()
        for mode in SPEC_MODES
    ]


@pytest.mark.parametrize(("symbol", "mode", "expected"), _cases())
def test_command_validity_per_mode(symbol, mode, expected):
    assert (_id(symbol) in ALLOWED_KU_BY_MODE[mode]) is expected


def test_every_control_command_is_covered_by_this_table():
    from detector_scenario_tool.protocol import registry

    known = {spec.symbol for spec in registry.by_category("KU")}
    assert known == set(VALIDITY), "the matrix and the catalogue disagree"


def test_no_commands_are_permitted_in_init():
    """КУ and КТ received before the state machine leaves INIT are not processed (§6.1 note 3)."""
    assert ALLOWED_KU_BY_MODE[Mode.INIT] == set()


def test_telemetry_commands_are_observe_only():
    """§6: КТ/TC are ignored without an acknowledgement outside OBSERVE."""
    assert KT_ALLOWED_MODES == {Mode.OBSERVE}


def test_shutdown_only_accepts_status_and_address_commands():
    """§10.3: «в SHUTDOWN разрешены CMD_STATUS_REQ, CMD_SET_DEST_ID и CMD_SET_DEVICE_ID»."""
    assert ALLOWED_KU_BY_MODE[Mode.SHUTDOWN] == {
        _id("CMD_STATUS_REQ"), _id("CMD_SET_DEST_ID"), _id("CMD_SET_DEVICE_ID"),
        # v2.1 adds the version query, which §5.2.10 permits in every mode including SHUTDOWN.
        _id("CMD_GET_VERSION"),
    }


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


def _id(symbol: str) -> int:
    from detector_scenario_tool.protocol import registry

    spec = registry.by_symbol(symbol)
    assert spec is not None, f"{symbol} is not in the catalogue"
    return spec.msg_id
