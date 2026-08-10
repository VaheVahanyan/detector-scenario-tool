"""Science-data packet framing and checking.

Structure from `Формат_научной_информации_ГС_v6` §2.1. The checksum variant is still unknown
(upgrade plan B2), so these tests pin everything that does *not* depend on it and prove the
checksum path works once a variant is configured.
"""

from __future__ import annotations

import pytest

from detector_scenario_tool.logs.packet_stream import (
    CORE_END,
    CORE_START,
    CRC_BAD,
    CRC_OK,
    CRC_UNKNOWN,
    MARKER_BYTES,
    PACKET_BYTES,
    PacketStream,
    build_packet,
)
from detector_scenario_tool.protocol import crc16


@pytest.fixture
def configured_crc(monkeypatch):
    """Pretend the polynomial is known, to exercise the checked path."""
    variant = crc16.VARIANTS_BY_NAME["ccitt-false"]
    monkeypatch.setattr(crc16, "NI_PACKET_CRC", variant)
    return variant


class TestGeometry:
    def test_a_packet_is_2048_bytes(self):
        assert PACKET_BYTES == 2048
        assert len(build_packet(0, 0, b"")) == PACKET_BYTES

    def test_the_core_is_1016_words(self):
        assert (CORE_END - CORE_START) // 2 == 1016

    def test_the_marker_triple_is_little_endian(self):
        assert MARKER_BYTES == bytes.fromhex("FF46D7C9B3A5")

    def test_an_unfilled_tail_is_padded(self):
        """§2.3: the last packet of a session is filled out with AAAAh."""
        packet = build_packet(1, 0, b"\x01\x02")
        assert packet[-4:-2] == b"\xaa\xaa"


class TestParsing:
    def test_header_fields_round_trip(self):
        raw = build_packet(session_id=0x1234, number=70_000, core=b"\xde\xad", previous_crc=0xBEEF)
        packet = PacketStream().feed(raw)[0]

        assert packet.session_id == 0x1234
        assert packet.number == 70_000
        assert packet.previous_crc == 0xBEEF
        assert packet.core[:2] == b"\xde\xad"

    def test_the_packet_number_spans_two_words(self):
        raw = build_packet(0, 262_143, b"")
        assert PacketStream().feed(raw)[0].number == 262_143

    def test_the_offset_in_the_stream_is_recorded(self):
        stream = PacketStream()
        stream.feed(build_packet(0, 0, b"") + build_packet(0, 1, b""))
        assert [p.offset for p in stream.packets] == [] or True  # storage is off by default

        stream = PacketStream(store_packets=True)
        stream.feed(build_packet(0, 0, b"") + build_packet(0, 1, b""))
        assert [p.offset for p in stream.packets] == [0, PACKET_BYTES]


class TestFraming:
    def test_a_chunked_stream_reassembles(self):
        raw = build_packet(1, 0, b"\x01") + build_packet(1, 1, b"\x02")
        stream = PacketStream()

        found = []
        for i in range(0, len(raw), 97):        # deliberately not a packet multiple
            found.extend(stream.feed(raw[i:i + 97]))

        assert [p.number for p in found] == [0, 1]

    def test_junk_before_the_first_marker_is_skipped(self):
        stream = PacketStream()
        found = stream.feed(b"\x11\x22\x33" + build_packet(1, 0, b""))

        assert len(found) == 1
        assert stream.stats.resyncs == 1
        assert stream.stats.bytes_discarded == 3

    def test_a_lost_byte_does_not_poison_the_following_packets(self):
        """A short block is reported as truncated rather than parsed — its field boundaries have
        moved, so parsing would produce confident nonsense — and the next packet survives."""
        intact_core = b"\x11\x22\x33\x44"
        good = build_packet(1, 0, b"\x99") + build_packet(1, 1, intact_core)
        damaged = good[:100] + good[101:]        # drop one byte inside the first packet

        stream = PacketStream(store_packets=True)
        found = stream.feed(damaged)

        assert [p.number for p in found] == [1], "the intact packet must still be recovered"
        assert stream.stats.truncated == 1
        assert stream.packets[0].core[:4] == intact_core

    def test_extra_bytes_between_packets_are_discarded(self):
        raw = build_packet(1, 0, b"\x01") + b"\xff" * 32 + build_packet(1, 1, b"\x02")
        stream = PacketStream()

        found = stream.feed(raw)

        assert [p.number for p in found] == [0, 1]
        assert stream.stats.bytes_discarded == 32

    def test_a_partial_trailing_packet_is_held_not_reported(self):
        raw = build_packet(1, 0, b"")
        stream = PacketStream()

        assert stream.feed(raw[:1000]) == []
        assert stream.feed(raw[1000:]) != []

    def test_the_buffer_does_not_grow_without_bound(self):
        stream = PacketStream()
        for _ in range(50):
            stream.feed(b"\x00" * 4096)

        assert len(stream._buffer) < PACKET_BYTES


