"""Conformance with `Протокол_CAN_ГС_v2_1_Спутникс`.

The previous revision of this file (`test_protocol_v2_deltas.py`) guarded the v2 tables. v2.1
renumbered every message and gave the short control commands their true content lengths, so it was
rewritten rather than extended — the old identifiers must not resolve at all any more, and there is
a test below that says so.

Everything here is read straight off the specification's tables. When a value disagrees with the
code, the specification wins.
"""

from __future__ import annotations

import pytest

from detector_scenario_tool.protocol import registry
from detector_scenario_tool.protocol.catalog import ProtocolCatalog
from detector_scenario_tool.protocol.fields import AckBehaviour
from detector_scenario_tool.protocol.message_lengths import get_expected_message_length

pytestmark = pytest.mark.protocol_v2

CATALOG = ProtocolCatalog()

#: §2 — the seventeen control commands, in the document's own order.
CONTROL_COMMANDS = [
    (0x0F00, "CMD_TELEM_REQ", 0),
    (0x0F01, "CMD_STATUS_REQ", 0),
    (0x0F02, "CMD_SET_TIME", 6),
    (0x0F03, "CMD_OBSERVE_START", 5),
    (0x0F04, "CMD_OBSERVE_CTRL", 5),
    (0x0F05, "CMD_DUTY", 1),
    (0x0F06, "CMD_DUMP", 4),
    (0x0F07, "CMD_SET_CFG", 68),
    (0x0F08, "CMD_ERASE", 1),
    (0x0F09, "CMD_TEST", 1),
    (0x0F0A, "CMD_TEST_RESULT", 1),
    (0x0F0B, "CMD_SHUTDOWN", 0),
    (0x0F0C, "CMD_RESET_ALARM", 0),
    (0x0401, "CMD_SET_TIME_BVS", 5),
    (0x0A61, "CMD_SET_DEST_ID", 2),
    (0x0A62, "CMD_SET_DEVICE_ID", 2),
    (0xFFE0, "CMD_GET_VERSION", 0),
]

#: §3 — the three telemetry commands.
TELEMETRY_COMMANDS = [
    (0xF210, "TLM_TIME_ORBIT_ATT", 125, "05h"),
    (0xF221, "TLM_MAGFIELD", 76, "06h"),
    (0x0E00, "TLM_MCILWAIN", 24, "07h"),
]

#: §4 — the five telemetry messages.
TELEMETRY_MESSAGES = [
    (0x0D00, "TM_STATUS", 6),
    (0x0D01, "TM_ACK", 6),
    (0x0D02, "TM_TELEMETRY", 109),
    (0x0D03, "TM_TEST_RESULT", 6146),
    (0xFFE1, "TM_VERSION", 3),
]


class TestRenumbering:
    @pytest.mark.parametrize(("msg_id", "symbol", "length"), CONTROL_COMMANDS)
    def test_control_commands(self, msg_id, symbol, length):
        spec = registry.find("KU", msg_id)
        assert spec is not None, f"{symbol} is missing"
        assert spec.symbol == symbol
        assert spec.length == length

    @pytest.mark.parametrize(("msg_id", "symbol", "length", "ni_format"), TELEMETRY_COMMANDS)
    def test_telemetry_commands(self, msg_id, symbol, length, ni_format):
        spec = registry.find("KT", msg_id)
        assert spec is not None, f"{symbol} is missing"
        assert spec.symbol == symbol
        assert spec.length == length
        assert ni_format in spec.doc_ref

    @pytest.mark.parametrize(("msg_id", "symbol", "length"), TELEMETRY_MESSAGES)
    def test_telemetry_messages(self, msg_id, symbol, length):
        spec = registry.find("TS", msg_id)
        assert spec is not None, f"{symbol} is missing"
        assert spec.symbol == symbol
        assert spec.length == length

    def test_the_counts_match_the_document(self):
        assert len(registry.by_category("KU")) == 17
        assert len(registry.by_category("KT")) == 3
        assert len(registry.by_category("TS")) == 5

    @pytest.mark.parametrize(
        ("category", "msg_id"),
        # Every identifier v2 used that v2.1 reassigned or dropped.
        [("KU", i) for i in range(0x0000, 0x000D)]
        + [("KT", 0x0100)]
        + [("TS", i) for i in range(0x0200, 0x0204)],
    )
    def test_no_v2_identifier_survives(self, category, msg_id):
        """A half-finished renumbering would leave a stale definition answering the old number."""
        assert registry.find(category, msg_id) is None


