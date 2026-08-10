"""UniCAN framing, against SXC Орбикрафт-Про РЭ §1.4.4.

This is the layer with no hardware and no Qt, so it carries the heaviest test load: everything the
live transport does on the wire is decided here.
"""

from __future__ import annotations

import pytest

from detector_scenario_tool.protocol.errors import UniCanBusError
from detector_scenario_tool.transport.unican import (
    ERROR_ID,
    LONG_START_ID,
    MAX_SHORT_PAYLOAD,
    CanFrame,
    Reassembler,
    UniCanDecodeError,
    UniCanError,
    UniCanErrorFrame,
    UniCanMessage,
    crc16_xmodem,
    decode_can_id,
    encode,
    encode_can_id,
    encode_error,
    max_address,
)

BVS = 0x05
NA = 0x1E


class TestCrc:
    def test_known_check_value(self):
        """CRC-16/XMODEM of "123456789" is 0x31C3."""
        assert crc16_xmodem(b"123456789") == 0x31C3

    def test_empty_input(self):
        assert crc16_xmodem(b"") == 0x0000

    def test_is_order_sensitive(self):
        assert crc16_xmodem(b"\x01\x02") != crc16_xmodem(b"\x02\x01")


class TestIdentifier:
    @pytest.mark.parametrize("extended", [False, True])
    @pytest.mark.parametrize("data_bit", [False, True])
    def test_round_trip(self, extended, data_bit):
        can_id = encode_can_id(NA, BVS, data_bit=data_bit, extended=extended)
        assert decode_can_id(can_id, extended) == (NA, BVS, data_bit)

    def test_standard_layout_matches_the_document(self):
        """bit 10 = Д, bits 9-5 sender, bits 4-0 receiver."""
        can_id = encode_can_id(destination=0x1E, source=0x05, data_bit=False, extended=False)
        assert can_id == (0x05 << 5) | 0x1E
        assert can_id.bit_length() <= 11

    def test_extended_layout_matches_the_document(self):
        """bit 28 = Д, bits 27-14 sender, bits 13-0 receiver."""
        can_id = encode_can_id(destination=0x1E, source=0x05, data_bit=True, extended=True)
        assert can_id == (1 << 28) | (0x05 << 14) | 0x1E
        assert can_id.bit_length() <= 29

    def test_data_bit_is_the_top_bit(self):
        plain = encode_can_id(NA, BVS, data_bit=False, extended=False)
        data = encode_can_id(NA, BVS, data_bit=True, extended=False)
        assert data - plain == 1 << 10

    def test_address_limits(self):
        assert max_address(extended=False) == 31
        assert max_address(extended=True) == 16383

    def test_address_out_of_range_is_rejected(self):
        with pytest.raises(UniCanError, match="does not fit"):
            encode_can_id(destination=32, source=BVS, data_bit=False, extended=False)

    def test_the_documented_defaults_fit_a_standard_identifier(self):
        """БВС 05h and НА 1Eh both fit the 5-bit field, so standard frames suffice."""
        assert BVS <= max_address(extended=False)
        assert NA <= max_address(extended=False)


class TestShortMessages:
    def test_one_frame_with_msg_id_then_payload(self):
        frames = encode(0x0001, b"\xaa" * 6, destination=NA, source=BVS)
        assert len(frames) == 1
        assert frames[0].data == b"\x01\x00" + b"\xaa" * 6
        assert frames[0].dlc == 8

    def test_msg_id_is_little_endian(self):
        frames = encode(0x0A61, b"", destination=NA, source=BVS)
        assert frames[0].data[:2] == b"\x61\x0a"

    def test_dlc_is_payload_plus_two(self):
        frames = encode(0x0002, b"\x01\x02\x03", destination=NA, source=BVS)
        assert frames[0].dlc == 5

    def test_six_bytes_is_still_short(self):
        frames = encode(0x0002, bytes(MAX_SHORT_PAYLOAD), destination=NA, source=BVS)
        assert len(frames) == 1

    def test_seven_bytes_becomes_long(self):
        frames = encode(0x0002, bytes(MAX_SHORT_PAYLOAD + 1), destination=NA, source=BVS)
        assert len(frames) > 1

    def test_data_bit_is_clear(self):
        frames = encode(0x0001, b"", destination=NA, source=BVS)
        assert decode_can_id(frames[0].can_id, extended=False)[2] is False


