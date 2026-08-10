"""Editing the content of a user-defined message.

Three views over the same bytes, because the same message is authored in different ways at
different moments:

* **HEX** — the default. Most user-defined messages are one-off probes and naming every byte
  would be busywork.
* **По байтам** — each byte gets a name and a value.
* **Биты** — a byte can be split into named bit fields, the way the protocol's own hardware
  configuration bytes are described.

The bytes themselves always live in `CustomMessageSpec.content_hex`; the layout only records names
and bit ranges. Switching views therefore cannot lose data.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from detector_scenario_tool.domain.custom_messages import (
    CustomBitRange,
    CustomByteLayout,
    CustomMessageSpec,
    parse_bit_range,
)
from detector_scenario_tool.i18n import tr

VIEW_HEX = "hex"
VIEW_BYTES = "bytes"

#: A tree row per byte stops being usable long before the 6146-byte maximum; past this the hex
#: view is the honest answer rather than a spinner.
MAX_ROWS = 512

COLUMN_INDEX = 0
COLUMN_NAME = 1
COLUMN_VALUE = 2

#: Item data slots.
_ROLE_BYTE = Qt.ItemDataRole.UserRole
_ROLE_BIT = Qt.ItemDataRole.UserRole + 1


class ContentEditor(QWidget):
    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.spec = CustomMessageSpec()
        self._loading = False

        self.view_combo = QComboBox()
        self.view_combo.addItem("", VIEW_HEX)
        self.view_combo.addItem("", VIEW_BYTES)

        self.split_button = QPushButton()
        self.merge_button = QPushButton()
        self.add_bit_button = QPushButton()
        self.remove_bit_button = QPushButton()
        self.hint_label = QLabel()
        self.hint_label.setWordWrap(True)

        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(0, 0, 0, 0)
        toolbar.addWidget(self.view_combo)
        toolbar.addWidget(self.split_button)
        toolbar.addWidget(self.merge_button)
        toolbar.addWidget(self.add_bit_button)
        toolbar.addWidget(self.remove_bit_button)
        toolbar.addStretch(1)

        self.hex_edit = QPlainTextEdit()
        self.hex_edit.setPlaceholderText(tr("payload.raw_hex_placeholder"))

        self.tree = QTreeWidget()
        self.tree.setColumnCount(3)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.SelectedClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        header = self.tree.header()
        header.setSectionResizeMode(COLUMN_INDEX, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(COLUMN_NAME, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(COLUMN_VALUE, QHeaderView.ResizeMode.ResizeToContents)

        self.stack = QStackedWidget()
        self.stack.addWidget(self.hex_edit)
        self.stack.addWidget(self.tree)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(toolbar)
        layout.addWidget(self.stack, 1)
        layout.addWidget(self.hint_label)

        self.view_combo.currentIndexChanged.connect(self._on_view_changed)
        self.hex_edit.textChanged.connect(self._on_hex_changed)
        self.tree.itemChanged.connect(self._on_item_changed)
        self.tree.itemSelectionChanged.connect(self._update_buttons)
        self.split_button.clicked.connect(self.split_selected_byte)
        self.merge_button.clicked.connect(self.merge_selected_byte)
        self.add_bit_button.clicked.connect(self.add_bit_field)
        self.remove_bit_button.clicked.connect(self.remove_bit_field)

        self.retranslate_ui()
        self._update_buttons()

    # -- content -----------------------------------------------------------------------

    def set_spec(self, spec: CustomMessageSpec) -> None:
        self.spec = spec
        self.spec.trim_layout()
        self._reload()

        # A message that already has names opens in the view that shows them.
        self.view_combo.setCurrentIndex(
            self.view_combo.findData(VIEW_BYTES if spec.has_layout else VIEW_HEX)
        )

    @property
    def view_mode(self) -> str:
        return self.view_combo.currentData() or VIEW_HEX

    def _reload(self) -> None:
        self._loading = True
        try:
            self.hex_edit.setPlainText(self.spec.content_hex)
            self._rebuild_tree()
        finally:
            self._loading = False
        self._update_hint()

    def _rebuild_tree(self) -> None:
        self.tree.clear()
        self.spec.trim_layout()
        content = self.spec.content_bytes()

        for index in range(min(self.spec.length, MAX_ROWS)):
            entry = self.spec.layout[index]
            item = QTreeWidgetItem(self.tree)
            item.setData(COLUMN_INDEX, _ROLE_BYTE, index)
            item.setText(COLUMN_INDEX, str(index))
            item.setText(COLUMN_NAME, entry.name)
            item.setText(COLUMN_VALUE, f"{content[index]:02X}")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)

            for position, bit_range in enumerate(entry.bits):
                child = QTreeWidgetItem(item)
                child.setData(COLUMN_INDEX, _ROLE_BYTE, index)
                child.setData(COLUMN_INDEX, _ROLE_BIT, position)
                child.setText(COLUMN_INDEX, bit_range.range_text)
                child.setText(COLUMN_NAME, bit_range.name)
                child.setText(COLUMN_VALUE, str(bit_range.extract(content[index])))
                child.setFlags(child.flags() | Qt.ItemFlag.ItemIsEditable)

            item.setExpanded(bool(entry.bits))

    # -- editing -----------------------------------------------------------------------

    def _on_view_changed(self) -> None:
        self.stack.setCurrentIndex(0 if self.view_mode == VIEW_HEX else 1)
        if self.view_mode == VIEW_BYTES:
            self._reload()
        self._update_buttons()
        self._update_hint()

    def _on_hex_changed(self) -> None:
        if self._loading:
            return
        self.spec.content_hex = self.hex_edit.toPlainText()
        self.changed.emit()

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if self._loading:
            return

        index = item.data(COLUMN_INDEX, _ROLE_BYTE)
        position = item.data(COLUMN_INDEX, _ROLE_BIT)
        if index is None:
            return

        entry = self.spec.byte_layout(index)

        if position is None:
            self._apply_byte_edit(item, column, index, entry)
        else:
            self._apply_bit_edit(item, column, index, entry, position)

        self._loading = True
        try:
            self.hex_edit.setPlainText(self.spec.content_hex)
        finally:
            self._loading = False

        self.changed.emit()

    def _apply_byte_edit(self, item, column: int, index: int, entry: CustomByteLayout) -> None:
        if column == COLUMN_NAME:
            entry.name = item.text(COLUMN_NAME).strip()
            return

        if column == COLUMN_VALUE:
            value = _parse_byte(item.text(COLUMN_VALUE))
            if value is None:
                self._set_text(item, COLUMN_VALUE, f"{self.spec.byte_value(index):02X}")
                return
            self.spec.set_byte(index, value)
            self._set_text(item, COLUMN_VALUE, f"{value:02X}")
            self._refresh_children(item, index)

    def _apply_bit_edit(
            self, item, column: int, index: int, entry: CustomByteLayout, position: int
    ) -> None:
        if position >= len(entry.bits):
            return
        bit_range = entry.bits[position]

        if column == COLUMN_NAME:
            bit_range.name = item.text(COLUMN_NAME).strip()
            return

        if column == COLUMN_INDEX:
            parsed = parse_bit_range(item.text(COLUMN_INDEX))
            if parsed is None:
                self._set_text(item, COLUMN_INDEX, bit_range.range_text)
                return
            bit_range.offset = parsed.offset
            bit_range.length = parsed.length
            self._set_text(item, COLUMN_INDEX, bit_range.range_text)
            self._set_text(
                item, COLUMN_VALUE, str(bit_range.extract(self.spec.byte_value(index)))
            )
            return

        if column == COLUMN_VALUE:
            try:
                value = int(item.text(COLUMN_VALUE), 0)
            except ValueError:
                self._set_text(
                    item, COLUMN_VALUE, str(bit_range.extract(self.spec.byte_value(index)))
                )
                return

            byte_value = bit_range.apply(self.spec.byte_value(index), value)
            self.spec.set_byte(index, byte_value)

            parent = item.parent()
            if parent is not None:
                self._set_text(parent, COLUMN_VALUE, f"{byte_value:02X}")
                self._refresh_children(parent, index)

    def _refresh_children(self, parent: QTreeWidgetItem, index: int) -> None:
        entry = self.spec.byte_layout(index)
        value = self.spec.byte_value(index)
        for position in range(parent.childCount()):
            if position >= len(entry.bits):
                break
            self._set_text(
                parent.child(position), COLUMN_VALUE, str(entry.bits[position].extract(value))
            )

    def _set_text(self, item: QTreeWidgetItem, column: int, text: str) -> None:
        was_loading = self._loading
        self._loading = True
        try:
            item.setText(column, text)
        finally:
            self._loading = was_loading

    # -- structure ---------------------------------------------------------------------

    def selected_byte(self) -> int | None:
        item = self.tree.currentItem()
        if item is None:
            return None
        return item.data(COLUMN_INDEX, _ROLE_BYTE)

    def split_selected_byte(self) -> None:
        """Give the byte one named field per bit, which the user then renames or merges."""
        index = self.selected_byte()
        if index is None:
            return

        entry = self.spec.byte_layout(index)
        if entry.bits:
            return

        entry.bits = [CustomBitRange(offset=offset, length=1) for offset in range(8)]
        self._reload()
        self._select_byte(index)
        self.changed.emit()

    def merge_selected_byte(self) -> None:
        index = self.selected_byte()
        if index is None:
            return

        entry = self.spec.byte_layout(index)
        if not entry.bits:
            return

        entry.bits = []
        self._reload()
        self._select_byte(index)
        self.changed.emit()

    def add_bit_field(self) -> None:
        index = self.selected_byte()
        if index is None:
            return

        entry = self.spec.byte_layout(index)
        used = 0
        for bit_range in entry.bits:
            used |= bit_range.mask

        offset = next((i for i in range(8) if not used & (1 << i)), None)
        if offset is None:
            return

        entry.bits.append(CustomBitRange(offset=offset, length=1))
        entry.bits.sort(key=lambda r: r.offset)
        self._reload()
        self._select_byte(index)
        self.changed.emit()

    def remove_bit_field(self) -> None:
        item = self.tree.currentItem()
        if item is None:
            return
        index = item.data(COLUMN_INDEX, _ROLE_BYTE)
        position = item.data(COLUMN_INDEX, _ROLE_BIT)
        if index is None or position is None:
            return

        entry = self.spec.byte_layout(index)
        if position < len(entry.bits):
            entry.bits.pop(position)

        self._reload()
        self._select_byte(index)
        self.changed.emit()

    def _select_byte(self, index: int) -> None:
        for row in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(row)
            if item.data(COLUMN_INDEX, _ROLE_BYTE) == index:
                self.tree.setCurrentItem(item)
                return

    # -- chrome ------------------------------------------------------------------------

    def _update_buttons(self) -> None:
        in_bytes_view = self.view_mode == VIEW_BYTES
        item = self.tree.currentItem()
        index = self.selected_byte()
        is_bit_row = item is not None and item.data(COLUMN_INDEX, _ROLE_BIT) is not None
        split = (
            index is not None
            and index < len(self.spec.layout)
            and self.spec.layout[index].is_split
        )

        self.split_button.setEnabled(in_bytes_view and index is not None and not split)
        self.merge_button.setEnabled(in_bytes_view and split)
        self.add_bit_button.setEnabled(in_bytes_view and split)
        self.remove_bit_button.setEnabled(in_bytes_view and is_bit_row)

        for button in (
            self.split_button,
            self.merge_button,
            self.add_bit_button,
            self.remove_bit_button,
        ):
            button.setVisible(in_bytes_view)

    def _update_hint(self) -> None:
        if self.view_mode == VIEW_HEX:
            self.hint_label.setText("")
            return

        if self.spec.length > MAX_ROWS:
            self.hint_label.setText(
                tr("custom.content.too_many_bytes", shown=MAX_ROWS, total=self.spec.length)
            )
        else:
            self.hint_label.setText(tr("custom.content.bytes_hint"))

    def retranslate_ui(self) -> None:
        self.tree.setHeaderLabels(
            [
                tr("custom.content.column.index"),
                tr("custom.field.name"),
                tr("custom.content.column.value"),
            ]
        )
        for index, mode in enumerate((VIEW_HEX, VIEW_BYTES)):
            self.view_combo.setItemText(index, tr(f"custom.content.view.{mode}"))

        self.split_button.setText(tr("custom.content.split"))
        self.merge_button.setText(tr("custom.content.merge"))
        self.add_bit_button.setText(tr("custom.content.add_bit"))
        self.remove_bit_button.setText(tr("custom.content.remove_bit"))
        self._update_hint()


def _parse_byte(text: str) -> int | None:
    cleaned = (text or "").strip()
    if not cleaned:
        return None
    try:
        value = int(cleaned, 16)
    except ValueError:
        return None
    return value if 0 <= value <= 0xFF else None
