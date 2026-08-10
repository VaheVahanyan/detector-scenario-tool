"""Golden byte vectors, taken from the byte tables in Протокол_CAN_ГС_v2.

For short messages the protocol numbers content bytes from 2, because those are the CAN frame data
bytes that follow the 2-byte MSG_ID (UniCAN, SXC РЭ §1.4.4.3). The 6 bytes produced here are exactly
frame data bytes 2..7.
"""

from __future__ import annotations

import pytest

from detector_scenario_tool.protocol.catalog import ProtocolCatalog
from detector_scenario_tool.protocol.message_lengths import get_expected_message_length
from detector_scenario_tool.protocol.packers import (
    PackingError,
    pack_message_payload,
    payload_to_hex,
)

CATALOG = ProtocolCatalog()

# Payloads that satisfy every field the packers require without a default.
MINIMAL_PAYLOADS: dict[tuple[str, int], dict] = {
    ("KU", 0x0002): {"board_time_ms": 0, "board_time_s": 0},
}


def _minimal_payload(category: str, msg_id: int) -> dict:
    return dict(MINIMAL_PAYLOADS.get((category, msg_id), {}))


SENDABLE = [m for m in CATALOG.messages if m.category in ("KU", "KT")]
_ids = [f"{m.category}-0x{m.msg_id:04X}" for m in SENDABLE]


@pytest.mark.parametrize("message", SENDABLE, ids=_ids)
def test_packed_length_matches_declared_length(message):
    packed = pack_message_payload(
        category=message.category,
        msg_id=message.msg_id,
        payload=_minimal_payload(message.category, message.msg_id),
    )
    assert len(packed) == get_expected_message_length(message.category, message.msg_id)


@pytest.mark.parametrize(
    ("category", "msg_id", "payload", "expected_hex"),
    [
        # §2.1 / §2.2: content bytes 2-7 are all AAh.
        ("KU", 0x0000, {}, "AA AA AA AA AA AA"),
        ("KU", 0x0001, {}, "AA AA AA AA AA AA"),
        # §2.12 / §2.13.
        ("KU", 0x000B, {}, "AA AA AA AA AA AA"),
        ("KU", 0x000C, {}, "AA AA AA AA AA AA"),
        # §2.3: bytes 2-3 milliseconds, bytes 4-7 board time, little-endian.
        (
            "KU",
            0x0002,
            {"board_time_ms": 500, "board_time_s": 1_234_567},
            "F4 01 87 D6 12 00",
        ),
        # §2.4: hw config, observation params, trigger config, AAh.
        # bank=NAND1(1) | PED power(bit 2) -> 0x05
        # params: events=1 | Nmax=2<<3 | spectrum=1<<6 | Nhist=2<<8 | threshold=3<<12 = 0x3251
        (
            "KU",
            0x0003,
            {
                "selected_nand_bank": 1,
                "ped_power_enabled": 1,
                "event_format_mode": 1,
                "event_count_mode": 2,
                "spectrum_mode": 1,
                "histogram_cells": 2,
                "particle_threshold": 3,
                "trigger_config": 0xBEEF,
            },
            "05 51 32 EF BE AA",
        ),
        # §2.6: bank=NAND2(2) | NAND power(bit 2) | PED power(bit 3) -> 0x0E, then AAh filler.
        (
            "KU",
            0x0005,
            {
                "selected_nand_bank": 2,
                "nand_power_enabled": 1,
                "ped_power_enabled": 1,
            },
            "0E AA AA AA AA AA",
        ),
        # §2.7: bank=NAND1, USB output, fixed count 1000 as a 24-bit little-endian value.
        (
            "KU",
            0x0006,
            {
                "selected_nand_bank": 1,
                "output_type": 0,
                "requested_packet_count": 1000,
            },
            "01 E8 03 00 AA AA",
        ),
        # §2.9: bank=NAND2 | keep power after erase(bit 2) -> 0x06.
        (
            "KU",
            0x0008,
            {"selected_nand_bank": 2, "keep_power_after_erase": 1},
            "06 AA AA AA AA AA",
        ),
    ],
)
def test_golden_vectors(category, msg_id, payload, expected_hex):
    packed = pack_message_payload(category=category, msg_id=msg_id, payload=payload)
    assert payload_to_hex(packed) == expected_hex


def test_dump_transmits_the_requested_count_even_when_it_will_be_ignored():
    """§2.7 note 1: with output type 1 the НА *ignores* the count — it is not required to be 0.

    The tool therefore transmits what the user configured rather than silently rewriting the
    field, so the bytes on the wire match what the inspector shows.
    """
    packed = pack_message_payload(
        category="KU",
        msg_id=0x0006,
        payload={
            "selected_nand_bank": 1,
            "output_type": 1,
            "requested_packet_count": 1234,
        },
    )
    assert payload_to_hex(packed) == "11 D2 04 00 AA AA"


def test_dump_with_a_fixed_count_of_zero_is_flagged():
    """§9.7: «при типе вывода 0 количество пакетов не равно 0»."""
    from detector_scenario_tool.protocol import registry
    from detector_scenario_tool.protocol.fields import validate_payload

    spec = registry.find("KU", 0x0006)
    issues = validate_payload(
        spec, {"selected_nand_bank": 1, "output_type": 0, "requested_packet_count": 0}
    )
    assert [i.code for i in issues] == ["dump.count_required"]


def test_invalid_bank_is_rejected():
    with pytest.raises(PackingError):
        pack_message_payload(
            category="KU", msg_id=0x0008, payload={"selected_nand_bank": 3}
        )


def test_out_of_range_field_is_rejected():
    with pytest.raises(PackingError):
        pack_message_payload(
            category="KU",
            msg_id=0x0002,
            payload={"board_time_ms": 70_000, "board_time_s": 0},
        )


def test_telemetry_messages_are_not_packable():
    """ТС/TM are received, never sent by the tool."""
    with pytest.raises(PackingError):
        pack_message_payload(category="TS", msg_id=0x0200, payload={})
