"""The catalogue: every message the tool knows, and what a scenario may do to it.

The safety property under test throughout is that the specification's own definitions live in
`protocol/definitions` as code and are never written over, so anything a scenario does to them is
reversible.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QMessageBox

from detector_scenario_tool.domain.custom_messages import CustomMessageSpec, from_message_def
from detector_scenario_tool.protocol import registry
from detector_scenario_tool.protocol.definitions import ALL_MESSAGE_DEFS
from detector_scenario_tool.services.custom_message_sync import CustomMessageSync
from detector_scenario_tool.ui.dialogs.message_catalog_dialog import (
    SOURCE_BUILTIN,
    SOURCE_CUSTOM,
    SOURCE_OVERRIDDEN,
    SOURCE_SUPPRESSED,
    MessageCatalogDialog,
)
import message_ids

ERASE = ("KU", message_ids.ERASE)
TEST = ("KU", message_ids.TEST)
CUSTOM = ("KU", message_ids.UNKNOWN)


@pytest.fixture(autouse=True)
def confirm_everything(monkeypatch):
    """The confirmations have their own tests; elsewhere assume the user said yes."""
    monkeypatch.setattr(
        QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
    )


@pytest.fixture
def sync():
    s = CustomMessageSync()
    yield s
    s.clear()


@pytest.fixture
def dialog(qtbot):
    def _make(specs=None, suppressed=None):
        d = MessageCatalogDialog(specs or [], suppressed or [])
        qtbot.addWidget(d)
        return d

    return _make


def _source(dialog, key) -> str:
    for row in dialog.rows():
        if row["key"] == key:
            return row["source"]
    raise AssertionError(f"{key} is not listed")


def _override_of(key, name="Изменённая") -> CustomMessageSpec:
    spec = from_message_def(registry.find(*key))
    spec.name = name
    return spec


class TestListing:
    def test_every_protocol_message_is_listed(self, dialog):
        d = dialog()
        assert len(d.rows()) == len(ALL_MESSAGE_DEFS)

    def test_built_in_messages_are_marked_as_such(self, dialog):
        assert _source(dialog(), ERASE) == SOURCE_BUILTIN

    def test_own_messages_are_listed_alongside(self, dialog):
        d = dialog([CustomMessageSpec(name="Моя", msg_id=CUSTOM[1], length=4)])

        assert len(d.rows()) == len(ALL_MESSAGE_DEFS) + 1
        assert _source(d, CUSTOM) == SOURCE_CUSTOM

    def test_the_summary_counts_the_three_kinds(self, dialog):
        d = dialog([CustomMessageSpec(msg_id=CUSTOM[1]), _override_of(ERASE)], [TEST])
        text = d.summary_label.text()

        assert str(len(ALL_MESSAGE_DEFS) + 1) in text
        assert "1" in text


class TestFiltering:
    def test_by_category(self, dialog):
        d = dialog()
        d.filter_combo.setCurrentIndex(d.filter_combo.findData("KT"))

        assert {row["key"][0] for row in d.visible_rows()} == {"KT"}

    def test_by_name(self, dialog):
        d = dialog()
        d.search_edit.setText("стирание")

        assert d.visible_rows()
        assert all("тир" in row["name"].lower() for row in d.visible_rows())

    def test_by_identifier(self, dialog):
        d = dialog()
        d.search_edit.setText(f"{message_ids.ERASE:04X}")

        assert [row["key"] for row in d.visible_rows()] == [ERASE]


class TestOverriding:
    def test_a_built_in_becomes_modified(self, dialog):
        d = dialog([_override_of(ERASE)])
        assert _source(d, ERASE) == SOURCE_OVERRIDDEN

    def test_the_override_reaches_the_registry(self, dialog, sync):
        d = dialog([_override_of(ERASE, name="Стирание (моё)")])
        sync.apply(d.specs, d.suppressed)

        assert registry.find(*ERASE).custom_name == "Стирание (моё)"
        assert registry.find(*ERASE).custom is True

    def test_seeding_from_a_built_in_keeps_its_shape(self):
        """The identifier, length and framing must survive; only the field types are lost."""
        spec = from_message_def(registry.find(*ERASE))

        assert (spec.category, spec.msg_id) == ERASE
        assert spec.length == registry.find(*ERASE).length
        assert spec.overrides_builtin is True

    def test_seeding_carries_the_field_names_over(self):
        spec = from_message_def(registry.find(*ERASE))
        names = [b.name for entry in spec.layout for b in entry.bits]

        assert any("NAND" in name for name in names)

    def test_an_override_is_not_reported_as_an_accidental_collision(self):
        from detector_scenario_tool.domain.custom_messages import validate_spec

        codes = [code for code, _ in validate_spec(_override_of(ERASE))]
        assert "custom.shadows_catalogue" not in codes

    def test_an_accidental_collision_still_is(self):
        from detector_scenario_tool.domain.custom_messages import validate_spec

        spec = CustomMessageSpec(category="KU", msg_id=message_ids.ERASE)
        codes = [code for code, _ in validate_spec(spec)]

        assert "custom.shadows_catalogue" in codes


class TestDeleting:
    def test_an_own_message_is_removed(self, dialog):
        d = dialog([CustomMessageSpec(msg_id=CUSTOM[1])])
        d.table.selectRow(_row_of(d, CUSTOM))
        d.delete_selected()

        assert not any((s.category, s.msg_id) == CUSTOM for s in d.specs)
        assert CUSTOM not in [row["key"] for row in d.rows()]

    def test_a_built_in_is_hidden_not_destroyed(self, dialog):
        d = dialog()
        d.table.selectRow(_row_of(d, ERASE))
        d.delete_selected()

        assert _source(d, ERASE) == SOURCE_SUPPRESSED
        assert ERASE in d.suppressed

    def test_a_hidden_built_in_leaves_the_registry(self, dialog, sync):
        d = dialog(suppressed=[ERASE])
        sync.apply(d.specs, d.suppressed)

        assert registry.find(*ERASE) is None

    def test_hiding_never_touches_the_specification(self, dialog, sync):
        d = dialog(suppressed=[ERASE])
        sync.apply(d.specs, d.suppressed)
        sync.clear()

        assert registry.find(*ERASE) is not None
        assert registry.find(*ERASE).symbol == "CMD_ERASE"


class TestRestoring:
    def test_a_modified_built_in_comes_back(self, dialog, sync):
        d = dialog([_override_of(ERASE)])
        d.table.selectRow(_row_of(d, ERASE))
        d.restore_selected()
        sync.apply(d.specs, d.suppressed)

        assert registry.find(*ERASE).symbol == "CMD_ERASE"
        assert registry.find(*ERASE).custom is False

    def test_a_hidden_built_in_comes_back(self, dialog, sync):
        d = dialog(suppressed=[ERASE])
        d.table.selectRow(_row_of(d, ERASE))
        d.restore_selected()
        sync.apply(d.specs, d.suppressed)

        assert registry.find(*ERASE) is not None

    def test_restore_all_undoes_every_change_to_built_ins(self, dialog, sync):
        d = dialog([_override_of(ERASE)], [TEST])
        d.restore_all()
        sync.apply(d.specs, d.suppressed)

        assert registry.find(*ERASE).symbol == "CMD_ERASE"
        assert registry.find(*TEST).symbol == "CMD_TEST"
        assert d.suppressed == []

    def test_restore_all_keeps_the_scenario_own_messages(self, dialog):
        own = CustomMessageSpec(name="Моя", msg_id=CUSTOM[1])
        d = dialog([own, _override_of(ERASE)], [TEST])

        d.restore_all()

        assert [s.msg_id for s in d.specs] == [CUSTOM[1]]

    def test_restoring_is_offered_only_where_it_means_something(self, dialog):
        d = dialog([CustomMessageSpec(msg_id=CUSTOM[1])])

        d.table.selectRow(_row_of(d, ERASE))
        assert not d.restore_button.isEnabled(), "an untouched built-in has nothing to restore"

        d.table.selectRow(_row_of(d, CUSTOM))
        assert not d.restore_button.isEnabled(), "an own message has no original to go back to"

    def test_restore_all_is_offered_only_when_something_changed(self, dialog):
        assert not dialog().restore_all_button.isEnabled()
        assert dialog([_override_of(ERASE)]).restore_all_button.isEnabled()
        assert dialog(suppressed=[TEST]).restore_all_button.isEnabled()


class TestConfirmations:
    def test_modifying_a_built_in_asks_first(self, dialog, monkeypatch):
        asked = []
        monkeypatch.setattr(
            QMessageBox,
            "question",
            staticmethod(lambda *a, **k: (asked.append(1), QMessageBox.StandardButton.Cancel)[1]),
        )

        d = dialog()
        d.table.selectRow(_row_of(d, ERASE))
        d.edit_selected()

        assert asked, "replacing a specification message must not happen silently"
        assert d.specs == []

    def test_restore_all_asks_first(self, dialog, monkeypatch):
        monkeypatch.setattr(
            QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Cancel)
        )

        d = dialog([_override_of(ERASE)])
        d.restore_all()

        assert d.specs, "cancelling must leave the changes in place"


class TestPersistence:
    def test_overrides_and_suppressions_round_trip(self, tmp_path):
        from detector_scenario_tool.domain.scenario import (
            ScenarioDocument,
            ScenarioMetadata,
            ValidationProfile,
        )
        from detector_scenario_tool.storage.scenario_io import load_scenario, save_scenario

        document = ScenarioDocument(
            schema_version=2,
            metadata=ScenarioMetadata(name="catalogue"),
            validation=ValidationProfile(),
            steps=[],
            custom_messages=[_override_of(ERASE, name="Моё стирание")],
            suppressed_messages=[TEST],
        )
        path = tmp_path / "catalogue.json"
        save_scenario(document, path)
        loaded = load_scenario(path)

        assert loaded.custom_messages[0].name == "Моё стирание"
        assert loaded.custom_messages[0].overrides_builtin is True
        assert loaded.suppressed_messages == [TEST]


def _row_of(dialog, key) -> int:
    """The visual row, which is not the model order — the table is sortable."""
    from detector_scenario_tool.ui.dialogs.message_catalog_dialog import _ROLE_KEY

    for index in range(dialog.table.rowCount()):
        item = dialog.table.item(index, 0)
        if item is not None and tuple(item.data(_ROLE_KEY)) == tuple(key):
            return index
    raise AssertionError(f"{key} is not visible")