class TestLongMessages:
    def test_set_cfg_worked_example(self):
        """CMD_SET_CFG is 66 bytes: Length = 68, one start frame plus nine data frames."""
        frames = encode(0x0007, bytes(66), destination=NA, source=BVS)

        assert len(frames) == 1 + 9
        start = frames[0]
        assert start.data[:2] == LONG_START_ID.to_bytes(2, "little")
        assert int.from_bytes(start.data[2:4], "little") == 0x0007
        assert int.from_bytes(start.data[4:6], "little") == 68
        assert start.dlc == 6

        assert sum(f.dlc for f in frames[1:]) == 68
        assert [f.dlc for f in frames[1:]] == [8] * 8 + [4]

    def test_length_counts_the_crc(self):
        payload = bytes(range(20))
        frames = encode(0x0007, payload, destination=NA, source=BVS)
        assert int.from_bytes(frames[0].data[4:6], "little") == len(payload) + 2

    def test_data_frames_carry_the_data_bit(self):
        frames = encode(0x0007, bytes(66), destination=NA, source=BVS)
        assert decode_can_id(frames[0].can_id, extended=False)[2] is False
        for frame in frames[1:]:
            assert decode_can_id(frame.can_id, extended=False)[2] is True

    def test_crc_is_appended_over_the_payload_only(self):
        payload = bytes(range(10))
        frames = encode(0x0007, payload, destination=NA, source=BVS)
        body = b"".join(f.data for f in frames[1:])
        assert body[:-2] == payload
        assert int.from_bytes(body[-2:], "little") == crc16_xmodem(payload)

    def test_the_largest_message_in_the_protocol(self):
        """ТС «Результаты теста ППЗУ» is 6146 bytes."""
        frames = encode(0x0007, bytes(6146), destination=NA, source=BVS)
        assert int.from_bytes(frames[0].data[4:6], "little") == 6148
        assert sum(f.dlc for f in frames[1:]) == 6148


class TestReservedIdentifiers:
    @pytest.mark.parametrize("msg_id", [0xFF00, LONG_START_ID, ERROR_ID])
    def test_service_identifiers_are_refused(self, msg_id):
        with pytest.raises(UniCanError, match="reserved"):
            encode(msg_id, b"", destination=NA, source=BVS)

    def test_the_highest_protocol_id_is_still_allowed(self):
        """TLM_MAGFIELD is F221h, just below the reserved range."""
        assert encode(0xF221, bytes(76), destination=NA, source=BVS)

    def test_non_16_bit_id_is_refused(self):
        with pytest.raises(UniCanError, match="16-bit"):
            encode(0x1_0000, b"", destination=NA, source=BVS)


