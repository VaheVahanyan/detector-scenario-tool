from __future__ import annotations

import json
from pathlib import Path

from detector_scenario_tool.domain.custom_messages import (
    CustomBitRange,
    CustomByteLayout,
    CustomMessageSpec,
)
from detector_scenario_tool.storage.migration import (
    CURRENT_SCHEMA_VERSION,
    PROTOCOL_VERSION,
    migrate_document,
)

#: Stamped into every saved file so a future revision can migrate without guessing.
from detector_scenario_tool.domain.scenario import (
    AckPolicy,
    CyclicPolicy,
    CommentStep,
    MessageRef,
    RetryPolicy,
    ScenarioDocument,
    ScenarioMetadata,
    SendMessageStep,
    StepKind,
    ValidationProfile,
    WaitForTsStep,
    WaitTimeStep,
)


def _message_ref_to_dict(message: MessageRef | None) -> dict | None:
    if message is None:
        return None
    return {
        "category": message.category,
        "msg_id": message.msg_id,
        "name": message.name,
    }


def _message_ref_from_dict(data: dict | None) -> MessageRef | None:
    if data is None:
        return None
    return MessageRef(
        category=data["category"],
        msg_id=data.get("msg_id"),
        name=data.get("name", ""),
    )


def _retry_policy_to_dict(retry: RetryPolicy) -> dict:
    return {
        "attempts": retry.attempts,
        "retry_delay_ms": retry.retry_delay_ms,
        "retry_on_timeout": retry.retry_on_timeout,
        "retry_on_reject": retry.retry_on_reject,
    }


def _retry_policy_from_dict(data: dict | None) -> RetryPolicy:
    data = data or {}
    return RetryPolicy(
        attempts=data.get("attempts", 1),
        retry_delay_ms=data.get("retry_delay_ms", 0),
        retry_on_timeout=data.get("retry_on_timeout", True),
        retry_on_reject=data.get("retry_on_reject", False),
    )


def _cyclic_to_dict(cyclic) -> dict | None:
    if cyclic is None:
        return None
    return {
        "enabled": cyclic.enabled,
        "period_ms": cyclic.period_ms,
        "max_repeats": cyclic.max_repeats,
    }


def _cyclic_from_dict(data: dict | None):
    if data is None:
        return None
    return CyclicPolicy(
        enabled=data.get("enabled", False),
        period_ms=data.get("period_ms", 20_000),
        max_repeats=data.get("max_repeats"),
    )


def _custom_message_to_dict(spec) -> dict:
    return {
        "id": spec.id,
        "name": spec.name,
        "category": spec.category,
        "msg_id": spec.msg_id,
        "length": spec.length,
        "content_hex": spec.content_hex,
        "force_long": spec.force_long,
        "destination_id": spec.destination_id,
        "source_id": spec.source_id,
        "cyclic": _cyclic_to_dict(spec.cyclic),
        "overrides_builtin": spec.overrides_builtin,
        "layout": [
            {
                "name": entry.name,
                "bits": [
                    {"name": b.name, "offset": b.offset, "length": b.length} for b in entry.bits
                ],
            }
            for entry in spec.layout
        ],
    }


def _custom_message_from_dict(data: dict) -> CustomMessageSpec:
    kwargs = {
        "name": data.get("name", ""),
        "category": data.get("category", "KU"),
        "msg_id": data.get("msg_id", 0),
        "length": data.get("length", 6),
        "content_hex": data.get("content_hex", ""),
        "force_long": data.get("force_long"),
        "destination_id": data.get("destination_id"),
        "source_id": data.get("source_id"),
        "cyclic": _cyclic_from_dict(data.get("cyclic")),
        "overrides_builtin": bool(data.get("overrides_builtin", False)),
        "layout": [
            CustomByteLayout(
                name=entry.get("name", ""),
                bits=[
                    CustomBitRange(
                        name=b.get("name", ""),
                        offset=b.get("offset", 0),
                        length=b.get("length", 1),
                    )
                    for b in entry.get("bits", [])
                ],
            )
            for entry in data.get("layout", [])
        ],
    }
    if data.get("id"):
        kwargs["id"] = data["id"]
    return CustomMessageSpec(**kwargs)


