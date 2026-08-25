"""The three views over a user-defined message's content.

The bytes live in `content_hex` and the layout only names them, so the load-bearing property is
that switching views, splitting a byte and editing a bit all agree about the same bytes.
"""

from __future__ import annotations

import pytest

from detector_scenario_tool.domain.custom_messages import (
    CustomBitRange,
    CustomByteLayout,
    CustomMessageSpec,
    parse_bit_range,
    to_message_def,
)
from detector_scenario_tool.protocol.fields import pack_message
from detector_scenario_tool.ui.widgets.content_editor import (
    COLUMN_INDEX,
    COLUMN_NAME,
    COLUMN_VALUE,
    VIEW_BYTES,
    VIEW_HEX,
    ContentEditor,
)


@pytest.fixture
def editor(qtbot):
    widget = ContentEditor()
    qtbot.addWidget(widget)
    return widget


def _load(editor, length: int = 3, content: str = "06 FF 00") -> CustomMessageSpec:
    spec = CustomMessageSpec(msg_id=0x0FFF, length=length, content_hex=content)
    editor.set_spec(spec)
    editor.view_combo.setCurrentIndex(editor.view_combo.findData(VIEW_BYTES))
    return spec


def _byte_row(editor, index: int):
    return editor.tree.topLevelItem(index)


class TestBitRangeParsing:
    @pytest.mark.parametrize(
        ("text", "offset", "length"),
        [("3", 3, 1), ("0-2", 0, 3), ("0–2", 0, 3), (" 5 ", 5, 1), ("7-4", 4, 4)],
    )
    def test_accepted_forms(self, text, offset, length):
        parsed = parse_bit_range(text)
        assert (parsed.offset, parsed.length) == (offset, length)

    @pytest.mark.parametrize("text", ["", "abc", "8", "0-9", "-1", "1-"])
    def test_rejected_forms(self, text):
        assert parse_bit_range(text) is None

    def test_a_range_reports_itself_the_way_it_is_typed(self):
        assert CustomBitRange(offset=0, length=2).range_text == "0-1"
        assert CustomBitRange(offset=4, length=1).range_text == "4"


class TestViews:
    def test_hex_is_the_default(self, editor):
        editor.set_spec(CustomMessageSpec(length=2))
        assert editor.view_mode == VIEW_HEX

    def test_an_annotated_message_opens_in_the_byte_view(self, editor):
        """Names are the reason to have made them; do not hide them behind a mode switch."""
        spec = CustomMessageSpec(length=1, content_hex="01")
        spec.trim_layout()
        spec.layout[0] = CustomByteLayout(name="Флаги")

        editor.set_spec(spec)

        assert editor.view_mode == VIEW_BYTES

    def test_the_byte_view_shows_one_row_per_byte(self, editor):
        _load(editor, length=3)
        assert editor.tree.topLevelItemCount() == 3

    def test_hex_edits_reach_the_byte_view(self, editor):
        _load(editor, length=2, content="00 00")
        editor.view_combo.setCurrentIndex(editor.view_combo.findData(VIEW_HEX))
        editor.hex_edit.setPlainText("AB CD")
        editor.view_combo.setCurrentIndex(editor.view_combo.findData(VIEW_BYTES))

        assert _byte_row(editor, 0).text(COLUMN_VALUE) == "AB"
        assert _byte_row(editor, 1).text(COLUMN_VALUE) == "CD"

    def test_byte_edits_reach_the_hex_view(self, editor):
        spec = _load(editor, length=2, content="00 00")
        _byte_row(editor, 1).setText(COLUMN_VALUE, "7F")

        assert spec.byte_value(1) == 0x7F
        assert "7F" in editor.hex_edit.toPlainText()


class TestByteEditing:
    def test_a_byte_can_be_named(self, editor):
        spec = _load(editor)
        _byte_row(editor, 0).setText(COLUMN_NAME, "Аппаратная конфигурация")

        assert spec.layout[0].name == "Аппаратная конфигурация"

    def test_an_unparsable_value_is_rejected_and_restored(self, editor):
        spec = _load(editor, content="06 FF 00")
        _byte_row(editor, 0).setText(COLUMN_VALUE, "не байт")

        assert spec.byte_value(0) == 0x06
        assert _byte_row(editor, 0).text(COLUMN_VALUE) == "06"

    def test_a_value_over_a_byte_is_rejected(self, editor):
        spec = _load(editor, content="06 FF 00")
        _byte_row(editor, 0).setText(COLUMN_VALUE, "1FF")

        assert spec.byte_value(0) == 0x06