class TestReassembly:
    @pytest.mark.parametrize("size", [0, 1, 6, 7, 8, 66, 125, 6146])
    def test_round_trip(self, size):
        payload = bytes((i * 7) & 0xFF for i in range(size))
        frames = encode(0x0007 if size > 6 else 0x0002, payload, destination=NA, source=BVS)

        reassembler = Reassembler()
        results = [reassembler.feed(frame) for frame in frames]
        message = results[-1]

        assert isinstance(message, UniCanMessage)
        assert message.payload == payload
        assert message.source == BVS
        assert message.destination == NA
        assert message.is_long == (size > 6)
        assert all(r is None for r in results[:-1])

    @pytest.mark.parametrize("extended", [False, True])
    def test_round_trip_with_either_identifier_width(self, extended):
        frames = encode(0x0007, bytes(20), destination=NA, source=BVS, extended=extended)
        reassembler = Reassembler(extended=extended)
        result = [reassembler.feed(f) for f in frames][-1]
        assert isinstance(result, UniCanMessage)

    def test_corrupted_payload_is_caught_by_the_crc(self):
        frames = encode(0x0007, bytes(range(20)), destination=NA, source=BVS)
        broken = list(frames)
        broken[2] = CanFrame(broken[2].can_id, bytes([0xFF]) + broken[2].data[1:])

        reassembler = Reassembler()
        result = [reassembler.feed(f) for f in broken][-1]

        assert isinstance(result, UniCanDecodeError)
        assert result.code is UniCanBusError.CRC_ERROR

    def test_data_without_a_start_is_reported(self):
        frames = encode(0x0007, bytes(20), destination=NA, source=BVS)
        reassembler = Reassembler()

        result = reassembler.feed(frames[1])

        assert isinstance(result, UniCanDecodeError)
        assert result.code is UniCanBusError.DATA_WITHOUT_START

    def test_a_second_start_interrupts_the_first(self):
        frames = encode(0x0007, bytes(20), destination=NA, source=BVS)
        reassembler = Reassembler()
        reassembler.feed(frames[0])
        reassembler.feed(frames[1])

        result = reassembler.feed(frames[0])

        assert isinstance(result, UniCanDecodeError)
        assert result.code is UniCanBusError.START_BEFORE_PREVIOUS_FINISHED

    def test_a_restarted_transfer_still_completes(self):
        frames = encode(0x0007, bytes(range(20)), destination=NA, source=BVS)
        reassembler = Reassembler()
        reassembler.feed(frames[0])
        reassembler.feed(frames[1])

        results = [reassembler.feed(f) for f in frames]

        assert isinstance(results[-1], UniCanMessage)
        assert results[-1].payload == bytes(range(20))

    def test_transfers_from_two_sources_do_not_mix(self):
        payload_a = bytes(range(20))
        payload_b = bytes(range(100, 120))
        frames_a = encode(0x0007, payload_a, destination=NA, source=BVS)
        frames_b = encode(0x0007, payload_b, destination=NA, source=0x09)

        reassembler = Reassembler()
        results = []
        for a, b in zip(frames_a, frames_b):
            results.append(reassembler.feed(a))
            results.append(reassembler.feed(b))

        messages = [r for r in results if isinstance(r, UniCanMessage)]
        assert {m.source for m in messages} == {BVS, 0x09}
        assert {m.payload for m in messages} == {payload_a, payload_b}

    def test_short_command_frame_is_rejected(self):
        frame = CanFrame(encode_can_id(NA, BVS, False, False), b"\x01")
        result = Reassembler().feed(frame)

        assert isinstance(result, UniCanDecodeError)
        assert result.code is UniCanBusError.COMMAND_TOO_SHORT

    def test_truncated_start_frame_is_rejected(self):
        frame = CanFrame(
            encode_can_id(NA, BVS, False, False), LONG_START_ID.to_bytes(2, "little") + b"\x07"
        )
        result = Reassembler().feed(frame)

        assert isinstance(result, UniCanDecodeError)
        assert result.code is UniCanBusError.START_COMMAND_TOO_SHORT

    def test_reset_drops_partial_transfers(self):
        frames = encode(0x0007, bytes(20), destination=NA, source=BVS)
        reassembler = Reassembler()
        reassembler.feed(frames[0])
        reassembler.reset()

        result = reassembler.feed(frames[1])
        assert isinstance(result, UniCanDecodeError)
        assert result.code is UniCanBusError.DATA_WITHOUT_START


class TestErrorFrames:
    @pytest.mark.parametrize("code", list(UniCanBusError))
    def test_every_documented_code_round_trips(self, code):
        frame = encode_error(0x0007, code, destination=BVS, source=NA)
        result = Reassembler().feed(frame)

        assert isinstance(result, UniCanErrorFrame)
        assert result.failed_msg_id == 0x0007
        assert result.known_code is code

    def test_an_unknown_code_is_still_reported(self):
        frame = encode_error(0x0007, 0x00FF, destination=BVS, source=NA)
        result = Reassembler().feed(frame)

        assert isinstance(result, UniCanErrorFrame)
        assert result.code == 0x00FF
        assert result.known_code is None

    def test_error_frames_are_not_confused_with_messages(self):
        frame = encode_error(0x0001, UniCanBusError.CRC_ERROR, destination=BVS, source=NA)
        assert not isinstance(Reassembler().feed(frame), UniCanMessage)
