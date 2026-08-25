"""User-defined messages.

A custom message is an ordinary `MessageDef` with one `raw` field, so the value of these tests is
proving that the rest of the stack needs no special case for it.
"""

from __future__ import annotations

import pytest

from detector_scenario_tool.domain.custom_messages import (
    MAX_CUSTOM_LENGTH,
    CustomMessageSpec,
    to_message_def,
    validate_spec,
)
from detector_scenario_tool.domain.scenario import CyclicPolicy
from detector_scenario_tool.protocol import registry
from detector_scenario_tool.protocol.fields import pack_message
from detector_scenario_tool.services.custom_message_sync import CustomMessageSync
from detector_scenario_tool.transport.unican import Reassembler, UniCanMessage, encode
from message_ids import STATUS_REQ, TLM_MCILWAIN


@pytest.fixture
def sync():
    s = CustomMessageSync()
    yield s
    s.clear()


class TestSpec:
    def test_short_or_long_follows_the_length(self):
        assert not CustomMessageSpec(length=6).is_long
        assert CustomMessageSpec(length=7).is_long

    def test_framing_can_be_forced(self):
        assert CustomMessageSpec(length=2, force_long=True).is_long
        assert not CustomMessageSpec(length=2, force_long=False).is_long

    def test_content_is_padded_to_the_declared_length(self):
        spec = CustomMessageSpec(length=6, content_hex="01 02")
        assert spec.content_bytes() == bytes([1, 2, 0, 0, 0, 0])

    def test_content_is_truncated_to_the_declared_length(self):
        spec = CustomMessageSpec(length=2, content_hex="01 02 03 04")
        assert spec.content_bytes() == bytes([1, 2])

    def test_unparsable_content_yields_zeros_rather_than_raising(self):
        assert CustomMessageSpec(length=3, content_hex="zz").content_bytes() == bytes(3)

    def test_length_is_clamped(self):
        assert CustomMessageSpec(length=99_999).length == MAX_CUSTOM_LENGTH
        assert CustomMessageSpec(length=-5).length == 0

    def test_the_name_falls_back_to_the_symbol(self):
        spec = CustomMessageSpec(msg_id=0x0FFF)
        assert spec.display_name == "CUSTOM_KU_0FFF"


class TestValidation:
    def test_a_plain_definition_is_clean(self):
        assert validate_spec(CustomMessageSpec(msg_id=0x0FFF, length=6, content_hex="AA")) == []

    @pytest.mark.parametrize("msg_id", [0xFFFE, 0xFFFF])
    def test_the_framing_identifiers_are_refused(self, msg_id):
        """FFFEh starts a long message and FFFFh is an error frame — these break the framing."""
        codes = [code for code, _ in validate_spec(CustomMessageSpec(msg_id=msg_id))]
        assert "custom.unusable_msg_id" in codes

    @pytest.mark.parametrize("msg_id", [0xFF00, 0xFFE5, 0xFFFD])
    def test_the_rest_of_the_reserved_band_only_warns(self, msg_id):
        """v2.1 allocates FFE0h/FFE1h from the band, so it cannot be a refusal any more — but a
        hand-written definition there may still collide with something the bus vendor uses.
        """
        codes = [code for code, _ in validate_spec(CustomMessageSpec(msg_id=msg_id))]
        assert codes == ["custom.reserved_msg_id"]

    def test_a_long_payload_forced_short_is_refused(self):
        spec = CustomMessageSpec(length=10, force_long=False)
        codes = [code for code, _ in validate_spec(spec)]
        assert "custom.too_long_for_short" in codes

    def test_bad_hex_is_reported(self):
        codes = [code for code, _ in validate_spec(CustomMessageSpec(content_hex="nope"))]
        assert "custom.content_not_hex" in codes

    def test_content_longer_than_the_length_is_reported(self):
        spec = CustomMessageSpec(length=2, content_hex="01 02 03")
        codes = [code for code, _ in validate_spec(spec)]
        assert "custom.content_too_long" in codes


