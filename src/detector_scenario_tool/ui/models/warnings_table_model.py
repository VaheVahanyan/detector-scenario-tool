from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from detector_scenario_tool.i18n import tr
from detector_scenario_tool.validation.diagnostics import Diagnostic


class WarningsTableModel(QAbstractTableModel):
    HEADER_KEYS = [
        "warnings.column.severity",
        "warnings.column.step",
        "warnings.column.code",
        "warnings.column.message",
    ]

    def __init__(self) -> None:
        super().__init__()
        self.items: list[Diagnostic] = []

    def set_items(self, items: list[Diagnostic]) -> None:
        self.beginResetModel()
        self.items = items
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self.items)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self.HEADER_KEYS)

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ):
        if role != Qt.ItemDataRole.DisplayRole:
            return None

        if orientation == Qt.Orientation.Horizontal:
            if 0 <= section < len(self.HEADER_KEYS):
                return tr(self.HEADER_KEYS[section])
            return None

        return str(section + 1)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        item = self.items[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return tr(f"severity.{item.severity.value}")
            if col == 1:
                return "-" if item.step_index < 0 else str(item.step_index + 1)
            if col == 2:
                return item.code
            if col == 3:
                return render_diagnostic(item)

        return None


def render_diagnostic(item: Diagnostic) -> str:
    """Format a diagnostic in the current language.

    Diagnostics carry a code and parameters rather than a finished string, so the warnings panel
    re-renders correctly after a language switch.
    """
    key = f"diag.{item.code}"
    text = tr(key, **item.params) if item.params else tr(key)

    if text != key:
        return text

    # No translation for this code yet: fall back to whatever the producer supplied, then to a
    # readable dump of the parameters, so a new rule is never invisible.
    if item.message:
        return item.message
    if item.params:
        params = ", ".join(f"{k}={v}" for k, v in item.params.items())
        return f"{item.code} ({params})"
    return item.code