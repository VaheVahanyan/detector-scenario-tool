"""Generated C, the packed export and the runtime contract.

The generator is deliberately lossy — only `SEND_KU`, `SEND_KT` and `WAIT_TIME` become executable
code, and repeats become a table the board services — so most of these tests are about what must
*not* silently disappear.
"""

from __future__ import annotations

import json

import pytest

from detector_scenario_tool.codegen import generate_scenario_c_files, save_generated_scenario_files
from detector_scenario_tool.domain.custom_messages import CustomMessageSpec
from detector_scenario_tool.domain.scenario import (
    AckPolicy,
    CommentStep,
    CyclicPolicy,
    MessageRef,
    ScenarioDocument,
    ScenarioMetadata,
    SendMessageStep,
    StepKind,
    ValidationProfile,
    WaitForTsStep,
    WaitTimeStep,
)
from detector_scenario_tool.protocol import registry
from detector_scenario_tool.services.custom_message_sync import CustomMessageSync
from detector_scenario_tool.storage.packed_export import build_packed_scenario_export


def _send(category: str, msg_id: int, sid: str = "s", **kw) -> SendMessageStep:
    spec = registry.find(category, msg_id)
    return SendMessageStep(
        id=sid,
        kind=StepKind.SEND_KU if category == "KU" else StepKind.SEND_KT,
        message=MessageRef(category=category, msg_id=msg_id, name=""),
        payload=dict(kw.pop("payload", None) or spec.default_payload()),
        ack_policy=kw.pop(
            "ack_policy", AckPolicy.EXPECT_ACK if category == "KU" else AckPolicy.NONE
        ),
        ack_timeout_ms=kw.pop("ack_timeout_ms", 1000 if category == "KU" else None),
        **kw,
    )


def _document(*steps, custom_messages=None) -> ScenarioDocument:
    return ScenarioDocument(
        schema_version=2,
        metadata=ScenarioMetadata(name="generated"),
        validation=ValidationProfile(),
        steps=list(steps),
        custom_messages=list(custom_messages or []),
    )


@pytest.fixture
def custom_sync():
    sync = CustomMessageSync()
    yield sync
    sync.clear()


class TestSourceStructure:
    def test_a_send_becomes_a_runtime_call(self):
        files = generate_scenario_c_files(_document(_send("KU", 0x0001)))
        assert "scenario_send_ku(0x0001u," in files.source_text

    def test_a_telemetry_command_uses_its_own_entry_point(self):
        files = generate_scenario_c_files(_document(_send("KT", 0x0100)))
        assert "scenario_send_kt(0x0100u," in files.source_text

    def test_a_pause_becomes_a_wait(self):
        files = generate_scenario_c_files(
            _document(WaitTimeStep(id="w", kind=StepKind.WAIT_TIME, delay_ms=2500))
        )
        assert "scenario_wait_ms(2500u)" in files.source_text

    def test_a_wait_for_message_is_left_to_the_runtime(self):
        """The board owns response waiting; exporting it as code would duplicate that."""
        step = WaitForTsStep(
            id="w",
            kind=StepKind.WAIT_FOR_TS,
            expected=MessageRef(category="TS", msg_id=0x0201, name=""),
        )
        files = generate_scenario_c_files(_document(step))

        assert "0x0201" in files.source_text
        assert "scenario_send" not in files.source_text

    def test_a_disabled_step_is_not_executed_but_is_recorded(self):
        step = _send("KU", 0x0001)
        step.enabled = False
        files = generate_scenario_c_files(_document(step))

        assert "scenario_send_ku" not in files.source_text
        assert "disabled" in files.meta_text

    def test_a_comment_never_becomes_code(self):
        files = generate_scenario_c_files(
            _document(CommentStep(id="c", kind=StepKind.COMMENT, text="note"))
        )
        assert "scenario_send" not in files.source_text

    def test_an_empty_scenario_still_compiles_to_something_valid(self):
        files = generate_scenario_c_files(_document())
        assert "scenario_run_once" in files.source_text
        assert "return SCENARIO_OK;" in files.source_text