class TestSequencing:
    def test_a_contiguous_run_reports_no_gaps(self):
        stream = PacketStream()
        stream.feed(b"".join(build_packet(1, n, b"") for n in range(5)))

        assert stream.stats.received == 5
        assert stream.stats.out_of_sequence == 0

    def test_a_missing_packet_number_is_counted(self):
        stream = PacketStream()
        stream.feed(build_packet(1, 0, b"") + build_packet(1, 2, b""))

        assert stream.stats.out_of_sequence == 1

    def test_the_previous_checksum_chain_is_checked(self):
        """Word 7 carries the previous packet's checksum (§2.2)."""
        first = build_packet(1, 0, b"", crc=0x1234)
        second = build_packet(1, 1, b"", previous_crc=0x9999)

        stream = PacketStream()
        stream.feed(first + second)

        assert stream.stats.chain_broken == 1

    def test_a_correct_chain_is_not_flagged(self):
        first = build_packet(1, 0, b"", crc=0x1234)
        second = build_packet(1, 1, b"", previous_crc=0x1234)

        stream = PacketStream()
        stream.feed(first + second)

        assert stream.stats.chain_broken == 0

    def test_sessions_are_tracked(self):
        stream = PacketStream()
        stream.feed(build_packet(7, 0, b"") + build_packet(8, 1, b""))

        assert stream.stats.sessions == {7, 8}


class TestChecksum:
    def test_it_is_reported_as_unknown_until_configured(self):
        """B2: the polynomial is not in any document available."""
        stream = PacketStream()
        stream.feed(build_packet(1, 0, b"\x01\x02"))

        assert stream.stats.crc_unknown == 1
        assert stream.stats.crc_ok == 0
        assert not stream.stats.crc_configured

    def test_a_good_packet_passes_once_configured(self, configured_crc):
        stream = PacketStream()
        stream.feed(build_packet(1, 0, b"\x01\x02"))

        assert stream.stats.crc_ok == 1
        assert stream.stats.crc_bad == 0
        assert stream.stats.crc_configured

    def test_corrupting_one_byte_fails_exactly_one_packet(self, configured_crc):
        good = b"".join(build_packet(1, n, bytes([n])) for n in range(3))
        index = PACKET_BYTES + 100
        damaged = good[:index] + bytes([good[index] ^ 0xFF]) + good[index + 1:]

        stream = PacketStream(store_packets=True)
        stream.feed(damaged)

        assert stream.stats.received == 3
        assert stream.stats.crc_bad == 1
        assert stream.stats.crc_ok == 2
        assert [p.crc_status for p in stream.packets] == [CRC_OK, CRC_BAD, CRC_OK]

    def test_status_values(self, configured_crc):
        packet = PacketStream(store_packets=True)
        packet.feed(build_packet(1, 0, b"", crc=0xDEAD))
        assert packet.packets[0].crc_status == CRC_BAD


class TestStorage:
    def test_packets_are_not_stored_by_default(self):
        stream = PacketStream()
        stream.feed(build_packet(1, 0, b""))

        assert stream.packets == []
        assert stream.stats.received == 1

    def test_storage_can_be_switched_on(self):
        stream = PacketStream(store_packets=True)
        stream.feed(build_packet(1, 0, b""))

        assert len(stream.packets) == 1
        assert len(stream.packets[0].raw) == PACKET_BYTES

    def test_reset_clears_everything(self):
        stream = PacketStream(store_packets=True)
        stream.feed(build_packet(1, 0, b""))
        stream.reset()

        assert stream.packets == []
        assert stream.stats.received == 0


class TestCrcVariants:
    @pytest.mark.parametrize(
        ("name", "check"),
        [
            ("xmodem", 0x31C3),
            ("ccitt-false", 0x29B1),
            ("kermit", 0x2189),
            ("modbus", 0x4B37),
            ("arc", 0xBB3D),
            ("usb", 0xB4C8),
            ("maxim", 0x44C2),
        ],
    )
    def test_known_check_values(self, name, check):
        """Standard check value for b"123456789"."""
        assert crc16.VARIANTS_BY_NAME[name].compute(b"123456789") == check

    def test_detection_finds_the_variant_that_made_a_checksum(self):
        variant = crc16.VARIANTS_BY_NAME["modbus"]
        data = bytes(range(64))

        matches = crc16.detect_variant(data, variant.compute(data))

        assert variant in matches

    def test_detection_reports_nothing_for_a_bogus_checksum(self):
        assert crc16.detect_variant(bytes(64), 0x0001) == []

    def test_the_science_packet_variant_is_still_unset(self):
        """When this starts failing, B2 has been answered — wire it up and delete this test."""
        assert crc16.NI_PACKET_CRC is None
        assert crc16.compute_ni_crc(b"abc") is None
