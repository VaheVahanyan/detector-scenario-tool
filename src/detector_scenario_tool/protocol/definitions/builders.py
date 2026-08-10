"""Small constructors that keep the message definitions readable.

Label keys default to `field.<key>`, a flat namespace: the payload keys are already semantic
(`keep_power_after_erase` rather than `hw_bit2`), so a field that means the same thing in two
messages shares one translation.
"""

from __future__ import annotations

from typing import Any, Mapping

from detector_scenario_tool.protocol.fields import FieldKind, FieldSpec

AA = 0xAA


def _label(key: str, label_key: str | None) -> str:
    return label_key or f"field.{key}"


def uint(key: str, offset: int, length: int, **kw: Any) -> FieldSpec:
    return FieldSpec(
        key=key,
        label_key=_label(key, kw.pop("label_key", None)),
        kind=FieldKind.UINT,
        byte_offset=offset,
        byte_length=length,
        **kw,
    )


def u8(key: str, offset: int, **kw: Any) -> FieldSpec:
    return uint(key, offset, 1, **kw)


def u16(key: str, offset: int, **kw: Any) -> FieldSpec:
    return uint(key, offset, 2, **kw)


def u24(key: str, offset: int, **kw: Any) -> FieldSpec:
    return uint(key, offset, 3, **kw)


def u32(key: str, offset: int, **kw: Any) -> FieldSpec:
    return uint(key, offset, 4, **kw)


def u64(key: str, offset: int, **kw: Any) -> FieldSpec:
    return uint(key, offset, 8, **kw)


def i16(key: str, offset: int, **kw: Any) -> FieldSpec:
    return FieldSpec(
        key=key,
        label_key=_label(key, kw.pop("label_key", None)),
        kind=FieldKind.INT,
        byte_offset=offset,
        byte_length=2,
        **kw,
    )


def f32(key: str, offset: int, **kw: Any) -> FieldSpec:
    return FieldSpec(
        key=key,
        label_key=_label(key, kw.pop("label_key", None)),
        kind=FieldKind.FLOAT,
        byte_offset=offset,
        byte_length=4,
        default=kw.pop("default", 0.0),
        **kw,
    )


def bits(
        key: str,
        offset: int,
        bit_offset: int,
        bit_length: int,
        byte_length: int = 1,
        **kw: Any,
) -> FieldSpec:
    choices: Mapping[int, str] | None = kw.pop("choices", None)
    return FieldSpec(
        key=key,
        label_key=_label(key, kw.pop("label_key", None)),
        kind=FieldKind.ENUM if choices else FieldKind.BITS,
        byte_offset=offset,
        byte_length=byte_length,
        bit_offset=bit_offset,
        bit_length=bit_length,
        choices=choices,
        **kw,
    )


def flag(key: str, offset: int, bit_offset: int, byte_length: int = 1, **kw: Any) -> FieldSpec:
    """A single bit, edited as a checkbox."""
    return bits(key, offset, bit_offset, 1, byte_length=byte_length, **kw)


def reserved(
        offset: int,
        bit_offset: int,
        bit_length: int,
        byte_length: int = 1,
        value: int = 0,
        suffix: str = "",
) -> FieldSpec:
    """Bits the document pins to a fixed value; validated, never editable."""
    key = f"_reserved_{offset}_{bit_offset}{suffix}"
    return FieldSpec(
        key=key,
        label_key="field.reserved",
        kind=FieldKind.BITS,
        byte_offset=offset,
        byte_length=byte_length,
        bit_offset=bit_offset,
        bit_length=bit_length,
        fixed_value=value,
    )


def filler(offset: int, length: int, value: int = AA) -> FieldSpec:
    """Bytes the document fixes to AAh."""
    return FieldSpec(
        key=f"_filler_{offset}",
        label_key="field.filler",
        kind=FieldKind.FILLER,
        byte_offset=offset,
        byte_length=length,
        fixed_value=value,
    )


def unused(offset: int, length: int, value: int = AA) -> FieldSpec:
    """Bytes documented as `XXh — не определено`: transmitted but never checked."""
    return FieldSpec(
        key=f"_unused_{offset}",
        label_key="field.unused",
        kind=FieldKind.UNUSED,
        byte_offset=offset,
        byte_length=length,
        fixed_value=value,
    )


def raw(key: str, offset: int, length: int, **kw: Any) -> FieldSpec:
    return FieldSpec(
        key=key,
        label_key=_label(key, kw.pop("label_key", None)),
        kind=FieldKind.RAW,
        byte_offset=offset,
        byte_length=length,
        default=kw.pop("default", b""),
        **kw,
    )


#: Bank selector shared by CMD_OBSERVE_START, CMD_DUTY, CMD_DUMP, CMD_ERASE, CMD_TEST,
#: CMD_TEST_RESULT. Bits 0-1 hold 1 (NAND1) or 2 (NAND2); 0 and 3 are rejected.
NAND_BANK_CHOICES: dict[int, str] = {1: "choice.nand1", 2: "choice.nand2"}
MRAM_BANK_CHOICES: dict[int, str] = {1: "choice.mram1", 2: "choice.mram2"}


def nand_bank(offset: int = 0, bit_offset: int = 0, key: str = "selected_nand_bank") -> FieldSpec:
    return bits(
        key,
        offset,
        bit_offset,
        2,
        choices=NAND_BANK_CHOICES,
        min_value=1,
        max_value=2,
        default=1,
    )


def mram_bank(offset: int = 0, bit_offset: int = 2, key: str = "selected_mram_bank") -> FieldSpec:
    return bits(
        key,
        offset,
        bit_offset,
        2,
        choices=MRAM_BANK_CHOICES,
        min_value=1,
        max_value=2,
        default=1,
    )
