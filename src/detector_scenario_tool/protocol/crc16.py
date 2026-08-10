"""CRC16 variants, and the one the science-data packets use.

`Формат_научной_информации_ГС_v6` says the last word of a packet is "CRC16" and nothing more —
no polynomial, no initial value, no reflection. Until that is confirmed against the firmware,
`NI_PACKET_CRC` stays `None` and the packet monitor reports the checksum as *not configured*
rather than inventing a verdict.

`detect_variant` closes the gap from the other end: given one captured packet whose checksum is
known good, it reports which of the named variants reproduces it.

Note this is a different checksum from UniCAN's, which the OrbiCraft manual does specify
(CRC16 X-modem) and which lives in `transport/unican.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class Crc16Variant:
    name: str
    polynomial: int
    init: int
    reflect_in: bool
    reflect_out: bool
    xor_out: int

    def compute(self, data: bytes) -> int:
        crc = self.init
        for byte in data:
            if self.reflect_in:
                byte = _reflect(byte, 8)
            crc ^= byte << 8
            for _ in range(8):
                crc = ((crc << 1) ^ self.polynomial) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
        if self.reflect_out:
            crc = _reflect(crc, 16)
        return crc ^ self.xor_out


def _reflect(value: int, width: int) -> int:
    result = 0
    for i in range(width):
        if value & (1 << i):
            result |= 1 << (width - 1 - i)
    return result


#: The variants worth trying against a capture. Check values are for b"123456789".
KNOWN_VARIANTS: tuple[Crc16Variant, ...] = (
    Crc16Variant("xmodem", 0x1021, 0x0000, False, False, 0x0000),        # 0x31C3
    Crc16Variant("ccitt-false", 0x1021, 0xFFFF, False, False, 0x0000),   # 0x29B1
    Crc16Variant("kermit", 0x1021, 0x0000, True, True, 0x0000),          # 0x2189
    Crc16Variant("modbus", 0x8005, 0xFFFF, True, True, 0x0000),          # 0x4B37
    Crc16Variant("arc", 0x8005, 0x0000, True, True, 0x0000),             # 0xBB3D
    Crc16Variant("usb", 0x8005, 0xFFFF, True, True, 0xFFFF),             # 0xB4C8
    Crc16Variant("maxim", 0x8005, 0x0000, True, True, 0xFFFF),           # 0x44C2
)

VARIANTS_BY_NAME = {variant.name: variant for variant in KNOWN_VARIANTS}

# ---------------------------------------------------------------------------------------
# TODO(B2): fill this in once the firmware's polynomial is known — see docs/UPGRADE_PLAN.md §1.
#
# Set it either to a name from KNOWN_VARIANTS, e.g.
#     NI_PACKET_CRC = VARIANTS_BY_NAME["ccitt-false"]
# or to a Crc16Variant spelled out in full. Everything downstream reads this one symbol.
# ---------------------------------------------------------------------------------------
NI_PACKET_CRC: Crc16Variant | None = None


def is_configured() -> bool:
    return NI_PACKET_CRC is not None


def compute_ni_crc(data: bytes) -> int | None:
    """The packet checksum, or None while the variant is unknown."""
    if NI_PACKET_CRC is None:
        return None
    return NI_PACKET_CRC.compute(data)


def detect_variant(
        data: bytes,
        expected: int,
        variants: Iterable[Crc16Variant] = KNOWN_VARIANTS,
) -> list[Crc16Variant]:
    """Which variants reproduce `expected` over `data`.

    More than one can match on a short sample, so the caller should try a second packet before
    believing the answer.
    """
    return [variant for variant in variants if variant.compute(data) == expected]
