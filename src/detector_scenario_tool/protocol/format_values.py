"""Rendering a field value for display.

Shared by the scenario table, the log decoder and the inspector so a bank selector reads
"NAND2" everywhere rather than "2" in one place and "nand2" in another.
"""

from __future__ import annotations

from typing import Any

from detector_scenario_tool.i18n import tr
from detector_scenario_tool.protocol.fields import FieldKind, FieldSpec


def format_field_value(field_spec: FieldSpec, value: Any) -> str:
    if field_spec.choices:
        label_key = field_spec.choices.get(value)
        return tr(label_key) if label_key else str(value)

    if field_spec.kind is FieldKind.FLOAT:
        return f"{float(value):.6g}"

    if field_spec.kind is FieldKind.RAW:
        raw = value if isinstance(value, (bytes, bytearray)) else b""
        head = " ".join(f"{b:02X}" for b in raw[:8])
        return f"{head}…" if len(raw) > 8 else head

    if field_spec.is_bitfield and field_spec.bit_length == 1:
        return tr("value.yes") if value else tr("value.no")

    return str(value)
