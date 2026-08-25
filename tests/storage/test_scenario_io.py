from __future__ import annotations

import json

import pytest

from detector_scenario_tool.domain.scenario import (
    AckPolicy,
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
from detector_scenario_tool.storage.migration import CURRENT_SCHEMA_VERSION
from detector_scenario_tool.storage.scenario_io import load_scenario, save_scenario
from message_ids import STATUS_REQ, TLM_MCILWAIN, TM_ACK


def _full_document() -> ScenarioDocument:
    return ScenarioDocument(
        schema_version=CURRENT_SCHEMA_VERSION,
        metadata=ScenarioMetadata(
            name="round trip", author="tester", description="every step kind"
        ),
        validation=ValidationProfile(safe_mode=True, strict_timeout_checks=True),
        steps=[
            SendMessageStep(
                id="s1",
                kind=StepKind.SEND_KU,
                title="status request",
                comment="hello",
                message=MessageRef(category="KU", msg_id=STATUS_REQ, name="Запрос статуса"),
                payload={},
                ack_policy=AckPolicy.EXPECT_ACK,
                ack_timeout_ms=1500,
                retry=RetryPolicy(
                    attempts=3, retry_delay_ms=250, retry_on_timeout=True, retry_on_reject=True
                ),
            ),
            WaitForTsStep(
                id="s2",
                kind=StepKind.WAIT_FOR_TS,
                expected=MessageRef(category="TS", msg_id=TM_ACK, name="Квитанция"),
                timeout_ms=1000,
                bind_to_previous_ku=True,
                ack_for_msg_id=STATUS_REQ,
                require_ack_ok=True,
            ),
            WaitTimeStep(id="s3", kind=StepKind.WAIT_TIME, delay_ms=750),
            CommentStep(id="s4", kind=StepKind.COMMENT, text="done"),
        ],
    )


def test_round_trip_preserves_every_field(tmp_path):
    original = _full_document()
    path = tmp_path / "scenario.json"

    save_scenario(original, path)
    loaded = load_scenario(path)

    assert loaded.schema_version == original.schema_version
    assert loaded.metadata == original.metadata
    assert loaded.validation == original.validation
    assert len(loaded.steps) == len(original.steps)

    for loaded_step, original_step in zip(loaded.steps, original.steps):
        assert type(loaded_step) is type(original_step)
        assert loaded_step == original_step


def test_saved_file_is_utf8_json_with_readable_russian(tmp_path):
    path = tmp_path / "scenario.json"
    save_scenario(_full_document(), path)

    raw = path.read_text(encoding="utf-8")
    assert "Запрос статуса" in raw, "names must not be \\u-escaped"
    json.loads(raw)


def test_retry_policy_is_normalised_on_load(tmp_path):
    """RetryPolicy.__post_init__ clamps; a hand-edited file must not smuggle nonsense through."""
    path = tmp_path / "scenario.json"
    save_scenario(_full_document(), path)

    data = json.loads(path.read_text(encoding="utf-8"))
    data["steps"][0]["retry"]["attempts"] = 0
    data["steps"][0]["retry"]["retry_delay_ms"] = -5
    path.write_text(json.dumps(data), encoding="utf-8")

    loaded = load_scenario(path)
    assert loaded.steps[0].retry.attempts == 1
    assert loaded.steps[0].retry.retry_delay_ms == 0


def test_missing_optional_fields_fall_back_to_defaults(tmp_path):
    path = tmp_path / "minimal.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "metadata": {"name": "minimal"},
                "validation": {},
                "steps": [
                    {"id": "s1", "kind": "wait_time", "delay_ms": 100},
                ],
            }
        ),
        encoding="utf-8",
    )

    loaded = load_scenario(path)
    assert loaded.metadata.name == "minimal"
    assert loaded.steps[0].delay_ms == 100


def test_v1_documents_are_migrated_not_silently_reinterpreted(tmp_path):
    """0100h means «Сверка времени» (6 B) in v1 and TLM_MCILWAIN (24 B) in v2.

    Loading a v1 file must not quietly turn one into the other.
    """
    path = tmp_path / "legacy.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "metadata": {"name": "legacy"},
                "validation": {},
                "steps": [
                    {
                        "id": "s1",
                        "kind": "send_kt",
                        # 0100h in v1 meant «Сверка времени», 6 bytes. It is not TLM_MCILWAIN.
                        "message": {"category": "KT", "msg_id": 0x0100, "name": "Сверка времени"},
                        "payload": {"board_time_ms": 1, "board_time_s": 2},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    loaded = load_scenario(path)
    assert loaded.schema_version >= 2
    assert loaded.migration_notes, "migration must be reported to the user"

    codes = {note.code for note in loaded.migration_notes}
    assert "migration.telemetry_command_quarantined" in codes

    # The step must not have become a telemetry-command send; it is parked as a disabled comment
    # that still carries the original JSON, with the identifier the v1 file actually used.
    step = loaded.steps[0]
    assert step.kind.value == "comment"
    assert step.enabled is False
    assert '"msg_id": 256' in step.text
