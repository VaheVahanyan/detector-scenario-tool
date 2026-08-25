"""Self-consistency of the declarative message definitions.

This replaces the old "seven parallel tables" hazard: a message is described once, and these tests
check that the one description is complete and internally coherent. Everything else — catalogue,
lengths, packer, editor, validator, decoder — is derived from it.
"""

from __future__ import annotations

import pytest

from detector_scenario_tool.i18n.manager import _TRANSLATIONS
from detector_scenario_tool.protocol import registry
from detector_scenario_tool.protocol.fields import (
    AckBehaviour,
    FieldKind,
    describe_layout,
    iter_covered_bytes,
    pack_message,
    unpack_message,
    validate_payload,
)

ALL = registry.all_messages()
SENDABLE = [spec for spec in ALL if spec.sendable]
_ids = [f"{s.category}-{s.symbol}" for s in ALL]
_send_ids = [f"{s.category}-{s.symbol}" for s in SENDABLE]


@pytest.mark.parametrize("spec", ALL, ids=_ids)
def test_fields_cover_every_byte_exactly_once(spec):
    """No gaps and no overlaps: pack_message refuses to leave a byte undescribed."""
    assert set(iter_covered_bytes(spec)) == set(range(spec.length))


@pytest.mark.parametrize("spec", ALL, ids=_ids)
def test_no_field_runs_past_the_end(spec):
    for field_spec in spec.fields:
        end = field_spec.byte_offset + field_spec.byte_length
        assert end <= spec.length, f"{field_spec.key} ends at {end}, message is {spec.length}"


@pytest.mark.parametrize("spec", ALL, ids=_ids)
def test_bitfields_fit_their_word(spec):
    for field_spec in spec.fields:
        if not field_spec.is_bitfield:
            continue
        width = field_spec.byte_length * 8
        assert field_spec.bit_offset + field_spec.bit_length <= width, field_spec.key


@pytest.mark.parametrize("spec", ALL, ids=_ids)
def test_bitfields_sharing_a_word_do_not_overlap(spec):
    used: dict[tuple[int, int], int] = {}
    for field_spec in spec.fields:
        if not field_spec.is_bitfield:
            continue
        key = (field_spec.byte_offset, field_spec.byte_length)
        mask = ((1 << field_spec.bit_length) - 1) << field_spec.bit_offset
        assert not (used.get(key, 0) & mask), f"{spec.symbol}: {field_spec.key} overlaps"
        used[key] = used.get(key, 0) | mask


@pytest.mark.parametrize("spec", ALL, ids=_ids)
def test_payload_keys_are_unique(spec):
    keys = [f.key for f in spec.fields]
    assert len(keys) == len(set(keys))


@pytest.mark.parametrize("spec", ALL, ids=_ids)
def test_every_field_label_is_translated(spec):
    for field_spec in spec.fields:
        assert field_spec.label_key in _TRANSLATIONS["ru"], field_spec.key
        assert field_spec.label_key in _TRANSLATIONS["en"], field_spec.key


@pytest.mark.parametrize("spec", ALL, ids=_ids)
def test_every_choice_label_is_translated(spec):
    for field_spec in spec.fields:
        for label_key in (field_spec.choices or {}).values():
            assert label_key in _TRANSLATIONS["ru"], label_key
            assert label_key in _TRANSLATIONS["en"], label_key


@pytest.mark.parametrize("spec", ALL, ids=_ids)
def test_message_name_is_translated(spec):
    assert spec.name_key in _TRANSLATIONS["ru"]
    assert spec.name_key in _TRANSLATIONS["en"]


@pytest.mark.parametrize("spec", ALL, ids=_ids)
def test_message_cites_the_specification(spec):
    assert spec.doc_ref, f"{spec.symbol} has no doc_ref"


@pytest.mark.parametrize("spec", SENDABLE, ids=_send_ids)
def test_default_payload_packs_to_the_declared_length(spec):
    assert len(pack_message(spec, spec.default_payload())) == spec.length


