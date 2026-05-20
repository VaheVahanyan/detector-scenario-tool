from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor, QBrush

from detector_scenario_tool.domain.logs import LogRecord
from detector_scenario_tool.protocol.catalog import ProtocolCatalog
from detector_scenario_tool.protocol.log_decode import build_log_summary
from detector_scenario_tool.i18n import tr


class LogTableModel(QAbstractTableModel):
    HEADER_KEYS = [
        "logs.column.time",
        "logs.column.source",
        "logs.column.direction",
        "logs.column.message",
        "logs.column.summary",
        "logs.column.payload_hex",
    ]

    def __init__(self, catalog: ProtocolCatalog) -> None:
        super().__init__()
        self._catalog = catalog
        self._items: list[LogRecord] = []
        self._matched_rows: set[int] = set()
        self._problem_rows: set[int] = set()
        self._row_tooltips: dict[int, str] = {}

    def set_items(self, items: list[LogRecord]) -> None:
        self.beginResetModel()
        self._items = list(items)
        self._matched_rows = set()
        self._problem_rows = set()
        self._row_tooltips = {}
        self.endResetModel()

    def set_matched_rows(self, matched_rows: set[int]) -> None:
        self.beginResetModel()
        self._matched_rows = set(matched_rows)
        self.endResetModel()

    def set_problem_rows(self, problem_rows: set[int]) -> None:
        self.beginResetModel()
        self._problem_rows = set(problem_rows)
        self.endResetModel()

    def set_row_tooltips(self, row_tooltips: dict[int, str]) -> None:
        self.beginResetModel()
        self._row_tooltips = dict(row_tooltips)
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._items)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self.HEADER_KEYS)

    def headerData(self, section: int, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None

        if orientation == Qt.Orientation.Horizontal:
            return tr(self.HEADER_KEYS[section])
        return str(section + 1)

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        item = self._items[index.row()]
        row = index.row()

        if role == Qt.ItemDataRole.DisplayRole:
            col = index.column()

            if col == 0:
                return str(item.timestamp_ms)
            if col == 1:
                return item.source
            if col == 2:
                return item.direction.upper()
            if col == 3:
                return self._message_title(item)
            if col == 4:
                return self._summary(item)
            if col == 5:
                return item.payload_hex

        if role == Qt.ItemDataRole.BackgroundRole:
            if row not in self._matched_rows:
                return QBrush(QColor(80, 35, 35))
            if row in self._problem_rows:
                return QBrush(QColor(85, 70, 30))

        if role == Qt.ItemDataRole.ForegroundRole:
            if row not in self._matched_rows:
                return QBrush(QColor(255, 220, 220))
            if row in self._problem_rows:
                return QBrush(QColor(255, 240, 190))

        if role == Qt.ItemDataRole.ToolTipRole:
            return self._row_tooltips.get(row)

        return None

    def _message_title(self, item: LogRecord) -> str:
        name = self._lookup_name(item.category, item.msg_id)
        if name:
            return f"{item.category} 0x{item.msg_id:04X} {name}"
        return f"{item.category} 0x{item.msg_id:04X}"

    def _summary(self, item: LogRecord) -> str:
        return build_log_summary(item)

    def _lookup_name(self, category: str, msg_id: int) -> str | None:
        if category == "KU":
            for msg in self._catalog.get_ku_messages():
                if msg.msg_id == msg_id:
                    return msg.name
        elif category == "KT":
            for msg in self._catalog.get_kt_messages():
                if msg.msg_id == msg_id:
                    return msg.name
        elif category == "TS":
            for msg in self._catalog.get_ts_messages():
                if msg.msg_id == msg_id:
                    return msg.name

        return None