def save_scenario(document: ScenarioDocument, path: str | Path) -> None:
    data = {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "custom_messages": [
            _custom_message_to_dict(spec) for spec in getattr(document, "custom_messages", [])
        ],
        "suppressed_messages": [
            {"category": category, "msg_id": msg_id}
            for category, msg_id in getattr(document, "suppressed_messages", [])
        ],
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
        "steps": [],
    }

    for step in document.steps:
        if step.kind in (StepKind.SEND_KU, StepKind.SEND_KT):
            data["steps"].append(
                {
                    "id": step.id,
                    "kind": step.kind.value,
                    "title": step.title,
                    "comment": step.comment,
                    "enabled": step.enabled,
                    "message": _message_ref_to_dict(step.message),
                    "payload": dict(step.payload),
                    "ack_policy": step.ack_policy.value,
                    "ack_timeout_ms": step.ack_timeout_ms,
                    "cyclic": _cyclic_to_dict(step.cyclic),
                    "retry": _retry_policy_to_dict(step.retry),
                }
            )
        elif step.kind == StepKind.WAIT_TIME:
            data["steps"].append(
                {
                    "id": step.id,
                    "kind": step.kind.value,
                    "title": step.title,
                    "comment": step.comment,
                    "enabled": step.enabled,
                    "delay_ms": step.delay_ms,
                }
            )
        elif step.kind == StepKind.WAIT_FOR_TS:
            data["steps"].append(
                {
                    "id": step.id,
                    "kind": step.kind.value,
                    "title": step.title,
                    "comment": step.comment,
                    "enabled": step.enabled,
                    "expected": _message_ref_to_dict(step.expected),
                    "timeout_ms": step.timeout_ms,
                    "match": dict(step.match),
                    "bind_to_previous_ku": step.bind_to_previous_ku,
                    "ack_for_msg_id": step.ack_for_msg_id,
                    "require_ack_ok": step.require_ack_ok,
                }
            )
        elif step.kind == StepKind.COMMENT:
            data["steps"].append(
                {
                    "id": step.id,
                    "kind": step.kind.value,
                    "title": step.title,
                    "comment": step.comment,
                    "enabled": step.enabled,
                    "text": step.text,
                }
            )

    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_scenario(path: str | Path) -> ScenarioDocument:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    raw, migration_notes = migrate_document(raw)

    metadata_raw = raw.get("metadata", {})
    metadata = ScenarioMetadata(
        name=metadata_raw.get("name", "Untitled scenario"),
        author=metadata_raw.get("author", ""),
        description=metadata_raw.get("description", ""),
    )

    validation_raw = raw.get("validation", {})
    validation = ValidationProfile(
        safe_mode=validation_raw.get("safe_mode", False),
        strict_ack_checks=validation_raw.get("strict_ack_checks", True),
        strict_mode_transition_checks=validation_raw.get("strict_mode_transition_checks", True),
        strict_timeout_checks=validation_raw.get("strict_timeout_checks", False),
    )

    steps = []
    for item in raw.get("steps", []):
        kind = StepKind(item["kind"])

        if kind in (StepKind.SEND_KU, StepKind.SEND_KT):
            retry_raw = item.get("retry", {})

            # backward compatibility:
            # if old flat field max_attempts appears, fold it into retry.attempts
            if "attempts" not in retry_raw and "max_attempts" in item:
                retry_raw = {
                    **retry_raw,
                    "attempts": item.get("max_attempts", 1),
                }

            step = SendMessageStep(
                id=item["id"],
                kind=kind,
                title=item.get("title", ""),
                comment=item.get("comment", ""),
                enabled=bool(item.get("enabled", True)),
                message=_message_ref_from_dict(item.get("message")),
                payload=dict(item.get("payload", {})),
                ack_policy=AckPolicy(item.get("ack_policy", AckPolicy.NONE.value)),
                ack_timeout_ms=item.get("ack_timeout_ms"),
                cyclic=_cyclic_from_dict(item.get("cyclic")),
                retry=_retry_policy_from_dict(retry_raw),
            )

        elif kind == StepKind.WAIT_TIME:
            step = WaitTimeStep(
                id=item["id"],
                kind=kind,
                title=item.get("title", ""),
                comment=item.get("comment", ""),
                enabled=bool(item.get("enabled", True)),
                delay_ms=item.get("delay_ms", 1000),
            )

        elif kind == StepKind.WAIT_FOR_TS:
            step = WaitForTsStep(
                id=item["id"],
                kind=kind,
                title=item.get("title", ""),
                comment=item.get("comment", ""),
                enabled=bool(item.get("enabled", True)),
                expected=_message_ref_from_dict(item.get("expected")),
                timeout_ms=item.get("timeout_ms", 1000),
                match=dict(item.get("match", {})),
                bind_to_previous_ku=item.get("bind_to_previous_ku", False),
                ack_for_msg_id=item.get("ack_for_msg_id"),
                require_ack_ok=item.get("require_ack_ok", False),
            )

        elif kind == StepKind.COMMENT:
            step = CommentStep(
                id=item["id"],
                kind=kind,
                title=item.get("title", ""),
                comment=item.get("comment", ""),
                enabled=bool(item.get("enabled", True)),
                text=item.get("text", ""),
            )

        else:
            continue

        steps.append(step)

    return ScenarioDocument(
        schema_version=raw.get("schema_version", CURRENT_SCHEMA_VERSION),
        metadata=metadata,
        validation=validation,
        steps=steps,
        custom_messages=[
            _custom_message_from_dict(item) for item in raw.get("custom_messages", [])
        ],
        suppressed_messages=[
            (item.get("category", "KU"), item.get("msg_id", 0))
            for item in raw.get("suppressed_messages", [])
        ],
        migration_notes=migration_notes,
    )
