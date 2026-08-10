"""One list of every message the tool knows: the specification's own and the scenario's additions.

A row is one of three things, and the Source column says which:

* **из протокола** — exactly as `Протокол_CAN_ГС_v2` defines it.
* **изменена** — a built-in replaced by this scenario. The original is untouched in
  `protocol/definitions` and comes back with «Восстановить».
* **своя** — added by this scenario.

Nothing here can destroy a built-in definition: hiding or replacing one is recorded in the
document, and restoring is removing that record.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from detector_scenario_tool.domain.custom_messages import (
    CATEGORIES,
    CustomMessageSpec,
    from_message_def,
)
from detector_scenario_tool.i18n import tr
from detector_scenario_tool.protocol import registry
from detector_scenario_tool.services.custom_message_sync import builtin_definition, is_builtin
from detector_scenario_tool.ui.dialogs.custom_message_dialog import CustomMessageDialog
from detector_scenario_tool.utils.labels import category_short

SOURCE_BUILTIN = "builtin"
SOURCE_OVERRIDDEN = "overridden"
SOURCE_CUSTOM = "custom"
SOURCE_SUPPRESSED = "suppressed"

COLUMNS = ("category", "msg_id", "name", "length", "source")

#: Row payload.
_ROLE_KEY = Qt.ItemDataRole.UserRole
_ROLE_SOURCE = Qt.ItemDataRole.UserRole + 1


class MessageCatalogDialog(QDialog):
    """Edits a document's view of the catalogue; changes apply only when accepted."""

    def __init__(
            self,
            custom_messages: list[CustomMessageSpec],
            suppressed: list[tuple[str, int]] | None = None,
            parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setModal(True)
        self.resize(880, 560)

        self.specs = [_copy(spec) for spec in custom_messages]
        self.suppressed = [tuple(key) for key in (suppressed or [])]

        self.filter_combo = QComboBox()
        self.filter_combo.addItem("", "")
        for code in CATEGORIES:
            self.filter_combo.addItem(category_short(code), code)

        self.search_edit = QLineEdit()

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.table.setSortingEnabled(True)

        header = self.table.horizontalHeader()
        for column in range(len(COLUMNS)):
            header.setSectionResizeMode(
                column,
                QHeaderView.ResizeMode.Stretch
                if COLUMNS[column] == "name"
                else QHeaderView.ResizeMode.ResizeToContents,
            )

        self.add_button = QPushButton()
        self.edit_button = QPushButton()
        self.delete_button = QPushButton()
        self.restore_button = QPushButton()
        self.restore_all_button = QPushButton()
        self.summary_label = QLabel()

        filters = QHBoxLayout()
        filters.addWidget(self.filter_combo)
        filters.addWidget(self.search_edit, 1)

        actions = QHBoxLayout()
        actions.addWidget(self.add_button)
        actions.addWidget(self.edit_button)
        actions.addWidget(self.delete_button)
        actions.addWidget(self.restore_button)
        actions.addStretch(1)
        actions.addWidget(self.restore_all_button)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(filters)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.summary_label)
        layout.addLayout(actions)
        layout.addWidget(self.buttons)

        self.filter_combo.currentIndexChanged.connect(self.refresh)
        self.search_edit.textChanged.connect(self.refresh)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        self.table.itemDoubleClicked.connect(lambda *_: self.edit_selected())
        self.add_button.clicked.connect(self.add_message)
        self.edit_button.clicked.connect(self.edit_selected)
        self.delete_button.clicked.connect(self.delete_selected)
        self.restore_button.clicked.connect(self.restore_selected)
        self.restore_all_button.clicked.connect(self.restore_all)

        self.retranslate_ui()
        self.refresh()

    # -- rows --------------------------------------------------------------------------

    def rows(self) -> list[dict]:
        """Every message the document would end up with, plus the ones it hides."""
        from detector_scenario_tool.protocol.definitions import ALL_MESSAGE_DEFS

        by_key: dict[tuple[str, int], dict] = {}

        for definition in ALL_MESSAGE_DEFS:
            key = (definition.category, definition.msg_id)
            by_key[key] = {
                "key": key,
                "name": definition.custom_name or tr(definition.name_key),
                "length": definition.length,
                "source": SOURCE_BUILTIN,
                "spec": None,
            }

        for spec in self.specs:
            key = (spec.category, spec.msg_id)
            by_key[key] = {
                "key": key,
                "name": spec.display_name,
                "length": spec.length,
                "source": SOURCE_OVERRIDDEN if is_builtin(*key) else SOURCE_CUSTOM,
                "spec": spec,
            }

        for key in self.suppressed:
            if key in by_key and by_key[key]["source"] == SOURCE_BUILTIN:
                by_key[key]["source"] = SOURCE_SUPPRESSED

        return [by_key[key] for key in sorted(by_key)]

    def visible_rows(self) -> list[dict]:
        category = self.filter_combo.currentData() or ""
        needle = self.search_edit.text().strip().lower()

        result = []
        for row in self.rows():
            if category and row["key"][0] != category:
                continue
            if needle:
                haystack = f"{row['name']} {row['key'][0]} {row['key'][1]:04x}".lower()
                if needle not in haystack:
                    continue
            result.append(row)
        return result

    def refresh(self) -> None:
        rows = self.visible_rows()

        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))

        for index, row in enumerate(rows):
            category, msg_id = row["key"]
            values = [
                category_short(category),
                f"0x{msg_id:04X}",
                row["name"],
                str(row["length"]),
                tr(f"catalog.source.{row['source']}"),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setData(_ROLE_KEY, row["key"])
                item.setData(_ROLE_SOURCE, row["source"])
                if row["source"] == SOURCE_SUPPRESSED:
                    font = item.font()
                    font.setStrikeOut(True)
                    item.setFont(font)
                self.table.setItem(index, column, item)

        self.table.setSortingEnabled(True)
        self._update_summary()
        self._update_buttons()

    # -- actions -----------------------------------------------------------------------

    def selected(self) -> dict | None:
        items = self.table.selectedItems()
        if not items:
            return None
        key = items[0].data(_ROLE_KEY)
        for row in self.rows():
            if row["key"] == key:
                return row
        return None

    def add_message(self) -> None:
        dialog = CustomMessageDialog(parent=self, siblings=self.specs)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.specs.append(dialog.result_spec())
            self.refresh()

    def edit_selected(self) -> None:
        row = self.selected()
        if row is None:
            return

        spec = row["spec"]
        if spec is None:
            # Editing a built-in for the first time: seed a definition from it, having said what
            # that costs.
            definition = registry.find(*row["key"])
            if definition is None:
                return
            if not self._confirm_override(row["name"]):
                return
            spec = from_message_def(definition, name=row["name"])
            new = True
        else:
            new = False

        dialog = CustomMessageDialog(spec, parent=self, siblings=self.specs)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        result = dialog.result_spec()
        if new:
            self.specs.append(result)
        else:
            for index, existing in enumerate(self.specs):
                if existing.id == result.id:
                    self.specs[index] = result
                    break
        self.refresh()

    def _confirm_override(self, name: str) -> bool:
        answer = QMessageBox.question(
            self,
            tr("catalog.override.title"),
            tr("catalog.override.text", name=name),
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        return answer == QMessageBox.StandardButton.Ok

    def delete_selected(self) -> None:
        row = self.selected()
        if row is None:
            return

        key = row["key"]

        if row["source"] == SOURCE_CUSTOM:
            self.specs = [s for s in self.specs if (s.category, s.msg_id) != key]
        else:
            # A built-in is hidden, not destroyed; «Восстановить» brings it back.
            self.specs = [s for s in self.specs if (s.category, s.msg_id) != key]
            if key not in self.suppressed:
                self.suppressed.append(key)

        self.refresh()

    def restore_selected(self) -> None:
        row = self.selected()
        if row is None or not is_builtin(*row["key"]):
            return

        key = row["key"]
        self.specs = [s for s in self.specs if (s.category, s.msg_id) != key]
        self.suppressed = [k for k in self.suppressed if k != key]
        self.refresh()

    def restore_all(self) -> None:
        changed = self._changed_builtin_count()
        if changed and not self._confirm_restore_all(changed):
            return

        self.specs = [s for s in self.specs if not is_builtin(s.category, s.msg_id)]
        self.suppressed = []
        self.refresh()

    def _confirm_restore_all(self, count: int) -> bool:
        answer = QMessageBox.question(
            self,
            tr("catalog.restore_all"),
            tr("catalog.restore_all.text", count=count),
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        return answer == QMessageBox.StandardButton.Ok

    def _changed_builtin_count(self) -> int:
        overridden = sum(1 for s in self.specs if is_builtin(s.category, s.msg_id))
        return overridden + len(self.suppressed)

    # -- chrome ------------------------------------------------------------------------

    def _update_buttons(self) -> None:
        row = self.selected()
        source = row["source"] if row else None

        self.edit_button.setEnabled(row is not None and source != SOURCE_SUPPRESSED)
        self.delete_button.setEnabled(row is not None and source != SOURCE_SUPPRESSED)
        self.restore_button.setEnabled(
            row is not None and source in (SOURCE_OVERRIDDEN, SOURCE_SUPPRESSED)
        )
        self.restore_all_button.setEnabled(self._changed_builtin_count() > 0)

    def _update_summary(self) -> None:
        rows = self.rows()
        self.summary_label.setText(
            tr(
                "catalog.summary",
                total=len(rows),
                custom=sum(1 for r in rows if r["source"] == SOURCE_CUSTOM),
                changed=self._changed_builtin_count(),
            )
        )

    def retranslate_ui(self) -> None:
        self.setWindowTitle(tr("catalog.title"))
        self.table.setHorizontalHeaderLabels(
            [
                tr("custom.field.category"),
                tr("custom.field.msg_id"),
                tr("custom.field.name"),
                tr("custom.field.length"),
                tr("catalog.column.source"),
            ]
        )
        self.filter_combo.setItemText(0, tr("logs.filter.category.all"))
        self.search_edit.setPlaceholderText(tr("catalog.search"))
        self.add_button.setText(tr("custom.manager.add"))
        self.edit_button.setText(tr("custom.manager.edit"))
        self.delete_button.setText(tr("catalog.delete"))
        self.restore_button.setText(tr("catalog.restore"))
        self.restore_all_button.setText(tr("catalog.restore_all"))


def _copy(spec: CustomMessageSpec) -> CustomMessageSpec:
    from detector_scenario_tool.ui.dialogs.custom_message_dialog import _copy as copy_spec

    return copy_spec(spec)
