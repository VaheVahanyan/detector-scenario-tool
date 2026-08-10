"""Declarative message description: the single source of truth for the CAN protocol.

Before this module a message's byte layout was written out four times — in the packers, in a
hand-written payload editor, in the validators and in the log decoder — and those four had to agree
on dict key names by convention alone. A `MessageDef` is written once; packing, unpacking,
validation, editing and log rendering are all derived from it.

Byte offsets are relative to the *message content*. For UniCAN short messages the protocol document
numbers content bytes from 2, because those are the CAN frame data bytes that follow the 2-byte
MSG_ID; `MessageDef.content_origin` records that offset so labels and diagnostics can quote the
document's numbering.
"""

from __future__ import annotations

import struct
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence


class FieldKind(str, Enum):
    UINT = "uint"
    INT = "int"
    FLOAT = "float"
    BITS = "bits"
    ENUM = "enum"
    FILLER = "filler"      # every byte a fixed value (AAh); checked
    UNUSED = "unused"      # "XXh — не определено"; filled but never checked
    RAW = "raw"            # opaque byte block, edited as hex


class PackingError(ValueError):
    pass


@dataclass(frozen=True)
class FieldSpec:
    key: str
    label_key: str
    kind: FieldKind
    byte_offset: int
    byte_length: int
    bit_offset: int | None = None
    bit_length: int | None = None
    min_value: int | None = None
    max_value: int | None = None
    fixed_value: int | None = None
    choices: Mapping[int, str] | None = None
    default: Any = 0
    unit: str = ""
    doc_ref: str = ""
    #: Literal label for a user-defined field. It is not translatable, so it wins over label_key.
    custom_label: str = ""

    @property
    def label(self) -> str:
        """What to show the user. Resolved here so every view agrees."""
        from detector_scenario_tool.i18n import tr

        return self.custom_label or tr(self.label_key)

    @property
    def is_bitfield(self) -> bool:
        return self.bit_offset is not None

    @property
    def editable(self) -> bool:
        """Whether the user chooses this value.

        Fillers, undefined bytes and reserved bits are all pinned by the document, so they get no
        widget and never enter a step's payload — the packer takes them from `fixed_value`.
        """
        if self.kind in (FieldKind.FILLER, FieldKind.UNUSED):
            return False
        return self.fixed_value is None

    @property
    def effective_min(self) -> int | None:
        if self.min_value is not None:
            return self.min_value
        if self.is_bitfield:
            return 0
        if self.kind is FieldKind.UINT:
            return 0
        if self.kind is FieldKind.INT:
            return -(1 << (self.byte_length * 8 - 1))
        return None

    @property
    def effective_max(self) -> int | None:
        if self.max_value is not None:
            return self.max_value
        if self.is_bitfield:
            return (1 << self.bit_length) - 1
        if self.kind is FieldKind.UINT:
            return (1 << (self.byte_length * 8)) - 1
        if self.kind is FieldKind.INT:
            return (1 << (self.byte_length * 8 - 1)) - 1
        return None


@dataclass(frozen=True)
class CrossCheck:
    """A rule that spans several fields and cannot be expressed as a range."""

    code: str
    check: Any  # Callable[[Mapping[str, Any]], bool] — True when the payload is valid
    keys: tuple[str, ...] = ()


class AckBehaviour(str, Enum):
    NONE = "none"                  # КТ: no acknowledgement at all
    ACK = "ack"
    ACK_MAY_BE_SUPPRESSED = "ack_may_be_suppressed"  # CMD_SET_TIME_SPUTNIKS


@dataclass(frozen=True)
class ExpectedResponse:
    category: str
    msg_id: int
    timeout_ms: int = 1000
    is_ack: bool = False
    bind_to_previous_ku: bool = False
    require_ack_ok: bool = False
    guaranteed: bool = True


@dataclass(frozen=True)
class CyclicDefault:
    enabled: bool = False
    period_ms: int = 20_000


@dataclass(frozen=True)
class MessageDef:
    category: str            # "KU" | "KT" | "TS"
    msg_id: int
    symbol: str              # CMD_SET_TIME
    name_key: str
    length: int
    fields: tuple[FieldSpec, ...] = ()
    allowed_modes: frozenset = frozenset()
    ack: AckBehaviour = AckBehaviour.ACK
    follow_up: tuple[ExpectedResponse, ...] = ()
    cross_checks: tuple[CrossCheck, ...] = ()
    cyclic_default: CyclicDefault | None = None
    doc_ref: str = ""
    changes_mode_to: Any = None
    #: True for a message the user defined rather than one from the specification.
    custom: bool = False
    #: User-supplied name; it is not translatable, so it wins over `name_key` when set.
    custom_name: str = ""
    #: Overrides for a custom message that deliberately targets other addresses or framing.
    forced_long: bool | None = None
    destination_override: int | None = None
    source_override: int | None = None

    @property
    def is_long(self) -> bool:
        """UniCAN short messages carry at most 6 payload bytes (SXC РЭ §1.4.4.3)."""
        if self.forced_long is not None:
            return self.forced_long
        return self.length > 6

    @property
    def content_origin(self) -> int:
        return 0 if self.is_long else 2

    @property
    def sendable(self) -> bool:
        return self.category in ("KU", "KT")

    @property
    def editable_fields(self) -> tuple[FieldSpec, ...]:
        return tuple(f for f in self.fields if f.editable)

    def field(self, key: str) -> FieldSpec | None:
        for spec in self.fields:
            if spec.key == key:
                return spec
        return None

    def default_payload(self) -> dict[str, Any]:
        return {f.key: f.default for f in self.editable_fields}


