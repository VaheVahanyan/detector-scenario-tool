"""UniCAN framing — the layer between a protocol message and CAN frames.

Specification: `SXC Орбикрафт-Про РЭ.pdf` §1.4.4. Note that `Протокол_CAN_ГС_v2.pdf` only *names*
UniCAN; it does not define it.

Addressing (§1.4.4.1) — source and destination live in the CAN identifier, together with a data
bit `Д` that separates a command/start frame from a continuation frame:

    standard (11 bit):  bit 10 = Д | bits 9-5 sender | bits 4-0 receiver
    extended (29 bit):  bit 28 = Д | bits 27-14 sender | bits 13-0 receiver

Short message (§1.4.4.3) — one frame, `Д = 0`, up to 6 payload bytes::

    data[0:2] = MSG_ID (little-endian) | data[2:8] = payload

Long message — a start frame followed by `Д = 1` data frames::

    start: data[0:2] = FFFEh | data[2:4] = MSG_ID | data[4:6] = Length
    data:  up to 8 bytes each, until Length bytes have arrived

`Length` counts the payload **plus** the trailing CRC and excludes the start frame, so
`Length = len(payload) + 2`. The last two bytes are a CRC16 X-modem over the message data.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from detector_scenario_tool.protocol.errors import UniCanBusError

#: §1.4.4.3 — a short message carries at most 6 payload bytes.
MAX_SHORT_PAYLOAD = 6

#: Service identifiers reserved by the protocol (§1.4.4.2: FF00…FFFF).
LONG_START_ID = 0xFFFE
ERROR_ID = 0xFFFF
RESERVED_MSG_ID_START = 0xFF00

#: The two identifiers that genuinely break the framing rather than merely being spoken for.
#: `Протокол_CAN_ГС_v2_1_Спутникс` allocates FFE0h/FFE1h out of the reserved band for the software
#: version query, and the firmware side confirmed the НА accepts them — so the band is a convention
#: this payload does not follow, and only these two can be refused outright.
UNUSABLE_MSG_IDS = frozenset({LONG_START_ID, ERROR_ID})

#: Address field widths, from the identifier layouts above.
STANDARD_ADDRESS_BITS = 5
EXTENDED_ADDRESS_BITS = 14

MAX_DLC = 8

#: The document says "CRC16 X-modem" but not the byte order of the two trailing bytes. Everything
#: else in this protocol family is little-endian, so that is the assumption; if a capture shows
#: otherwise this is the single line to change.
CRC_BYTE_ORDER = "little"


class UniCanError(ValueError):
    """Raised for input the framing layer cannot represent."""


# --------------------------------------------------------------------------------------
# CRC16 X-modem
# --------------------------------------------------------------------------------------

def crc16_xmodem(data: bytes, seed: int = 0x0000) -> int:
    """Poly 0x1021, init 0x0000, no reflection, no final XOR.

    Check value for b"123456789" is 0x31C3.
    """
    crc = seed
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


# --------------------------------------------------------------------------------------
# Frames and decoded messages
# --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class CanFrame:
    can_id: int
    data: bytes
    extended: bool = False

    @property
    def dlc(self) -> int:
        return len(self.data)


@dataclass(frozen=True)
class UniCanMessage:
    msg_id: int
    payload: bytes
    source: int
    destination: int
    is_long: bool = False


@dataclass(frozen=True)
class UniCanErrorFrame:
    """An error frame received from the bus (FFFFh, §1.4.4.3 table 11)."""

    failed_msg_id: int
    code: int
    source: int
    destination: int

    @property
    def known_code(self) -> UniCanBusError | None:
        try:
            return UniCanBusError(self.code)
        except ValueError:
            return None


@dataclass(frozen=True)
class UniCanDecodeError:
    """A problem this end detected while reassembling — not something the bus reported."""

    code: UniCanBusError
    detail: str
    msg_id: int | None = None
    source: int | None = None


# --------------------------------------------------------------------------------------
# Identifier packing
# --------------------------------------------------------------------------------------

def address_bits(extended: bool) -> int:
    return EXTENDED_ADDRESS_BITS if extended else STANDARD_ADDRESS_BITS


def max_address(extended: bool) -> int:
    return (1 << address_bits(extended)) - 1


def encode_can_id(destination: int, source: int, data_bit: bool, extended: bool) -> int:
    bits = address_bits(extended)
    limit = max_address(extended)

    for name, value in (("destination", destination), ("source", source)):
        if not 0 <= value <= limit:
            raise UniCanError(
                f"{name} address 0x{value:X} does not fit in {bits} bits "
                f"({'extended' if extended else 'standard'} identifier)."
            )

    return ((1 if data_bit else 0) << (2 * bits)) | (source << bits) | destination


def decode_can_id(can_id: int, extended: bool) -> tuple[int, int, bool]:
    """Returns (destination, source, data_bit)."""
    bits = address_bits(extended)
    mask = (1 << bits) - 1

    destination = can_id & mask
    source = (can_id >> bits) & mask
    data_bit = bool((can_id >> (2 * bits)) & 1)
    return destination, source, data_bit


# --------------------------------------------------------------------------------------
# Encoding
# --------------------------------------------------------------------------------------

def encode(
        msg_id: int,
        payload: bytes,
        destination: int,
        source: int,
        extended: bool = False,
) -> list[CanFrame]:
    """Split a protocol message into CAN frames. Short or long is decided by the payload size."""
    if not 0 <= msg_id <= 0xFFFF:
        raise UniCanError(f"MSG_ID 0x{msg_id:X} is not a 16-bit value.")
    if msg_id in UNUSABLE_MSG_IDS:
        raise UniCanError(
            f"MSG_ID 0x{msg_id:04X} is the long-message start or the error frame; "
            f"sending it as a message would corrupt the framing."
        )

    if len(payload) <= MAX_SHORT_PAYLOAD:
        return [_encode_short(msg_id, payload, destination, source, extended)]

    return _encode_long(msg_id, payload, destination, source, extended)


def _encode_short(
        msg_id: int, payload: bytes, destination: int, source: int, extended: bool
) -> CanFrame:
    can_id = encode_can_id(destination, source, data_bit=False, extended=extended)
    return CanFrame(can_id, msg_id.to_bytes(2, "little") + payload, extended)


def _encode_long(
        msg_id: int, payload: bytes, destination: int, source: int, extended: bool
) -> list[CanFrame]:
    body = payload + crc16_xmodem(payload).to_bytes(2, CRC_BYTE_ORDER)
    length = len(body)
    if length > 0xFFFF:
        raise UniCanError(f"Message body of {length} bytes exceeds the 16-bit length field.")

    start_id = encode_can_id(destination, source, data_bit=False, extended=extended)
    data_id = encode_can_id(destination, source, data_bit=True, extended=extended)

    frames = [
        CanFrame(
            start_id,
            LONG_START_ID.to_bytes(2, "little")
            + msg_id.to_bytes(2, "little")
            + length.to_bytes(2, "little"),
            extended,
        )
    ]
    frames.extend(
        CanFrame(data_id, body[offset:offset + MAX_DLC], extended)
        for offset in range(0, length, MAX_DLC)
    )
    return frames


def encode_error(
        failed_msg_id: int,
        code: int,
        destination: int,
        source: int,
        extended: bool = False,
) -> CanFrame:
    can_id = encode_can_id(destination, source, data_bit=False, extended=extended)
    return CanFrame(
        can_id,
        ERROR_ID.to_bytes(2, "little")
        + failed_msg_id.to_bytes(2, "little")
        + int(code).to_bytes(2, "little"),
        extended,
    )


# --------------------------------------------------------------------------------------
# Reassembly
# --------------------------------------------------------------------------------------

@dataclass
class _Transfer:
    msg_id: int
    length: int
    destination: int
    buffer: bytearray = field(default_factory=bytearray)


class Reassembler:
    """Turns a stream of CAN frames back into messages.

    Transfers are tracked per source address, because §1.4.4.3 continues a long message with
    "все последующие кадры, приходящие с того же устройства".
    """

    def __init__(self, extended: bool = False) -> None:
        self.extended = extended
        self._transfers: dict[int, _Transfer] = {}

    def reset(self) -> None:
        self._transfers.clear()

    def feed(
            self, frame: CanFrame
    ) -> UniCanMessage | UniCanErrorFrame | UniCanDecodeError | None:
        destination, source, data_bit = decode_can_id(frame.can_id, self.extended)

        if data_bit:
            return self._feed_data(frame, source)

        if frame.dlc < 2:
            # §1.4.4.3: "сообщения, у которых поле «данные» равно нулю и поле DLC которых меньше
            # двух, являются некорректными и должны быть отброшены".
            return UniCanDecodeError(
                UniCanBusError.COMMAND_TOO_SHORT,
                f"command frame with DLC {frame.dlc}",
                source=source,
            )

        header = int.from_bytes(frame.data[0:2], "little")

        if header == LONG_START_ID:
            return self._start_long(frame, source, destination)

        if header == ERROR_ID:
            return self._decode_error_frame(frame, source, destination)

        return UniCanMessage(
            msg_id=header,
            payload=bytes(frame.data[2:]),
            source=source,
            destination=destination,
            is_long=False,
        )

    # -- long transfers ----------------------------------------------------------------

    def _start_long(
            self, frame: CanFrame, source: int, destination: int
    ) -> UniCanDecodeError | None:
        if frame.dlc < 6:
            return UniCanDecodeError(
                UniCanBusError.START_COMMAND_TOO_SHORT,
                f"start frame with DLC {frame.dlc}",
                source=source,
            )

        msg_id = int.from_bytes(frame.data[2:4], "little")
        length = int.from_bytes(frame.data[4:6], "little")

        previous = self._transfers.get(source)
        self._transfers[source] = _Transfer(msg_id, length, destination)

        if previous is not None:
            return UniCanDecodeError(
                UniCanBusError.START_BEFORE_PREVIOUS_FINISHED,
                f"0x{previous.msg_id:04X} was still incomplete",
                msg_id=previous.msg_id,
                source=source,
            )
        return None

    def _feed_data(
            self, frame: CanFrame, source: int
    ) -> UniCanMessage | UniCanDecodeError | None:
        transfer = self._transfers.get(source)
        if transfer is None:
            # §1.4.4.3: data frames with no preceding start are ignored.
            return UniCanDecodeError(
                UniCanBusError.DATA_WITHOUT_START,
                "data frame outside a transfer",
                source=source,
            )

        transfer.buffer.extend(frame.data)

        if len(transfer.buffer) < transfer.length:
            return None

        self._transfers.pop(source, None)

        if len(transfer.buffer) > transfer.length:
            return UniCanDecodeError(
                UniCanBusError.MORE_DATA_THAN_DECLARED,
                f"{len(transfer.buffer)} bytes for a declared {transfer.length}",
                msg_id=transfer.msg_id,
                source=source,
            )

        if transfer.length < 2:
            return UniCanDecodeError(
                UniCanBusError.COMMAND_TOO_SHORT,
                f"declared length {transfer.length} leaves no room for a CRC",
                msg_id=transfer.msg_id,
                source=source,
            )

        payload = bytes(transfer.buffer[:-2])
        received_crc = int.from_bytes(transfer.buffer[-2:], CRC_BYTE_ORDER)
        if received_crc != crc16_xmodem(payload):
            return UniCanDecodeError(
                UniCanBusError.CRC_ERROR,
                f"expected 0x{crc16_xmodem(payload):04X}, got 0x{received_crc:04X}",
                msg_id=transfer.msg_id,
                source=source,
            )

        return UniCanMessage(
            msg_id=transfer.msg_id,
            payload=payload,
            source=source,
            destination=transfer.destination,
            is_long=True,
        )

    @staticmethod
    def _decode_error_frame(
            frame: CanFrame, source: int, destination: int
    ) -> UniCanErrorFrame | UniCanDecodeError:
        if frame.dlc < 6:
            return UniCanDecodeError(
                UniCanBusError.COMMAND_TOO_SHORT,
                f"error frame with DLC {frame.dlc}",
                source=source,
            )
        return UniCanErrorFrame(
            failed_msg_id=int.from_bytes(frame.data[2:4], "little"),
            code=int.from_bytes(frame.data[4:6], "little"),
            source=source,
            destination=destination,
        )
