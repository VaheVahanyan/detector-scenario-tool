from __future__ import annotations

import json
from pathlib import Path

from detector_scenario_tool.domain.scenario import (
    CommentStep,
    ScenarioDocument,
    SendMessageStep,
    WaitForTsStep,
    WaitTimeStep,
)
from detector_scenario_tool.protocol.message_lengths import get_expected_message_length
from detector_scenario_tool.protocol.packers import pack_send_message_step, payload_to_hex
from detector_scenario_tool.storage.migration import CURRENT_SCHEMA_VERSION
from detector_scenario_tool.storage.scenario_io import PROTOCOL_VERSION


def build_packed_scenario_export(document: ScenarioDocument) -> dict:
    steps = []

    for step in document.steps:
        if isinstance(step, SendMessageStep):
            packed_bytes = None
            packed_hex = None
            packed_length = None
            packing_error = None
            pack_ok = False
            expected_length = None
            msg_id_hex = None

            if step.message is not None and step.message.msg_id is not None:
                expected_length = get_expected_message_length(
                    step.message.category,
                    step.message.msg_id,
                )
                msg_id_hex = f"0x{step.message.msg_id:04X}"

            try:
                packed = pack_send_message_step(step)
                packed_bytes = list(packed)
                packed_hex = payload_to_hex(packed)
                packed_length = len(packed)
                pack_ok = (
                        expected_length is None or packed_length == expected_length
                )
            except Exception as exc:
                packing_error = str(exc)
                pack_ok = False

            steps.append(
                {
                    "id": step.id,
                    "kind": step.kind.value,
                    "title": step.title,
                    "comment": step.comment,
                    "enabled": step.enabled,
                    "message": None if step.message is None else {
                        "category": step.message.category,
                        "msg_id": step.message.msg_id,
                        "msg_id_hex": msg_id_hex,
                        "name": step.message.name,
                    },
                    "payload": dict(step.payload),
                    "ack_policy": step.ack_policy.value,
                    "ack_timeout_ms": step.ack_timeout_ms,
                    "cyclic": None if step.cyclic is None else {
                        "enabled": step.cyclic.enabled,
                        "period_ms": step.cyclic.period_ms,
                        "max_repeats": step.cyclic.max_repeats,
                    },
                    "retry": {
                        "attempts": step.retry.attempts,
                        "retry_delay_ms": step.retry.retry_delay_ms,
                        "retry_on_timeout": step.retry.retry_on_timeout,
                        "retry_on_reject": step.retry.retry_on_reject,
                    },
                    "packed": {
                        "payload_length_expected": expected_length,
                        "payload_length_actual": packed_length,
                        "pack_ok": pack_ok,
                        "bytes": packed_bytes,
                        "hex": packed_hex,
                        "error": packing_error,
                    },
                }
            )

        elif isinstance(step, WaitTimeStep):
            steps.append(
                {
                    "id": step.id,
                    "kind": step.kind.value,
                    "title": step.title,
                    "comment": step.comment,
                    "enabled": step.enabled,
                    "delay_ms": step.delay_ms,
                }
            )

        elif isinstance(step, WaitForTsStep):
            steps.append(
                {
                    "id": step.id,
                    "kind": step.kind.value,
                    "title": step.title,
                    "comment": step.comment,
                    "enabled": step.enabled,
                    "expected": None if step.expected is None else {
                        "category": step.expected.category,
                        "msg_id": step.expected.msg_id,
                        "msg_id_hex": None if step.expected.msg_id is None else f"0x{step.expected.msg_id:04X}",
                        "name": step.expected.name,
                    },
                    "timeout_ms": step.timeout_ms,
                    "match": dict(step.match),
                    "bind_to_previous_ku": step.bind_to_previous_ku,
                    "ack_for_msg_id": step.ack_for_msg_id,
                    "require_ack_ok": step.require_ack_ok,
                }
            )

        elif isinstance(step, CommentStep):
            steps.append(
                {
                    "id": step.id,
                    "kind": step.kind.value,
                    "title": step.title,
                    "comment": step.comment,
                    "enabled": step.enabled,
                    "text": step.text,
                }
            )

    return {
        "schema_version": CURRENT_SCHEMA_VERSION,
        # Board tooling consuming this needs to know which protocol revision produced the bytes.
        "protocol_version": PROTOCOL_VERSION,
        "metadata": {
            "name": document.metadata.name,
            "author": document.metadata.author,
            "description": document.metadata.description,
        },
        "validation": {
            "safe_mode": document.validation.safe_mode,
            "strict_ack_checks": document.validation.strict_ack_checks,
            "strict_mode_transition_checks": document.validation.strict_mode_transition_checks,
            "strict_timeout_checks": document.validation.strict_timeout_checks,
        },
        "steps": steps,
        # Messages the scenario defines itself; a consumer cannot look these up anywhere else.
        "custom_messages": [
            {
                "id": spec.id,
                "name": spec.name,
                "category": spec.category,
                "msg_id": spec.msg_id,
                "msg_id_hex": f"0x{spec.msg_id:04X}",
                "length": spec.length,
                "is_long": spec.is_long,
                "content_hex": payload_to_hex(spec.content_bytes()),
                "destination_id": spec.destination_id,
                "source_id": spec.source_id,
            }
            for spec in getattr(document, "custom_messages", [])
        ],
        # Everything a schema upgrade could not carry over, so the loss is visible in the export
        # rather than only in the UI that produced it.
        "migration_notes": [
            {"code": note.code, "step_index": note.step_index, "params": dict(note.params)}
            for note in getattr(document, "migration_notes", [])
        ],
        "cyclic": [
            {
                "step_index": index,
                "category": step.message.category,
                "msg_id": step.message.msg_id,
                "msg_id_hex": f"0x{step.message.msg_id:04X}",
                "period_ms": step.cyclic.period_ms,
                "max_repeats": step.cyclic.max_repeats,
            }
            for index, step in enumerate(document.steps)
            if isinstance(step, SendMessageStep)
            and step.repeats
            and step.message is not None
            and step.message.msg_id is not None
        ],
    }


def save_packed_scenario_export(document: ScenarioDocument, path: str | Path) -> None:
    data = build_packed_scenario_export(document)
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