# --------------------------------------------------------------------------------------
# Packing
# --------------------------------------------------------------------------------------

def _group_fields(spec: MessageDef) -> dict[tuple[int, int], list[FieldSpec]]:
    groups: dict[tuple[int, int], list[FieldSpec]] = defaultdict(list)
    for field_spec in spec.fields:
        groups[(field_spec.byte_offset, field_spec.byte_length)].append(field_spec)
    return groups


def _resolve(field_spec: FieldSpec, payload: Mapping[str, Any]) -> Any:
    if field_spec.kind in (FieldKind.FILLER, FieldKind.UNUSED):
        return field_spec.fixed_value if field_spec.fixed_value is not None else 0

    if field_spec.fixed_value is not None:
        # Reserved bits: the document fixes the value, so ignore whatever the payload says.
        return field_spec.fixed_value

    if field_spec.key not in payload:
        return field_spec.default

    return payload[field_spec.key]


def _coerce_int(field_spec: FieldSpec, value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if not isinstance(value, int):
        raise PackingError(
            f"Field {field_spec.key!r} must be an integer, got {type(value).__name__}."
        )

    low, high = field_spec.effective_min, field_spec.effective_max
    if low is not None and value < low:
        raise PackingError(f"Field {field_spec.key!r} = {value} is below {low}.")
    if high is not None and value > high:
        raise PackingError(f"Field {field_spec.key!r} = {value} is above {high}.")
    return value


def pack_message(spec: MessageDef, payload: Mapping[str, Any]) -> bytes:
    """Render `payload` into the message's `length` content bytes."""
    buf = bytearray(spec.length)
    written = bytearray(spec.length)

    for (offset, byte_length), specs in _group_fields(spec).items():
        if offset < 0 or offset + byte_length > spec.length:
            raise PackingError(
                f"{spec.symbol}: field at {offset}..{offset + byte_length - 1} "
                f"does not fit in {spec.length} bytes."
            )

        chunk = _pack_group(spec, specs, byte_length, payload)
        buf[offset:offset + byte_length] = chunk
        for i in range(offset, offset + byte_length):
            written[i] = 1

    if not all(written):
        gaps = [i for i, done in enumerate(written) if not done]
        raise PackingError(
            f"{spec.symbol}: bytes {gaps[:8]}{'...' if len(gaps) > 8 else ''} are not described."
        )

    return bytes(buf)


def _pack_group(
        spec: MessageDef,
        specs: Sequence[FieldSpec],
        byte_length: int,
        payload: Mapping[str, Any],
) -> bytes:
    first = specs[0]

    if first.kind is FieldKind.FILLER or first.kind is FieldKind.UNUSED:
        fill = first.fixed_value if first.fixed_value is not None else 0
        return bytes([fill]) * byte_length

    if first.kind is FieldKind.RAW:
        value = _resolve(first, payload)
        raw = _coerce_raw(first, value, byte_length)
        return raw

    if first.kind is FieldKind.FLOAT:
        value = _resolve(first, payload)
        try:
            return struct.pack("<f", float(value))
        except (TypeError, ValueError) as exc:
            raise PackingError(f"Field {first.key!r}: {exc}") from exc

    if first.is_bitfield:
        word = 0
        for field_spec in specs:
            value = _coerce_int(field_spec, _resolve(field_spec, payload))
            mask = (1 << field_spec.bit_length) - 1
            word |= (value & mask) << field_spec.bit_offset
        return word.to_bytes(byte_length, "little", signed=False)

    if len(specs) != 1:
        raise PackingError(
            f"{spec.symbol}: several non-bitfield fields share bytes "
            f"{first.byte_offset}..{first.byte_offset + byte_length - 1}."
        )

    value = _coerce_int(first, _resolve(first, payload))
    signed = first.kind is FieldKind.INT
    return value.to_bytes(byte_length, "little", signed=signed)


def _coerce_raw(field_spec: FieldSpec, value: Any, byte_length: int) -> bytes:
    if isinstance(value, (bytes, bytearray)):
        raw = bytes(value)
    elif isinstance(value, str):
        cleaned = value.replace(" ", "").replace("\n", "")
        try:
            raw = bytes.fromhex(cleaned)
        except ValueError as exc:
            raise PackingError(f"Field {field_spec.key!r} is not valid hex: {exc}") from exc
    elif isinstance(value, (list, tuple)):
        raw = bytes(value)
    elif value in (None, 0):
        raw = b""
    else:
        raise PackingError(f"Field {field_spec.key!r} must be bytes or a hex string.")

    if len(raw) > byte_length:
        raise PackingError(
            f"Field {field_spec.key!r} is {len(raw)} bytes, expected at most {byte_length}."
        )
    return raw + bytes(byte_length - len(raw))


# --------------------------------------------------------------------------------------
# Unpacking (log decoding)
# --------------------------------------------------------------------------------------

def unpack_message(spec: MessageDef, data: bytes) -> dict[str, Any]:
    """Decode content bytes into a payload dict. Short data yields only the fields that fit."""
    values: dict[str, Any] = {}

    for field_spec in spec.fields:
        start = field_spec.byte_offset
        end = start + field_spec.byte_length
        if end > len(data):
            continue

        chunk = data[start:end]

        if field_spec.kind is FieldKind.FLOAT:
            values[field_spec.key] = struct.unpack("<f", chunk)[0]
            continue

        if field_spec.kind is FieldKind.RAW:
            values[field_spec.key] = chunk
            continue

        if field_spec.kind in (FieldKind.FILLER, FieldKind.UNUSED):
            continue

        word = int.from_bytes(chunk, "little", signed=field_spec.kind is FieldKind.INT)

        if field_spec.is_bitfield:
            unsigned = int.from_bytes(chunk, "little", signed=False)
            mask = (1 << field_spec.bit_length) - 1
            values[field_spec.key] = (unsigned >> field_spec.bit_offset) & mask
        else:
            values[field_spec.key] = word

    return values


# --------------------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class FieldIssue:
    code: str
    key: str
    params: dict[str, Any] = field(default_factory=dict)


def validate_payload(spec: MessageDef, payload: Mapping[str, Any]) -> list[FieldIssue]:
    """Range, reserved-value and cross-field checks, derived from the definition."""
    issues: list[FieldIssue] = []

    for field_spec in spec.fields:
        if field_spec.fixed_value is not None:
            # Reserved bits and fillers: the packer always writes the documented value, but a
            # payload that disagrees means a hand-edited file or a stale migration.
            supplied = payload.get(field_spec.key)
            if supplied is not None and supplied != field_spec.fixed_value:
                issues.append(
                    FieldIssue(
                        "field.reserved_value",
                        field_spec.key,
                        {"expected": field_spec.fixed_value, "actual": supplied},
                    )
                )
            continue

        if field_spec.kind in (FieldKind.FILLER, FieldKind.UNUSED):
            continue

        if field_spec.key not in payload:
            continue

        value = payload[field_spec.key]

        if field_spec.kind is FieldKind.FLOAT:
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                issues.append(FieldIssue("field.not_a_number", field_spec.key, {"actual": value}))
            continue

        if field_spec.kind is FieldKind.RAW:
            continue

        if isinstance(value, bool) or not isinstance(value, int):
            issues.append(FieldIssue("field.not_an_integer", field_spec.key, {"actual": value}))
            continue

        low, high = field_spec.effective_min, field_spec.effective_max
        if (low is not None and value < low) or (high is not None and value > high):
            issues.append(
                FieldIssue(
                    "field.out_of_range",
                    field_spec.key,
                    {"actual": value, "min": low, "max": high},
                )
            )
            continue

        if field_spec.choices is not None and value not in field_spec.choices:
            issues.append(
                FieldIssue(
                    "field.invalid_choice",
                    field_spec.key,
                    {"actual": value, "allowed": sorted(field_spec.choices)},
                )
            )

    for rule in spec.cross_checks:
        try:
            ok = rule.check(payload)
        except Exception:
            ok = False
        if not ok:
            issues.append(FieldIssue(rule.code, rule.keys[0] if rule.keys else "", {}))

    return issues


def describe_layout(spec: MessageDef) -> list[tuple[int, int, str]]:
    """(doc byte offset, length, key) for every field — used by tests and tooltips."""
    return [
        (f.byte_offset + spec.content_origin, f.byte_length, f.key)
        for f in sorted(spec.fields, key=lambda f: (f.byte_offset, f.bit_offset or 0))
    ]


def iter_covered_bytes(spec: MessageDef) -> Iterable[int]:
    covered: set[int] = set()
    for f in spec.fields:
        covered.update(range(f.byte_offset, f.byte_offset + f.byte_length))
    return sorted(covered)