class TestUnpadded:
    """v2 declared every short КУ as six `AAh`-padded bytes; v2.1 gives the true lengths."""

    @pytest.mark.parametrize(
        ("msg_id", "symbol"),
        [(0x0F00, "CMD_TELEM_REQ"), (0x0F01, "CMD_STATUS_REQ"),
         (0x0F0B, "CMD_SHUTDOWN"), (0x0F0C, "CMD_RESET_ALARM")],
    )
    def test_a_contentless_command_packs_to_nothing(self, msg_id, symbol):
        from detector_scenario_tool.protocol.packers import pack_message_payload

        assert pack_message_payload(category="KU", msg_id=msg_id, payload={}) == b""

    def test_a_one_byte_command_packs_to_one_byte(self):
        from detector_scenario_tool.protocol.packers import pack_message_payload

        packed = pack_message_payload(
            category="KU", msg_id=0x0F08, payload={"selected_nand_bank": 1}
        )
        assert packed == bytes([0x01])

    def test_nothing_is_padded_to_six_any_more(self):
        for spec in registry.by_category("KU"):
            if spec.length in (0, 6):
                continue
            assert spec.length == sum(
                f.byte_length for f in _top_level_fields(spec)
            ), spec.symbol


class TestContentChanges:
    def test_set_cfg_splits_the_initial_rtc(self):
        """§2.8: bytes 42-43 milliseconds, 44-47 seconds — v2 had a bare u32 at 42."""
        spec = registry.find("KU", 0x0F07)
        ms = spec.field("initial_rtc_ms")
        seconds = spec.field("initial_rtc_s")

        assert (ms.byte_offset, ms.byte_length) == (42, 2)
        assert (seconds.byte_offset, seconds.byte_length) == (44, 4)
        assert spec.field("initial_rtc") is None, "the v2 field must be gone, not merely renamed"

    @pytest.mark.parametrize(
        ("key", "offset"),
        [
            ("session_id", 48),
            ("nand1_packet_count", 50),
            ("nand2_packet_count", 53),
            ("nand1_erase_count", 56),
            ("nand2_erase_count", 58),
            ("nand1_test_count", 60),
            ("nand2_test_count", 62),
            ("alarm_mask", 64),
        ],
    )
    def test_set_cfg_tail_shifted_by_two(self, key, offset):
        assert registry.find("KU", 0x0F07).field(key).byte_offset == offset

    def test_address_commands_carry_a_16_bit_identifier(self):
        """§2.15/§2.16: bytes 2-3, uint16_t — v2 had a single byte plus XXh filler."""
        dest = registry.find("KU", 0x0A61).field("destination_id")
        device = registry.find("KU", 0x0A62).field("device_id")

        assert (dest.byte_offset, dest.byte_length) == (0, 2)
        assert (device.byte_offset, device.byte_length) == (0, 2)

    def test_the_destination_defaults_to_the_bvs_not_to_the_payload(self):
        """§1.5/§1.6: the НА replies *to* the БВС (0005h); 001Eh is the НА's own address."""
        from detector_scenario_tool.transport_defaults import (
            DEFAULT_BVS_ADDRESS,
            DEFAULT_NA_ADDRESS,
        )

        assert registry.find("KU", 0x0A61).field("destination_id").default == DEFAULT_BVS_ADDRESS
        assert registry.find("KU", 0x0A62).field("device_id").default == DEFAULT_NA_ADDRESS

    def test_bvs_time_preset_has_no_trailing_filler(self):
        """§2.14: bytes 2-5 time32_t, byte 6 accuracy — five bytes, nothing after."""
        spec = registry.find("KU", 0x0401)
        assert spec.length == 5
        assert spec.field("posix_time").byte_offset == 0
        assert spec.field("time_source_accuracy").byte_offset == 4


class TestTelemetryMessageGrowth:
    """§4.3 — «Телеметрия» went 100 → 109 through four independent changes."""

    def test_the_current_rtc_is_split(self):
        spec = registry.find("TS", 0x0D02)
        assert (spec.field("rtc_ms").byte_offset, spec.field("rtc_ms").byte_length) == (0, 2)
        assert (spec.field("rtc_s").byte_offset, spec.field("rtc_s").byte_length) == (2, 4)

    def test_the_initial_rtc_is_split(self):
        spec = registry.find("TS", 0x0D02)
        assert spec.field("initial_rtc_ms").byte_offset == 76
        assert spec.field("initial_rtc_s").byte_offset == 78

    def test_the_addresses_are_16_bit(self):
        spec = registry.find("TS", 0x0D02)
        for key, offset in (("destination_id", 102), ("device_id", 104)):
            assert (spec.field(key).byte_offset, spec.field(key).byte_length) == (offset, 2)

    def test_the_software_version_is_appended(self):
        spec = registry.find("TS", 0x0D02)
        assert spec.field("sw_major").byte_offset == 106
        assert spec.field("sw_minor").byte_offset == 107
        assert spec.field("sw_extra").byte_offset == 108