class TestCyclicTable:
    def test_a_repeating_send_reaches_the_table(self):
        step = _send("KT", 0x0100, cyclic=CyclicPolicy(enabled=True, period_ms=20_000))
        files = generate_scenario_c_files(_document(step))

        assert "{ 0x0100u, 20000u, 0u }" in files.source_text
        assert "scenario_cyclic_count = 1u" in files.source_text

    def test_the_table_is_declared_in_the_header(self):
        files = generate_scenario_c_files(_document())
        assert "extern const scenario_cyclic_t scenario_cyclic_table[]" in files.header_text
        assert "extern const uint32_t          scenario_cyclic_count" in files.header_text

    def test_max_repeats_is_carried_over(self):
        step = _send(
            "KT", 0x0100, cyclic=CyclicPolicy(enabled=True, period_ms=5000, max_repeats=4)
        )
        files = generate_scenario_c_files(_document(step))
        assert "{ 0x0100u, 5000u, 4u }" in files.source_text

    def test_an_empty_table_is_still_valid_c(self):
        """A zero-length array is not legal C, so the count is what says "none"."""
        files = generate_scenario_c_files(_document(_send("KU", 0x0001)))

        assert "scenario_cyclic_table[] =" in files.source_text
        assert "scenario_cyclic_count = 0u" in files.source_text
        assert "{ 0u, 0u, 0u }" in files.source_text

    def test_a_single_shot_stays_out_of_the_table(self):
        step = _send("KT", 0x0100, cyclic=CyclicPolicy(enabled=False))
        files = generate_scenario_c_files(_document(step))
        assert "scenario_cyclic_count = 0u" in files.source_text

    def test_a_disabled_repeating_step_stays_out(self):
        step = _send("KT", 0x0100, cyclic=CyclicPolicy(enabled=True, period_ms=1000))
        step.enabled = False
        files = generate_scenario_c_files(_document(step))
        assert "scenario_cyclic_count = 0u" in files.source_text

    def test_the_repeat_is_still_sent_once_by_the_linear_sequence(self):
        """The table is the cadence; the first send is part of the scenario."""
        step = _send("KT", 0x0100, cyclic=CyclicPolicy(enabled=True, period_ms=1000))
        files = generate_scenario_c_files(_document(step))
        assert "scenario_send_kt(0x0100u," in files.source_text


class TestCustomMessages:
    def test_a_user_defined_message_is_emitted_as_raw_bytes(self, custom_sync):
        spec = CustomMessageSpec(name="Test", msg_id=0x0F01, length=4, content_hex="DE AD BE EF")
        custom_sync.apply([spec])

        files = generate_scenario_c_files(_document(_send("KU", 0x0F01)))

        assert "scenario_send_ku(0x0F01u," in files.source_text
        assert "0xDE, 0xAD, 0xBE, 0xEF" in files.source_text

    def test_it_is_marked_in_the_metadata(self, custom_sync):
        custom_sync.apply([CustomMessageSpec(msg_id=0x0F01, length=4, content_hex="01020304")])
        files = generate_scenario_c_files(_document(_send("KU", 0x0F01)))

        assert "custom=true" in files.meta_text

    def test_a_catalogue_message_is_not_marked(self):
        files = generate_scenario_c_files(_document(_send("KU", 0x0001)))
        assert "custom=true" not in files.meta_text


class TestMetadata:
    def test_the_cyclic_period_is_recorded(self):
        step = _send("KT", 0x0100, cyclic=CyclicPolicy(enabled=True, period_ms=20_000))
        files = generate_scenario_c_files(_document(step))

        assert "cyclic=true" in files.meta_text
        assert "cyclic_period_ms=20000" in files.meta_text

    def test_a_non_repeating_step_says_so(self):
        files = generate_scenario_c_files(_document(_send("KU", 0x0001)))
        assert "cyclic=false" in files.meta_text


