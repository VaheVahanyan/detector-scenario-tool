"""Conformance with Протокол_CAN_ГС_v2.

This file started life as the phase 1 checklist, with every expectation marked
``xfail(strict=True)`` against the old pre-v2 tables. Phase 1 landed, the markers are gone, and
these are now the regression tests that keep the catalogue matching the specification.
"""

from __future__ import annotations

import pytest

from detector_scenario_tool.protocol import registry
from detector_scenario_tool.protocol.catalog import ProtocolCatalog
from detector_scenario_tool.protocol.fields import AckBehaviour
from detector_scenario_tool.protocol.message_lengths import get_expected_message_length

pytestmark = pytest.mark.protocol_v2

CATALOG = ProtocolCatalog()


@pytest.mark.parametrize(
    ("msg_id", "symbol"),
    [
        (0x0401, "CMD_SET_TIME_SPUTNIKS"),
        (0x0A61, "CMD_SET_DEST_ID"),
        (0x0A62, "CMD_SET_DEVICE_ID"),
    ],
)
def test_sputniks_control_commands_exist(msg_id, symbol):
    """§3.1: the command set is 16 control commands, not the 13 of the previous revision."""
    spec = registry.find("KU", msg_id)
    assert spec is not None
    assert spec.symbol == symbol


def test_control_command_count():
    assert len(registry.by_category("KU")) == 16


@pytest.mark.parametrize(
    ("category", "msg_id", "expected_length", "what"),
    [
        ("KU", 0x0007, 66, "CMD_SET_CFG including the CAN control word"),
        ("TS", 0x0202, 100, "ТС «Телеметрия»"),
        ("TS", 0x0203, 6146, "ТС «Результаты теста ППЗУ» (6144 + CRC)"),
    ],
)
def test_message_lengths(category, msg_id, expected_length, what):
    assert get_expected_message_length(category, msg_id) == expected_length, what


@pytest.mark.parametrize(
    ("msg_id", "symbol", "expected_length", "ni_format"),
    [
        (0xF210, "TLM_TIME_ORBIT_ATT", 125, "05h"),
        (0xF221, "TLM_MAGFIELD", 76, "06h"),
        (0x0100, "TLM_MCILWAIN", 24, "07h"),
    ],
)
def test_v2_telemetry_commands(msg_id, symbol, expected_length, ni_format):
    """§3.2: the three КТ of v2, each producing one НИ format."""
    spec = registry.find("KT", msg_id)
    assert spec is not None
    assert spec.symbol == symbol
    assert spec.length == expected_length
    assert ni_format in spec.doc_ref


@pytest.mark.parametrize("msg_id", [0x0101, 0x0102, 0x0103])
def test_pre_v2_telemetry_commands_are_gone(msg_id):
    assert registry.find("KT", msg_id) is None


def test_all_telemetry_commands_are_long():
    """24, 76 and 125 bytes all exceed the 6-byte UniCAN short-message limit."""
    kt_messages = registry.by_category("KT")
    assert len(kt_messages) == 3
    assert all(spec.is_long for spec in kt_messages)


def test_telemetry_commands_get_no_acknowledgement():
    """§2.3: «на КТ ТС «Квитанция» не выдается»."""
    for spec in registry.by_category("KT"):
        assert spec.ack is AckBehaviour.NONE
        assert not any(r.is_ack for r in spec.follow_up), spec.symbol


def test_only_sputniks_time_may_go_unacknowledged():
    """§2.4: the single exception to "every КУ is acknowledged"."""
    suppressible = [
        spec.symbol
        for spec in registry.by_category("KU")
        if spec.ack is AckBehaviour.ACK_MAY_BE_SUPPRESSED
    ]
    assert suppressible == ["CMD_SET_TIME_SPUTNIKS"]


def test_test_result_request_packs_the_mram_bank():
    """§2.11: hw config bits 0-1 select the NAND bank, bits 2-3 the MRAM copy."""
    from detector_scenario_tool.protocol.packers import pack_message_payload

    packed = pack_message_payload(
        category="KU",
        msg_id=0x000A,
        payload={"selected_nand_bank": 2, "selected_mram_bank": 2},
    )
    # NAND2 = 2 in bits 0-1, MRAM2 = 2 << 2 = 8 in bits 2-3.
    assert packed[0] == 0x0A


def test_observe_ctrl_carries_the_registration_threshold():
    """§9.5 action 3 writes the threshold to the ПЭД register, so bits 12-15 are in use."""
    spec = registry.find("KU", 0x0004)
    threshold = spec.field("particle_threshold")
    assert threshold is not None
    assert (threshold.bit_offset, threshold.bit_length) == (12, 4)


def test_observe_ctrl_reserves_the_bank_selector_bits_to_three():
    """§9.5: «биты 0–1 аппаратной конфигурации равны 3»."""
    from detector_scenario_tool.protocol.packers import pack_message_payload

    packed = pack_message_payload(category="KU", msg_id=0x0004, payload={})
    assert packed[0] & 0b11 == 3


def test_event_format_mode_allows_all_six_documented_modes():
    """§2.4: the «События» flag runs 0…6; the previous implementation capped it at 4."""
    spec = registry.find("KU", 0x0003)
    assert spec.field("event_format_mode").effective_max == 6


def test_dump_rejects_the_can_output_interface():
    """§9.7: «Значение бита 3, равное 1, отклоняется с кодом ERR_CONTENT»."""
    from detector_scenario_tool.protocol.packers import pack_message_payload

    packed = pack_message_payload(
        category="KU",
        msg_id=0x0006,
        payload={"selected_nand_bank": 1, "requested_packet_count": 1},
    )
    assert packed[0] & (1 << 3) == 0


def test_addresses_default_to_the_documented_values():
    """§1.5/§1.6: БВС КА = 05h, НА = 1Eh."""
    from detector_scenario_tool.transport_defaults import DEFAULT_BVS_ADDRESS, DEFAULT_NA_ADDRESS

    assert DEFAULT_BVS_ADDRESS == 0x05
    assert DEFAULT_NA_ADDRESS == 0x1E
