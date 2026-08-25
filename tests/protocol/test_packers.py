"""Golden byte vectors, taken from the byte tables in Протокол_CAN_ГС_v2_1_Спутникс.

For short messages the protocol numbers content bytes from 2, because those are the CAN frame data
bytes that follow the 2-byte MSG_ID (UniCAN, SXC РЭ §1.4.4.3). The bytes produced here are exactly
frame data bytes 2 onwards.

Every vector below changed in v2.1: the previous revision declared each short command as six bytes
padded with `AAh`, and v2.1 gives the true content length instead. The expectations are re-derived
from the §2 tables rather than adjusted from the old ones, because "the old value minus the
padding" would silently reproduce any mistake the old values already contained.
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
from message_ids import (
    DUMP,
    DUTY,
    ERASE,
    GET_VERSION,
    OBSERVE_START,
    RESET_ALARM,
    SET_DEST_ID,
    SET_DEVICE_ID,
    SET_TIME,
    SHUTDOWN,
    STATUS_REQ,
    TELEM_REQ,
    TM_STATUS,
)

CATALOG = ProtocolCatalog()

# Payloads that satisfy every field the packers require without a default.
MINIMAL_PAYLOADS: dict[tuple[str, int], dict] = {
    ("KU", SET_TIME): {"board_time_ms": 0, "board_time_s": 0},
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
        # §2.1 / §2.2 / §2.12 / §2.13: the length column says 0 — these carry no content at all.
        ("KU", TELEM_REQ, {}, ""),
        ("KU", STATUS_REQ, {}, ""),
        ("KU", SHUTDOWN, {}, ""),
        ("KU", RESET_ALARM, {}, ""),
        # КУ 17, new in v2.1: also contentless.
        ("KU", GET_VERSION, {}, ""),
        # §2.3: bytes 2-3 milliseconds, bytes 4-7 board time, little-endian. Six bytes in both
        # revisions — the one short command whose length did not change.
        (
            "KU",
            SET_TIME,
            {"board_time_ms": 500, "board_time_s": 1_234_567},
            "F4 01 87 D6 12 00",
        ),
        # §2.4, five bytes: hw config, observation params, trigger config.
        # bank=NAND1(1) | PED power(bit 2) -> 0x05
        # params: events=1 | Nmax=2<<3 | spectrum=1<<6 | Nhist=2<<8 | threshold=3<<12 = 0x3251
        (
            "KU",
            OBSERVE_START,
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
            "05 51 32 EF BE",
        ),
        # §2.6, one byte: bank=NAND2(2) | NAND power(bit 2) | PED power(bit 3) -> 0x0E.
        (
            "KU",
            DUTY,
            {
                "selected_nand_bank": 2,
                "nand_power_enabled": 1,
                "ped_power_enabled": 1,
            },
            "0E",
        ),
        # §2.7, four bytes: bank=NAND1, USB output, fixed count 1000 as 24-bit little-endian.
        (
            "KU",
            DUMP,
            {
                "selected_nand_bank": 1,
                "output_interface": 0,
                "output_type": 0,
                "requested_packet_count": 1000,
            },
            "01 E8 03 00",
        ),
        # §2.7 again, with the CAN interface selected: bit 3 -> 0x09. The firmware answers
        # ERR_CONTENT, but the bit must reach the wire for that to be observable.
        (
            "KU",
            DUMP,
            {
                "selected_nand_bank": 1,
                "output_interface": 1,
                "output_type": 0,
                "requested_packet_count": 1000,
            },
            "09 E8 03 00",
        ),
        # §2.9, one byte: bank=NAND2 | keep power after erase(bit 2) -> 0x06.
        ("KU", ERASE, {"selected_nand_bank": 2, "keep_power_after_erase": 1}, "06"),
        # §2.15 / §2.16, two bytes: the addresses are uint16_t in v2.1, little-endian.
        ("KU", SET_DEST_ID, {"destination_id": 0x0005}, "05 00"),
        ("KU", SET_DEVICE_ID, {"device_id": 0x001E}, "1E 00"),
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
        msg_id=DUMP,
        payload={
            "selected_nand_bank": 1,
            "output_type": 1,
            "requested_packet_count": 1234,
        },
    )
    assert payload_to_hex(packed) == "11 D2 04 00"


def test_dump_with_a_fixed_count_of_zero_is_flagged():
    """§9.7: «при типе вывода 0 количество пакетов не равно 0»."""
    from detector_scenario_tool.protocol import registry
    from detector_scenario_tool.protocol.fields import validate_payload

    spec = registry.find("KU", DUMP)
    issues = validate_payload(
        spec, {"selected_nand_bank": 1, "output_type": 0, "requested_packet_count": 0}
    )
    assert [i.code for i in issues] == ["dump.count_required"]


def test_invalid_bank_is_rejected():
    with pytest.raises(PackingError):
        pack_message_payload(
            category="KU", msg_id=ERASE, payload={"selected_nand_bank": 3}
        )


def test_out_of_range_field_is_rejected():
    with pytest.raises(PackingError):
        pack_message_payload(
            category="KU",
            msg_id=SET_TIME,
            payload={"board_time_ms": 70_000, "board_time_s": 0},
        )


def test_telemetry_messages_are_not_packable():
    """ТС/TM are received, never sent by the tool."""
    with pytest.raises(PackingError):
        pack_message_payload(category="TS", msg_id=TM_STATUS, payload={})
