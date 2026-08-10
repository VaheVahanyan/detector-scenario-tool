"""Framing and checking the science-data packet stream produced in DUMP mode.

Structure per `Формат_научной_информации_ГС_v6` §2.1 — 1024 little-endian 16-bit words:

===========  ==================================================
word 1–3     markers 46FFh, C9D7h, A5B3h
word 4       observation session identifier
word 5–6     packet number, low word first (0…262143)
word 7       checksum of the *previous* packet (0 in packet 0)
word 8–1023  information core
word 1024    checksum of this packet's core
===========  ==================================================

The stream is resynchronised by hunting the marker triple, so a capture that starts mid-packet or
loses a byte recovers instead of reporting every following packet as broken.

DUMP output travels over USB, not CAN (`mode_dump.md` §4.2, and `CMD_DUMP` bit 3 = 1 is rejected
with ERR_CONTENT), so this reads a byte stream rather than the command bus.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from detector_scenario_tool.protocol.crc16 import compute_ni_crc, is_configured

PACKET_WORDS = 1024
PACKET_BYTES = PACKET_WORDS * 2

MARKERS = (0x46FF, 0xC9D7, 0xA5B3)
MARKER_BYTES = b"".join(word.to_bytes(2, "little") for word in MARKERS)

CORE_FIRST_WORD = 8          # 1-based, per the document
CORE_LAST_WORD = 1023
CRC_WORD = 1024

#: Byte offsets derived from the word table above.
CORE_START = (CORE_FIRST_WORD - 1) * 2
CORE_END = CORE_LAST_WORD * 2
CRC_OFFSET = (CRC_WORD - 1) * 2

#: §2.3 — an unfilled tail is padded with AAAAh.
PAD_WORD = 0xAAAA

MAX_PACKET_NUMBER = 262_143


# Plain constants rather than an enum: "unknown" is a configuration state of the tool, not a
# property of the packet.
CRC_OK = "ok"
CRC_BAD = "bad"
CRC_UNKNOWN = "unknown"


@dataclass(frozen=True)
class Packet:
    session_id: int
    number: int
    previous_crc: int
    core: bytes
    crc: int
    raw: bytes
    #: Byte offset in the stream where this packet started.
    offset: int

    @property
    def crc_status(self) -> str:
        computed = compute_ni_crc(self.core)
        if computed is None:
            return CRC_UNKNOWN
        return CRC_OK if computed == self.crc else CRC_BAD

    @property
    def is_padded_tail(self) -> bool:
        """The last packet of a session is filled out with AAAAh (§2.3)."""
        tail = self.core[-2:]
        return tail == PAD_WORD.to_bytes(2, "little")


@dataclass
class PacketStats:
    received: int = 0
    crc_ok: int = 0
    crc_bad: int = 0
    crc_unknown: int = 0
    out_of_sequence: int = 0
    chain_broken: int = 0
    #: Blocks that ended early because bytes were lost inside them.
    truncated: int = 0
    resyncs: int = 0
    bytes_consumed: int = 0
    bytes_discarded: int = 0
    sessions: set[int] = field(default_factory=set)

    @property
    def valid(self) -> int:
        return self.crc_ok

    @property
    def crc_configured(self) -> bool:
        return is_configured()

    def reset(self) -> None:
        self.__init__()


class PacketStream:
    """Feed it bytes, take packets out.

    Holds at most one packet's worth of unmatched bytes, so a long capture does not accumulate.
    """

    def __init__(self, store_packets: bool = False) -> None:
        self.stats = PacketStats()
        self.store_packets = store_packets
        self.packets: list[Packet] = []

        self._buffer = bytearray()
        self._consumed = 0
        self._expected_number: int | None = None
        self._previous_crc: int | None = None

    def reset(self) -> None:
        self.stats.reset()
        self.packets.clear()
        self._buffer.clear()
        self._consumed = 0
        self._expected_number = None
        self._previous_crc = None

    def feed(self, data: bytes) -> list[Packet]:
        """Returns the packets completed by this chunk."""
        self._buffer.extend(data)
        found: list[Packet] = []

        while True:
            start = self._buffer.find(MARKER_BYTES)
            if start < 0:
                # Keep only what could still be the beginning of a marker.
                keep = len(MARKER_BYTES) - 1
                if len(self._buffer) > keep:
                    discarded = len(self._buffer) - keep
                    self.stats.bytes_discarded += discarded
                    self._consumed += discarded
                    del self._buffer[:discarded]
                break

            if start > 0:
                self.stats.bytes_discarded += start
                self.stats.resyncs += 1
                self._consumed += start
                del self._buffer[:start]

            # Where the next packet begins decides how long this one really is. Consuming a
            # blind 2048 bytes would swallow the next marker whenever a byte went missing, and
            # every following packet with it.
            next_marker = self._buffer.find(MARKER_BYTES, 1)

            if 0 < next_marker < PACKET_BYTES:
                # Short block: bytes were lost inside it, so its field boundaries have moved and
                # parsing it would produce confident nonsense.
                self.stats.truncated += 1
                self.stats.bytes_discarded += next_marker
                self._consumed += next_marker
                del self._buffer[:next_marker]
                continue

            if len(self._buffer) < PACKET_BYTES:
                break

            raw = bytes(self._buffer[:PACKET_BYTES])
            packet = self._parse(raw, self._consumed)
            self._record(packet)
            found.append(packet)

            del self._buffer[:PACKET_BYTES]
            self._consumed += PACKET_BYTES
            self.stats.bytes_consumed += PACKET_BYTES

        return found

    # -- internals ---------------------------------------------------------------------

    @staticmethod
    def _parse(raw: bytes, offset: int) -> Packet:
        def word(index: int) -> int:
            return int.from_bytes(raw[index * 2:index * 2 + 2], "little")

        number = word(4) | (word(5) << 16)
        return Packet(
            session_id=word(3),
            number=number,
            previous_crc=word(6),
            core=raw[CORE_START:CORE_END],
            crc=int.from_bytes(raw[CRC_OFFSET:CRC_OFFSET + 2], "little"),
            raw=raw,
            offset=offset,
        )

    def _record(self, packet: Packet) -> None:
        stats = self.stats
        stats.received += 1
        stats.sessions.add(packet.session_id)

        status = packet.crc_status
        if status == CRC_OK:
            stats.crc_ok += 1
        elif status == CRC_BAD:
            stats.crc_bad += 1
        else:
            stats.crc_unknown += 1

        if self._expected_number is not None and packet.number != self._expected_number:
            stats.out_of_sequence += 1
        self._expected_number = packet.number + 1

        # Word 7 chains a packet to the one before it; packet 0 carries 0 (§2.2).
        if self._previous_crc is not None and packet.previous_crc != self._previous_crc:
            stats.chain_broken += 1
        self._previous_crc = packet.crc

        if self.store_packets:
            self.packets.append(packet)


def build_packet(
        session_id: int,
        number: int,
        core: bytes,
        previous_crc: int = 0,
        crc: int | None = None,
) -> bytes:
    """Assemble a well-formed packet. Used by tests and by the file-replay fixtures."""
    if len(core) > CORE_END - CORE_START:
        raise ValueError("core is larger than the information core of a packet")

    body = bytearray()
    for marker in MARKERS:
        body += marker.to_bytes(2, "little")
    body += session_id.to_bytes(2, "little")
    body += (number & 0xFFFF).to_bytes(2, "little")
    body += ((number >> 16) & 0xFFFF).to_bytes(2, "little")
    body += previous_crc.to_bytes(2, "little")

    core_size = CORE_END - CORE_START
    # The core is a whole number of words, so an odd-length payload gets a zero byte first and
    # only then the AAAAh filler.
    padded = bytearray(core)
    if len(padded) % 2:
        padded.append(0x00)
    padded += PAD_WORD.to_bytes(2, "little") * ((core_size - len(padded)) // 2)
    padded = bytes(padded)
    body += padded

    if crc is None:
        computed = compute_ni_crc(bytes(padded))
        crc = computed if computed is not None else 0
    body += crc.to_bytes(2, "little")

    assert len(body) == PACKET_BYTES
    return bytes(body)
