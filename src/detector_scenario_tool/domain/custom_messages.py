"""User-defined messages.

The frame format is fixed — a UniCAN header plus a payload — so authoring one means choosing a
MSG_ID, the two addresses, the length, whether it is short or long, and the content bytes.

A custom message becomes an ordinary `MessageDef` carrying a single `raw` field. Everything
downstream — the packer, the generic payload editor, validation, the log decoder, the runner —
then works on it with no special cases, which is the whole point of the declarative layer.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from detector_scenario_tool.domain.scenario import CyclicPolicy
from detector_scenario_tool.protocol.definitions.builders import bits, raw, u8
from detector_scenario_tool.protocol.fields import AckBehaviour, CyclicDefault, MessageDef
from detector_scenario_tool.protocol.modes import OPERATIONAL_MODES
from detector_scenario_tool.transport.unican import (
    MAX_SHORT_PAYLOAD,
    RESERVED_MSG_ID_START,
)

#: Longest message in the protocol is ТС «Результаты теста ППЗУ» at 6146 bytes; allow a little
#: more so a deliberately oversized negative test is still expressible.
MAX_CUSTOM_LENGTH = 8192

CATEGORIES = ("KU", "KT", "TS")


@dataclass
class CustomBitRange:
    """A named run of bits inside one byte."""

    name: str = ""
    offset: int = 0
    length: int = 1

    def __post_init__(self) -> None:
        self.offset = max(0, min(7, int(self.offset)))
        self.length = max(1, min(8 - self.offset, int(self.length)))

    @property
    def mask(self) -> int:
        return ((1 << self.length) - 1) << self.offset

    @property
    def label(self) -> str:
        return self.name or self.range_text

    @property
    def range_text(self) -> str:
        last = self.offset + self.length - 1
        return str(self.offset) if last == self.offset else f"{self.offset}-{last}"

    def extract(self, byte_value: int) -> int:
        return (byte_value >> self.offset) & ((1 << self.length) - 1)

    def apply(self, byte_value: int, value: int) -> int:
        capped = int(value) & ((1 << self.length) - 1)
        return (byte_value & ~self.mask & 0xFF) | (capped << self.offset)


@dataclass
class CustomByteLayout:
    """A name for one content byte, and optionally the bit fields inside it."""

    name: str = ""
    bits: list[CustomBitRange] = field(default_factory=list)

    @property
    def is_split(self) -> bool:
        return bool(self.bits)


def parse_bit_range(text: str) -> CustomBitRange | None:
    """`3` or `0-2`, as the user types it."""
    cleaned = (text or "").strip().replace(" ", "").replace("–", "-")
    if not cleaned:
        return None

    try:
        if "-" in cleaned:
            first_text, last_text = cleaned.split("-", 1)
            first, last = int(first_text), int(last_text)
        else:
            first = last = int(cleaned)
    except ValueError:
        return None

    if first > last:
        first, last = last, first
    if not (0 <= first <= 7 and 0 <= last <= 7):
        return None

    return CustomBitRange(offset=first, length=last - first + 1)


@dataclass
class CustomMessageSpec:
    """What the user typed. Kept separate from `MessageDef` so it stays plain, saveable data."""

    name: str = ""
    category: str = "KU"
    msg_id: int = 0x0000
    length: int = 6
    content_hex: str = ""
    #: None means "decide from the length", which is what the protocol does.
    force_long: bool | None = None
    #: None means "use the addresses of the current session".
    destination_id: int | None = None
    source_id: int | None = None
    cyclic: CyclicPolicy | None = None
    #: Optional per-byte annotation. The bytes themselves always live in `content_hex`; this only
    #: says what they are called and which of them are split into bit fields, so switching between
    #: the hex, byte and bit views can never lose data.
    layout: list[CustomByteLayout] = field(default_factory=list)
    #: True when this deliberately replaces a message from the specification. Such an override is
    #: always reversible: the built-in definitions live in code and are never written over.
    overrides_builtin: bool = False
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self) -> None:
        self.msg_id = max(0, min(0xFFFF, int(self.msg_id)))
        self.length = max(0, min(MAX_CUSTOM_LENGTH, int(self.length)))
        if self.category not in CATEGORIES:
            self.category = "KU"
        if self.cyclic is not None and not isinstance(self.cyclic, CyclicPolicy):
            self.cyclic = CyclicPolicy()

    @property
    def is_long(self) -> bool:
        if self.force_long is not None:
            return self.force_long
        return self.length > MAX_SHORT_PAYLOAD

    @property
    def symbol(self) -> str:
        return f"CUSTOM_{self.category}_{self.msg_id:04X}"

    @property
    def display_name(self) -> str:
        return self.name or self.symbol

    def byte_layout(self, index: int) -> CustomByteLayout:
        """The annotation for byte `index`, creating an empty one on demand."""
        while len(self.layout) < self.length:
            self.layout.append(CustomByteLayout())
        return self.layout[index]

    def trim_layout(self) -> None:
        """Keep the annotation the same size as the message."""
        while len(self.layout) < self.length:
            self.layout.append(CustomByteLayout())
        del self.layout[self.length:]

    @property
    def has_layout(self) -> bool:
        return any(entry.name or entry.bits for entry in self.layout)

    def set_byte(self, index: int, value: int) -> None:
        data = bytearray(self.content_bytes())
        if not 0 <= index < len(data):
            return
        data[index] = int(value) & 0xFF
        self.content_hex = " ".join(f"{b:02X}" for b in data)

    def byte_value(self, index: int) -> int:
        data = self.content_bytes()
        return data[index] if 0 <= index < len(data) else 0

    def content_bytes(self) -> bytes:
        """The declared content, padded or truncated to `length`."""
        cleaned = self.content_hex.replace(" ", "").replace("\n", "").replace(",", "")
        try:
            data = bytes.fromhex(cleaned)
        except ValueError:
            data = b""
        return data[: self.length] + bytes(max(0, self.length - len(data)))


def to_message_def(spec: CustomMessageSpec) -> MessageDef:
    """Wrap a user definition as a protocol message the rest of the tool understands."""
    cyclic_default = (
        None
        if spec.cyclic is None
        else CyclicDefault(enabled=spec.cyclic.enabled, period_ms=spec.cyclic.period_ms)
    )

    return MessageDef(
        category=spec.category,
        msg_id=spec.msg_id,
        symbol=spec.symbol,
        name_key="",
        custom_name=spec.display_name,
        length=spec.length,
        fields=_build_fields(spec),
        # Nothing is known about where the payload accepts this, so do not invent restrictions;
        # `custom.unknown_to_protocol` tells the user that instead.
        allowed_modes=frozenset(OPERATIONAL_MODES),
        # An unknown MSG_ID is answered with ERR_MSG_ID, which is itself an acknowledgement.
        ack=AckBehaviour.ACK if spec.category == "KU" else AckBehaviour.NONE,
        follow_up=(),
        cyclic_default=cyclic_default,
        doc_ref="",
        custom=True,
        forced_long=spec.force_long,
        destination_override=spec.destination_id,
        source_override=spec.source_id,
    )


def from_message_def(definition, name: str = "") -> CustomMessageSpec:
    """Seed a user definition from a catalogue message, to be edited.

    Lossy on purpose, and the dialog says so: a `MessageDef` describes multi-byte integers, floats,
    enumerations and cross-field rules, while a user definition is bytes plus names. Fields that
    live inside a single byte keep their names; anything wider is named on its first byte and the
    rest is left blank rather than pretending to be understood.
    """
    from detector_scenario_tool.protocol.fields import pack_message

    try:
        content = pack_message(definition, definition.default_payload())
    except Exception:
        content = bytes(definition.length)

    spec = CustomMessageSpec(
        name=name or definition.custom_name or definition.symbol,
        category=definition.category,
        msg_id=definition.msg_id,
        length=definition.length,
        content_hex=" ".join(f"{b:02X}" for b in content),
        force_long=definition.forced_long,
        destination_id=definition.destination_override,
        source_id=definition.source_override,
        cyclic=(
            None
            if definition.cyclic_default is None
            else CyclicPolicy(
                enabled=definition.cyclic_default.enabled,
                period_ms=definition.cyclic_default.period_ms,
            )
        ),
        overrides_builtin=not definition.custom,
    )
    spec.trim_layout()

    for field_spec in definition.fields:
        if field_spec.byte_offset >= spec.length:
            continue
        entry = spec.layout[field_spec.byte_offset]

        if field_spec.is_bitfield and field_spec.byte_length == 1:
            entry.bits.append(
                CustomBitRange(
                    name=field_spec.label,
                    offset=field_spec.bit_offset,
                    length=field_spec.bit_length,
                )
            )
        elif field_spec.byte_length == 1 and not field_spec.is_bitfield:
            entry.name = field_spec.label
        elif not entry.name:
            entry.name = field_spec.label

    for entry in spec.layout:
        entry.bits.sort(key=lambda r: r.offset)

    return spec


def _uncovered_runs(covered_mask: int) -> list[tuple[int, int]]:
    """(offset, length) for each contiguous run of bits the user did not name."""
    runs: list[tuple[int, int]] = []
    offset = 0
    while offset < 8:
        if covered_mask & (1 << offset):
            offset += 1
            continue
        start = offset
        while offset < 8 and not covered_mask & (1 << offset):
            offset += 1
        runs.append((start, offset - start))
    return runs


def _build_fields(spec: CustomMessageSpec) -> tuple:
    """Turn the annotation into real fields, so a named message gets a real form everywhere.

    Without annotation the message stays one opaque hex block, which is the right default: most
    user-defined messages are one-off probes and naming every byte would be busywork.
    """
    if not spec.length:
        return ()

    if not spec.has_layout:
        return (raw("content", 0, spec.length, default=spec.content_bytes()),)

    content = spec.content_bytes()
    fields = []

    for index in range(spec.length):
        entry = spec.layout[index] if index < len(spec.layout) else CustomByteLayout()
        value = content[index]

        # An unnamed bit field conveys nothing, so it does not become a form row of its own; the
        # runs below fold those bits together. Splitting a byte and naming only what matters is
        # the normal way to use this.
        named_bits = [bit for bit in entry.bits if bit.name]

        if not named_bits:
            fields.append(
                u8(
                    f"byte_{index}",
                    index,
                    label_key="",
                    custom_label=entry.name or f"#{index}",
                    default=value,
                )
            )
            continue

        for bit_range in named_bits:
            fields.append(
                bits(
                    f"byte_{index}_bit_{bit_range.offset}",
                    index,
                    bit_range.offset,
                    bit_range.length,
                    label_key="",
                    custom_label=bit_range.name or f"#{index}.{bit_range.range_text}",
                    default=bit_range.extract(value),
                )
            )

        # Bits the user did not describe still have to be written, or packing would leave a hole.
        # Grouping them into contiguous runs keeps the form readable instead of showing eight
        # anonymous check boxes.
        covered = 0
        for bit_range in named_bits:
            covered |= bit_range.mask

        for offset, length in _uncovered_runs(covered):
            gap = CustomBitRange(offset=offset, length=length)
            fields.append(
                bits(
                    f"byte_{index}_bit_{offset}",
                    index,
                    offset,
                    length,
                    label_key="",
                    custom_label=f"#{index}.{gap.range_text}",
                    default=gap.extract(value),
                )
            )

    return tuple(fields)


def validate_spec(
        spec: CustomMessageSpec,
        others: list[CustomMessageSpec] | None = None,
) -> list[tuple[str, dict]]:
    """(code, params) for everything wrong with a definition, for the dialog and the analyzer."""
    from detector_scenario_tool.protocol import registry

    issues: list[tuple[str, dict]] = []

    existing = registry.find(spec.category, spec.msg_id)
    if existing is not None and not existing.custom and not spec.overrides_builtin:
        # Accidentally reusing a protocol identifier would silently change what every scenario
        # using it means; deliberately overriding one is a different thing and is allowed.
        issues.append(
            (
                "custom.shadows_catalogue",
                {"msg": f"0x{spec.msg_id:04X}", "symbol": existing.symbol},
            )
        )

    for other in others or []:
        if other.id != spec.id and other.category == spec.category and other.msg_id == spec.msg_id:
            issues.append(
                ("custom.duplicate_msg_id", {"msg": f"0x{spec.msg_id:04X}", "name": other.display_name})
            )
            break

    if spec.msg_id >= RESERVED_MSG_ID_START:
        # FFFEh and FFFFh are the long-message start and error frames; using them would corrupt
        # the framing rather than merely be rejected.
        issues.append(
            ("custom.reserved_msg_id", {"msg": f"0x{spec.msg_id:04X}"})
        )

    if spec.length > MAX_SHORT_PAYLOAD and spec.force_long is False:
        issues.append(
            ("custom.too_long_for_short", {"length": spec.length, "max": MAX_SHORT_PAYLOAD})
        )

    declared = len(
        bytes.fromhex(spec.content_hex.replace(" ", "").replace("\n", "").replace(",", ""))
    ) if _is_hex(spec.content_hex) else -1

    if declared < 0:
        issues.append(("custom.content_not_hex", {}))
    elif declared > spec.length:
        issues.append(("custom.content_too_long", {"actual": declared, "length": spec.length}))

    for key, value in (("destination_id", spec.destination_id), ("source_id", spec.source_id)):
        if value is not None and not 0 <= value <= 0xFFFF:
            issues.append(("custom.address_out_of_range", {"field": key, "actual": value}))

    issues.extend(_layout_issues(spec))
    return issues


def _layout_issues(spec: CustomMessageSpec) -> list[tuple[str, dict]]:
    issues: list[tuple[str, dict]] = []

    for index, entry in enumerate(spec.layout[: spec.length]):
        seen = 0
        for bit_range in entry.bits:
            if seen & bit_range.mask:
                issues.append(
                    (
                        "custom.bits_overlap",
                        {"byte": index, "range": bit_range.range_text},
                    )
                )
                break
            seen |= bit_range.mask

    return issues


def _is_hex(text: str) -> bool:
    cleaned = text.replace(" ", "").replace("\n", "").replace(",", "")
    if not cleaned:
        return True
    try:
        bytes.fromhex(cleaned)
    except ValueError:
        return False
    return True