class TestBitEditing:
    def test_splitting_gives_one_field_per_bit(self, editor):
        spec = _load(editor)
        editor.tree.setCurrentItem(_byte_row(editor, 0))
        editor.split_selected_byte()

        assert len(spec.layout[0].bits) == 8
        assert _byte_row(editor, 0).childCount() == 8

    def test_the_bits_show_the_byte_that_is_already_there(self, editor):
        _load(editor, content="06 00 00")     # 0b0000_0110
        editor.tree.setCurrentItem(_byte_row(editor, 0))
        editor.split_selected_byte()

        row = _byte_row(editor, 0)
        assert [row.child(i).text(COLUMN_VALUE) for i in range(8)] == list("01100000")

    def test_bits_can_be_merged_into_a_range(self, editor):
        spec = _load(editor, content="06 00 00")
        editor.tree.setCurrentItem(_byte_row(editor, 0))
        editor.split_selected_byte()

        _byte_row(editor, 0).child(0).setText(COLUMN_INDEX, "0-1")

        assert spec.layout[0].bits[0].length == 2
        assert _byte_row(editor, 0).child(0).text(COLUMN_VALUE) == "2"

    def test_editing_a_bit_field_changes_the_byte(self, editor):
        spec = _load(editor, content="00 00 00")
        editor.tree.setCurrentItem(_byte_row(editor, 0))
        editor.split_selected_byte()

        _byte_row(editor, 0).child(2).setText(COLUMN_VALUE, "1")

        assert spec.byte_value(0) == 0b100
        assert _byte_row(editor, 0).text(COLUMN_VALUE) == "04"

    def test_an_invalid_bit_range_is_restored(self, editor):
        spec = _load(editor)
        editor.tree.setCurrentItem(_byte_row(editor, 0))
        editor.split_selected_byte()

        _byte_row(editor, 0).child(0).setText(COLUMN_INDEX, "nonsense")

        assert spec.layout[0].bits[0].offset == 0
        assert _byte_row(editor, 0).child(0).text(COLUMN_INDEX) == "0"

    def test_a_bit_field_can_be_removed(self, editor):
        spec = _load(editor)
        editor.tree.setCurrentItem(_byte_row(editor, 0))
        editor.split_selected_byte()

        editor.tree.setCurrentItem(_byte_row(editor, 0).child(3))
        editor.remove_bit_field()

        assert len(spec.layout[0].bits) == 7

    def test_a_bit_field_can_be_added_back(self, editor):
        spec = _load(editor)
        editor.tree.setCurrentItem(_byte_row(editor, 0))
        editor.split_selected_byte()
        editor.tree.setCurrentItem(_byte_row(editor, 0).child(0))
        editor.remove_bit_field()

        editor.tree.setCurrentItem(_byte_row(editor, 0))
        editor.add_bit_field()

        assert len(spec.layout[0].bits) == 8

    def test_merging_back_keeps_the_byte_value(self, editor):
        spec = _load(editor, content="06 00 00")
        editor.tree.setCurrentItem(_byte_row(editor, 0))
        editor.split_selected_byte()
        editor.merge_selected_byte()

        assert spec.layout[0].bits == []
        assert spec.byte_value(0) == 0x06

    def test_the_buttons_follow_the_selection(self, editor):
        _load(editor)
        editor.tree.setCurrentItem(_byte_row(editor, 0))

        assert editor.split_button.isEnabled()
        assert not editor.merge_button.isEnabled()
        assert not editor.remove_bit_button.isEnabled()

        editor.split_selected_byte()
        assert not editor.split_button.isEnabled()
        assert editor.merge_button.isEnabled()

        editor.tree.setCurrentItem(_byte_row(editor, 0).child(0))
        assert editor.remove_bit_button.isEnabled()


class TestGeneratedFields:
    def test_named_bits_become_named_form_fields(self, editor):
        spec = _load(editor, length=2, content="06 FF")
        spec.layout[0] = CustomByteLayout(
            name="Конфигурация",
            bits=[
                CustomBitRange(name="Банк", offset=0, length=2),
                CustomBitRange(name="Питание", offset=2, length=1),
            ],
        )
        spec.layout[1] = CustomByteLayout(name="Счётчик")

        labels = [f.label for f in to_message_def(spec).editable_fields]

        assert "Банк" in labels
        assert "Питание" in labels
        assert "Счётчик" in labels

    def test_unnamed_bits_are_folded_into_one_run(self, editor):
        """An unnamed bit field says nothing, so it should not become a form row of its own."""
        spec = _load(editor, length=1, content="06")
        spec.layout[0] = CustomByteLayout(
            bits=[CustomBitRange(name="Банк", offset=0, length=2)]
            + [CustomBitRange(offset=i, length=1) for i in range(2, 8)]
        )

        labels = [f.label for f in to_message_def(spec).editable_fields]

        assert labels == ["Банк", "#0.2-7"]

    def test_a_byte_with_no_named_bits_stays_a_plain_byte(self, editor):
        spec = _load(editor, length=1, content="06")
        spec.layout[0] = CustomByteLayout(
            bits=[CustomBitRange(offset=i, length=1) for i in range(8)]
        )

        fields = to_message_def(spec).editable_fields
        assert len(fields) == 1
        assert fields[0].byte_length == 1

    def test_the_bytes_survive_the_round_trip(self, editor):
        spec = _load(editor, length=2, content="06 FF")
        spec.layout[0] = CustomByteLayout(
            bits=[
                CustomBitRange(name="Банк", offset=0, length=2),
                CustomBitRange(name="Питание", offset=2, length=1),
            ]
        )

        definition = to_message_def(spec)
        packed = pack_message(definition, definition.default_payload())

        assert packed == bytes([0x06, 0xFF])

    def test_without_annotation_it_stays_one_hex_block(self, editor):
        spec = _load(editor, length=4, content="01 02 03 04")

        fields = to_message_def(spec).editable_fields
        assert [f.key for f in fields] == ["content"]


class TestLargeMessages:
    def test_the_byte_view_is_capped(self, editor):
        from detector_scenario_tool.ui.widgets.content_editor import MAX_ROWS

        _load(editor, length=MAX_ROWS + 100, content="")

        assert editor.tree.topLevelItemCount() == MAX_ROWS
        assert editor.hint_label.text()

    def test_the_hex_view_still_covers_everything(self, editor):
        spec = _load(editor, length=4000, content="")
        editor.view_combo.setCurrentIndex(editor.view_combo.findData(VIEW_HEX))

        assert len(spec.content_bytes()) == 4000
