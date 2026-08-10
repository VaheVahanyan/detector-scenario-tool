"""Serialising a step's payload into message content bytes.

This used to be 432 lines of `if msg_id == …` that had to be kept in step with the payload editors
and the validators by hand. Packing is now generic: the byte layout comes from the message
definition, so a new message needs no code here at all.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from detector_scenario_tool.domain.scenario import SendMessageStep
from detector_scenario_tool.protocol import registry
from detector_scenario_tool.protocol.fields import PackingError, pack_message, unpack_message

__all__ = [
    "PackingError",
    "pack_send_message_step",
    "pack_message_payload",
    "unpack_message_payload",
    "payload_to_hex",
    "save_payload_hex_dump",
]


def pack_send_message_step(step: SendMessageStep) -> bytes:
    if step.message is None or step.message.msg_id is None:
        raise PackingError("Cannot pack step without selected message.")

    return pack_message_payload(
        category=step.message.category,
        msg_id=step.message.msg_id,
        payload=step.payload,
    )


def pack_message_payload(category: str, msg_id: int, payload: Mapping[str, Any]) -> bytes:
    spec = registry.find(category, msg_id)
    if spec is None:
        raise PackingError(f"Unknown message {category} 0x{msg_id:04X}.")

    if not spec.sendable:
        raise PackingError(
            f"{category} 0x{msg_id:04X} ({spec.symbol}) is sent by the detector, not by the tool."
        )

    return pack_message(spec, payload)


def unpack_message_payload(category: str, msg_id: int, data: bytes) -> dict[str, Any]:
    spec = registry.find(category, msg_id)
    if spec is None:
        raise PackingError(f"Unknown message {category} 0x{msg_id:04X}.")
    return unpack_message(spec, data)


def payload_to_hex(payload_bytes: bytes) -> str:
    return " ".join(f"{b:02X}" for b in payload_bytes)


def save_payload_hex_dump(
        category: str,
        msg_id: int,
        payload: Mapping[str, Any],
        path: str | Path,
) -> None:
    packed = pack_message_payload(category=category, msg_id=msg_id, payload=payload)
    data = {
        "category": category,
        "msg_id": msg_id,
        "packed_length": len(packed),
        "packed_hex": payload_to_hex(packed),
        "packed_bytes": list(packed),
    }
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