class TestContract:
    def test_the_payload_limit_matches_the_largest_message(self):
        """ТС «Результаты теста ППЗУ» is 6146 bytes, not the 6144 of the previous revision."""
        contract = generate_scenario_c_files(_document()).contract_text
        assert "SCENARIO_MAX_PAYLOAD_LEN 6146u" in contract

    def test_it_documents_the_cyclic_table(self):
        contract = generate_scenario_c_files(_document()).contract_text
        assert "scenario_cyclic_table" in contract

    def test_it_documents_user_defined_messages(self):
        contract = generate_scenario_c_files(_document()).contract_text
        assert "User-defined messages" in contract

    def test_it_documents_the_current_log_format(self):
        contract = generate_scenario_c_files(_document()).contract_text
        assert "DSTLOG|v=2" in contract
        assert "src=host" in contract

    def test_it_states_that_response_waiting_is_not_exported(self):
        contract = generate_scenario_c_files(_document()).contract_text
        assert "WAIT_FOR_TS" in contract


class TestFileOutput:
    def test_all_four_files_are_written(self, tmp_path):
        files = save_generated_scenario_files(_document(_send("KU", 0x0001)), tmp_path)

        for name in (
            files.header_filename,
            files.source_filename,
            files.meta_filename,
            files.contract_filename,
        ):
            assert (tmp_path / name).exists()

    def test_the_source_includes_its_own_header(self, tmp_path):
        files = save_generated_scenario_files(_document(), tmp_path)
        assert f'#include "{files.header_filename}"' in files.source_text


class TestPackedExport:
    def test_it_stamps_the_schema_and_protocol_version(self):
        export = build_packed_scenario_export(_document())

        assert export["schema_version"] == 2
        assert export["protocol_version"] == "CAN_v2"

    def test_packed_bytes_are_included(self):
        export = build_packed_scenario_export(_document(_send("KU", 0x0001)))
        packed = export["steps"][0]["packed"]

        assert packed["payload_length_actual"] == 6
        assert packed["hex"] == "AA AA AA AA AA AA"
        assert packed["pack_ok"] is True

    def test_a_packing_failure_is_reported_rather_than_hidden(self):
        step = _send("KU", 0x0002, payload={"board_time_ms": 99_999, "board_time_s": 0})
        export = build_packed_scenario_export(_document(step))
        packed = export["steps"][0]["packed"]

        assert packed["pack_ok"] is False
        assert packed["error"]

    def test_repeats_are_listed_separately(self):
        step = _send("KT", 0x0100, cyclic=CyclicPolicy(enabled=True, period_ms=20_000))
        export = build_packed_scenario_export(_document(step))

        assert export["cyclic"] == [
            {
                "step_index": 0,
                "category": "KT",
                "msg_id": 0x0100,
                "msg_id_hex": "0x0100",
                "period_ms": 20_000,
                "max_repeats": None,
            }
        ]

    def test_user_defined_messages_travel_with_the_export(self):
        """A consumer has nowhere else to look them up."""
        spec = CustomMessageSpec(name="X", msg_id=0x0F01, length=4, content_hex="DE AD BE EF")
        export = build_packed_scenario_export(_document(custom_messages=[spec]))

        assert len(export["custom_messages"]) == 1
        assert export["custom_messages"][0]["msg_id_hex"] == "0x0F01"
        assert export["custom_messages"][0]["content_hex"] == "DE AD BE EF"

    def test_migration_notes_are_carried_over(self):
        document = _document()
        document.migration_notes = [
            type("Note", (), {"code": "migration.upgraded", "step_index": None, "params": {}})()
        ]
        export = build_packed_scenario_export(document)

        assert export["migration_notes"][0]["code"] == "migration.upgraded"

    def test_the_export_is_json_serialisable(self):
        spec = CustomMessageSpec(msg_id=0x0F01, length=2, content_hex="0102")
        document = _document(
            _send("KU", 0x0001),
            _send("KT", 0x0100, cyclic=CyclicPolicy(enabled=True, period_ms=1000)),
            custom_messages=[spec],
        )
        json.dumps(build_packed_scenario_export(document), ensure_ascii=False)