class TestNewMessages:
    def test_the_version_query_is_allowed_everywhere(self):
        """§5.2.10 row 17: «+» in all seven modes."""
        from detector_scenario_tool.protocol.modes import OPERATIONAL_MODES

        spec = registry.find("KU", 0xFFE0)
        assert set(spec.allowed_modes) == set(OPERATIONAL_MODES)

    def test_the_version_query_expects_an_ack_and_the_version(self):
        spec = registry.find("KU", 0xFFE0)
        expected = {(r.category, r.msg_id) for r in spec.follow_up}
        assert expected == {("TS", 0x0D01), ("TS", 0xFFE1)}

    def test_the_version_reply_carries_three_bytes(self):
        spec = registry.find("TS", 0xFFE1)
        assert [f.key for f in spec.fields] == ["sw_major", "sw_minor", "sw_extra"]
        assert spec.length == 3

    def test_the_reserved_band_no_longer_blocks_them(self):
        """C1: the НА accepts FFE0h/FFE1h; only FFFEh/FFFFh break the framing."""
        from detector_scenario_tool.transport.unican import encode

        assert len(encode(0xFFE0, b"", destination=0x1E, source=0x05)) == 1
        assert len(encode(0xFFE1, bytes(3), destination=0x05, source=0x1E)) == 1


class TestDumpInterface:
    """C3 — bit 3 becomes a real selector, defaulting to USB."""

    def test_the_interface_is_selectable(self):
        field = registry.find("KU", 0x0F06).field("output_interface")
        assert field is not None
        assert field.editable
        assert (field.bit_offset, field.bit_length) == (3, 1)

    def test_it_defaults_to_usb(self):
        from detector_scenario_tool.protocol.packers import pack_message_payload

        packed = pack_message_payload(
            category="KU", msg_id=0x0F06,
            payload=registry.find("KU", 0x0F06).default_payload(),
        )
        assert packed[0] & (1 << 3) == 0

    def test_choosing_can_is_transmitted_not_silently_dropped(self):
        from detector_scenario_tool.protocol.packers import pack_message_payload

        packed = pack_message_payload(
            category="KU", msg_id=0x0F06,
            payload={"selected_nand_bank": 1, "output_interface": 1,
                     "requested_packet_count": 1},
        )
        assert packed[0] & (1 << 3) != 0


class TestUnchangedFromV2:
    """Verified cell by cell against v2.1; these must survive the renumbering untouched."""

    def test_only_the_bvs_time_preset_may_go_unacknowledged(self):
        suppressible = [
            spec.symbol
            for spec in registry.by_category("KU")
            if spec.ack is AckBehaviour.ACK_MAY_BE_SUPPRESSED
        ]
        assert suppressible == ["CMD_SET_TIME_BVS"]

    def test_telemetry_commands_get_no_acknowledgement(self):
        """§5.1.2: «На КТ ... НА не выдает ТС «Квитанция»»."""
        for spec in registry.by_category("KT"):
            assert spec.ack is AckBehaviour.NONE
            assert not any(r.is_ack for r in spec.follow_up), spec.symbol

    def test_all_telemetry_commands_are_long(self):
        assert all(spec.is_long for spec in registry.by_category("KT"))

    @pytest.mark.parametrize(
        ("msg_id", "modes"),
        [
            (0x0F00, {"duty", "observe", "alarm"}),
            (0x0F04, {"observe"}),
            (0x0F05, {"duty", "erase", "test", "observe", "dump"}),
            (0x0F07, {"duty", "alarm"}),
            (0x0F0C, {"alarm"}),
            (0x0F08, {"duty"}),
        ],
    )
    def test_the_mode_matrix_is_unchanged(self, msg_id, modes):
        """§5.2.10 — identical to v2 for commands 1-16."""
        spec = registry.find("KU", msg_id)
        assert {mode.value for mode in spec.allowed_modes} == modes

    def test_observe_ctrl_still_pins_the_bank_selector_to_three(self):
        from detector_scenario_tool.protocol.packers import pack_message_payload

        assert pack_message_payload(category="KU", msg_id=0x0F04, payload={})[0] & 0b11 == 3

    def test_observe_ctrl_still_carries_the_registration_threshold(self):
        threshold = registry.find("KU", 0x0F04).field("particle_threshold")
        assert (threshold.bit_offset, threshold.bit_length) == (12, 4)

    def test_event_format_mode_still_allows_six_modes(self):
        assert registry.find("KU", 0x0F03).field("event_format_mode").effective_max == 6

    def test_the_test_result_request_still_packs_the_mram_bank(self):
        from detector_scenario_tool.protocol.packers import pack_message_payload

        packed = pack_message_payload(
            category="KU", msg_id=0x0F0A,
            payload={"selected_nand_bank": 2, "selected_mram_bank": 2},
        )
        assert packed[0] == 0x0A

    def test_addresses_default_to_the_documented_values(self):
        from detector_scenario_tool.transport_defaults import (
            DEFAULT_BVS_ADDRESS,
            DEFAULT_NA_ADDRESS,
        )

        assert (DEFAULT_BVS_ADDRESS, DEFAULT_NA_ADDRESS) == (0x05, 0x1E)


def _top_level_fields(spec):
    """One entry per distinct (offset, width), so bit fields sharing a byte count once."""
    seen = {}
    for field in spec.fields:
        seen[(field.byte_offset, field.byte_length)] = field
    return seen.values()