class TestConversion:
    def test_it_becomes_a_message_definition(self):
        spec = CustomMessageSpec(name="Test", msg_id=0x0FFF, length=6, content_hex="01 02 03")
        definition = to_message_def(spec)

        assert definition.custom is True
        assert definition.custom_name == "Test"
        assert definition.length == 6
        assert [f.key for f in definition.editable_fields] == ["content"]

    def test_it_packs_through_the_ordinary_packer(self):
        spec = CustomMessageSpec(msg_id=0x0FFF, length=6, content_hex="01 02 03")
        definition = to_message_def(spec)

        packed = pack_message(definition, {"content": spec.content_bytes()})
        assert packed == bytes([1, 2, 3, 0, 0, 0])

    def test_forced_framing_survives_the_conversion(self):
        definition = to_message_def(CustomMessageSpec(length=2, force_long=True))
        assert definition.is_long is True

    def test_cyclic_policy_survives_the_conversion(self):
        spec = CustomMessageSpec(cyclic=CyclicPolicy(enabled=True, period_ms=3000))
        definition = to_message_def(spec)

        assert definition.cyclic_default is not None
        assert definition.cyclic_default.period_ms == 3000

    def test_a_custom_message_frames_over_unican(self):
        spec = CustomMessageSpec(msg_id=0x0FFF, length=10, content_hex="01" * 10)
        frames = encode(spec.msg_id, spec.content_bytes(), destination=0x1E, source=0x05)

        reassembler = Reassembler()
        message = [reassembler.feed(f) for f in frames][-1]

        assert isinstance(message, UniCanMessage)
        assert message.payload == spec.content_bytes()


class TestRegistrySync:
    def test_a_definition_becomes_visible_to_the_catalogue(self, sync):
        sync.apply([CustomMessageSpec(name="X", msg_id=0x0FFF, length=6)])

        found = registry.find("KU", 0x0FFF)
        assert found is not None
        assert found.custom_name == "X"

    def test_applying_again_withdraws_the_previous_set(self, sync):
        sync.apply([CustomMessageSpec(msg_id=0x0FFF, length=6)])
        sync.apply([CustomMessageSpec(msg_id=0x0FFE, length=6)])

        assert registry.find("KU", 0x0FFF) is None
        assert registry.find("KU", 0x0FFE) is not None

    def test_clear_removes_everything(self, sync):
        sync.apply([CustomMessageSpec(msg_id=0x0FFF, length=6)])
        sync.clear()

        assert registry.find("KU", 0x0FFF) is None

    def test_a_catalogue_message_cannot_be_shadowed(self, sync):
        """Redefining CMD_STATUS_REQ would silently change what every existing scenario means."""
        rejected = sync.apply([CustomMessageSpec(msg_id=STATUS_REQ, length=6)])

        assert len(rejected) == 1
        assert registry.find("KU", STATUS_REQ).symbol == "CMD_STATUS_REQ"

    def test_the_mode_matrix_is_refreshed(self, sync):
        from detector_scenario_tool.validation.mode_analyzer import ALLOWED_KU_BY_MODE
        from detector_scenario_tool.protocol.modes import Mode

        sync.apply([CustomMessageSpec(msg_id=0x0FFF, length=6)])
        assert 0x0FFF in ALLOWED_KU_BY_MODE[Mode.DUTY]

        sync.clear()
        assert 0x0FFF not in ALLOWED_KU_BY_MODE[Mode.DUTY]


class TestPersistence:
    def test_round_trip(self, tmp_path):
        from detector_scenario_tool.domain.scenario import (
            ScenarioDocument,
            ScenarioMetadata,
            ValidationProfile,
        )
        from detector_scenario_tool.storage.scenario_io import load_scenario, save_scenario

        spec = CustomMessageSpec(
            name="Проба",
            category="KT",
            msg_id=0x0FFE,
            length=4,
            content_hex="DE AD BE EF",
            force_long=True,
            destination_id=0x09,
            source_id=0x05,
            cyclic=CyclicPolicy(enabled=True, period_ms=2000),
        )
        document = ScenarioDocument(
            schema_version=2,
            metadata=ScenarioMetadata(name="custom"),
            validation=ValidationProfile(),
            steps=[],
            custom_messages=[spec],
        )

        path = tmp_path / "custom.json"
        save_scenario(document, path)
        loaded = load_scenario(path)

        assert len(loaded.custom_messages) == 1
        restored = loaded.custom_messages[0]
        assert restored.id == spec.id
        assert restored.name == "Проба"
        assert restored.category == "KT"
        assert restored.msg_id == 0x0FFE
        assert restored.force_long is True
        assert restored.destination_id == 0x09
        assert restored.cyclic.period_ms == 2000