@pytest.mark.parametrize("spec", SENDABLE, ids=_send_ids)
def test_default_payload_is_valid(spec):
    assert validate_payload(spec, spec.default_payload()) == []


@pytest.mark.parametrize("spec", SENDABLE, ids=_send_ids)
def test_pack_unpack_round_trip(spec):
    payload = spec.default_payload()
    decoded = unpack_message(spec, pack_message(spec, payload))

    for field_spec in spec.editable_fields:
        if field_spec.kind is FieldKind.RAW:
            continue
        expected = payload[field_spec.key]
        actual = decoded[field_spec.key]
        if field_spec.kind is FieldKind.FLOAT:
            assert actual == pytest.approx(expected, abs=1e-6), field_spec.key
        else:
            assert actual == expected, field_spec.key


@pytest.mark.parametrize("spec", ALL, ids=_ids)
def test_reserved_fields_are_not_editable(spec):
    """Reserved bits and AAh fillers are pinned by the document, so they never enter a payload."""
    for field_spec in spec.fields:
        if field_spec.fixed_value is not None:
            assert not field_spec.editable, field_spec.key
    assert all(f.fixed_value is None for f in spec.editable_fields)


@pytest.mark.parametrize("spec", ALL, ids=_ids)
def test_short_messages_use_the_documents_byte_numbering(spec):
    """Short-message content is numbered from byte 2 in the protocol (UniCAN MSG_ID occupies 0-1)."""
    expected_origin = 0 if spec.length > 6 else 2
    assert spec.content_origin == expected_origin

    layout = describe_layout(spec)
    if not layout:
        # v2.1 gives four commands and the version query no content whatsoever.
        assert spec.length == 0
        return
    assert layout[0][0] == expected_origin


class TestAckBehaviour:
    def test_control_commands_are_acknowledged(self):
        for spec in registry.by_category("KU"):
            assert spec.ack is not AckBehaviour.NONE, spec.symbol

    def test_telemetry_commands_are_not(self):
        for spec in registry.by_category("KT"):
            assert spec.ack is AckBehaviour.NONE, spec.symbol

    def test_every_acknowledged_command_lists_the_ack_as_a_response(self):
        for spec in registry.by_category("KU"):
            ack_id = registry.by_symbol("TM_ACK").msg_id
            assert any(r.is_ack and r.msg_id == ack_id for r in spec.follow_up), spec.symbol

    def test_follow_up_responses_are_known_telemetry_messages(self):
        known = {spec.msg_id for spec in registry.by_category("TS")}
        for spec in ALL:
            for response in spec.follow_up:
                assert response.category == "TS"
                assert response.msg_id in known, f"{spec.symbol} -> 0x{response.msg_id:04X}"


class TestRegistry:
    def test_lookup_by_symbol_and_by_id_agree(self):
        for spec in ALL:
            assert registry.by_symbol(spec.symbol) is spec
            assert registry.find(spec.category, spec.msg_id) is spec

    def test_symbols_are_unique(self):
        symbols = [spec.symbol for spec in ALL]
        assert len(symbols) == len(set(symbols))

    def test_runtime_registration_and_removal(self):
        """The manual command builder (phase 7) depends on this working."""
        from detector_scenario_tool.protocol.definitions.builders import raw
        from detector_scenario_tool.protocol.fields import MessageDef

        custom = MessageDef(
            category="KU",
            msg_id=0x0FFF,
            symbol="CUSTOM_TEST",
            name_key="msg.cmd_telem_req",
            length=6,
            fields=(raw("content", 0, 6),),
            doc_ref="test",
        )
        try:
            registry.register(custom)
            assert registry.find("KU", 0x0FFF) is custom
            packed = pack_message(custom, {"content": "01 02 03"})
            assert packed == bytes([1, 2, 3, 0, 0, 0])
        finally:
            registry.unregister("KU", 0x0FFF)

        assert registry.find("KU", 0x0FFF) is None

    def test_registering_a_duplicate_is_refused(self):
        existing = registry.by_symbol("CMD_STATUS_REQ")
        with pytest.raises(ValueError):
            registry.register(existing)