class TestIdentifierValidity:
    def test_a_catalogue_identifier_is_refused(self):
        """Redefining CMD_STATUS_REQ would change what every scenario using it means."""
        issues = dict(validate_spec(CustomMessageSpec(category="KU", msg_id=STATUS_REQ)))

        assert "custom.shadows_catalogue" in issues
        assert issues["custom.shadows_catalogue"]["symbol"] == "CMD_STATUS_REQ"

    def test_a_free_identifier_is_accepted(self):
        codes = [code for code, _ in validate_spec(CustomMessageSpec(msg_id=0x0FFF))]
        assert "custom.shadows_catalogue" not in codes

    def test_the_same_identifier_in_another_category_is_free(self):
        """КУ and КТ are separate spaces; 0100h is a КТ and says nothing about КУ 0100h."""
        codes = [code for code, _ in validate_spec(CustomMessageSpec(category="KU", msg_id=TLM_MCILWAIN))]
        assert "custom.shadows_catalogue" not in codes

    def test_a_duplicate_among_user_definitions_is_reported(self):
        first = CustomMessageSpec(name="Первая", msg_id=0x0FFF)
        second = CustomMessageSpec(name="Вторая", msg_id=0x0FFF)

        issues = dict(validate_spec(second, others=[first]))

        assert "custom.duplicate_msg_id" in issues
        assert issues["custom.duplicate_msg_id"]["name"] == "Первая"

    def test_a_definition_does_not_collide_with_itself(self):
        spec = CustomMessageSpec(msg_id=0x0FFF)
        codes = [code for code, _ in validate_spec(spec, others=[spec])]

        assert "custom.duplicate_msg_id" not in codes

    def test_overlapping_bit_fields_are_reported(self):
        from detector_scenario_tool.domain.custom_messages import CustomBitRange, CustomByteLayout

        spec = CustomMessageSpec(msg_id=0x0FFF, length=1)
        spec.trim_layout()
        spec.layout[0] = CustomByteLayout(
            bits=[
                CustomBitRange(name="A", offset=0, length=3),
                CustomBitRange(name="B", offset=2, length=2),
            ]
        )

        codes = [code for code, _ in validate_spec(spec)]
        assert "custom.bits_overlap" in codes


class TestLayoutPersistence:
    def test_layout_survives_a_round_trip(self, tmp_path):
        from detector_scenario_tool.domain.custom_messages import CustomBitRange, CustomByteLayout
        from detector_scenario_tool.domain.scenario import (
            ScenarioDocument,
            ScenarioMetadata,
            ValidationProfile,
        )
        from detector_scenario_tool.storage.scenario_io import load_scenario, save_scenario

        spec = CustomMessageSpec(name="X", msg_id=0x0FFF, length=2, content_hex="06 FF")
        spec.trim_layout()
        spec.layout[0] = CustomByteLayout(
            name="Конфигурация",
            bits=[CustomBitRange(name="Банк", offset=0, length=2)],
        )
        spec.layout[1] = CustomByteLayout(name="Счётчик")

        document = ScenarioDocument(
            schema_version=2,
            metadata=ScenarioMetadata(name="layout"),
            validation=ValidationProfile(),
            steps=[],
            custom_messages=[spec],
        )
        path = tmp_path / "layout.json"
        save_scenario(document, path)
        restored = load_scenario(path).custom_messages[0]

        assert restored.layout[0].name == "Конфигурация"
        assert restored.layout[0].bits[0].name == "Банк"
        assert restored.layout[0].bits[0].offset == 0
        assert restored.layout[0].bits[0].length == 2
        assert restored.layout[1].name == "Счётчик"
