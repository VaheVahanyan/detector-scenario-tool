from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor, QBrush

from detector_scenario_tool.domain.logs import LogRecord
from detector_scenario_tool.protocol.catalog import ProtocolCatalog
from detector_scenario_tool.utils.labels import message_label
from detector_scenario_tool.protocol.log_decode import build_log_summary
from detector_scenario_tool.i18n import tr


VIEW_DECODED = "decoded"
VIEW_RAW = "raw"

#: Column sets per view. Raw shows the wire, decoded shows the meaning.
HEADERS = {
    VIEW_DECODED: [
        "logs.column.time",
        "logs.column.source",
        "logs.column.direction",
        "logs.column.message",
        "logs.column.summary",
        "logs.column.payload_hex",
    ],
    VIEW_RAW: [
        "logs.column.time",
        "logs.column.source",
        "logs.column.direction",
        "logs.column.can_id",
        "logs.column.frames",
        "logs.column.bytes",
        "logs.column.valid",
        "logs.column.payload_hex",
    ],
}


class LogTableModel(QAbstractTableModel):
    #: Kept for callers that predate the raw view.
    HEADER_KEYS = HEADERS[VIEW_DECODED]

    def __init__(self, catalog: ProtocolCatalog) -> None:
        super().__init__()
        self._catalog = catalog
        self._view_mode = VIEW_DECODED
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
        self._set_annotations(matched_rows=matched_rows)

    def set_problem_rows(self, problem_rows: set[int]) -> None:
        self._set_annotations(problem_rows=problem_rows)

    def set_row_tooltips(self, row_tooltips: dict[int, str]) -> None:
        self._set_annotations(row_tooltips=row_tooltips)

    def set_annotations(
            self,
            matched_rows: set[int],
            problem_rows: set[int],
            row_tooltips: dict[int, str],
    ) -> None:
        """Apply all three overlays in one repaint instead of three model resets."""
        self._set_annotations(
            matched_rows=matched_rows,
            problem_rows=problem_rows,
            row_tooltips=row_tooltips,
        )

    def _set_annotations(
            self,
            matched_rows: set[int] | None = None,
            problem_rows: set[int] | None = None,
            row_tooltips: dict[int, str] | None = None,
    ) -> None:
        # Annotations only change colours and tooltips. Resetting the model here would clear the
        # view's selection, so emit dataChanged instead.
        changed = False

        if matched_rows is not None and set(matched_rows) != self._matched_rows:
            self._matched_rows = set(matched_rows)
            changed = True

        if problem_rows is not None and set(problem_rows) != self._problem_rows:
            self._problem_rows = set(problem_rows)
            changed = True

        if row_tooltips is not None and dict(row_tooltips) != self._row_tooltips:
            self._row_tooltips = dict(row_tooltips)
            changed = True

        if not changed:
            return

        row_count = self.rowCount()
        if row_count == 0:
            return

        self.dataChanged.emit(
            self.index(0, 0),
            self.index(row_count - 1, self.columnCount() - 1),
            [
                Qt.ItemDataRole.BackgroundRole,
                Qt.ItemDataRole.ForegroundRole,
                Qt.ItemDataRole.ToolTipRole,
            ],
        )

    @property
    def view_mode(self) -> str:
        return self._view_mode

    def set_view_mode(self, mode: str) -> None:
        if mode == self._view_mode:
            return
        # The column count changes, so this genuinely is a structural reset.
        self.beginResetModel()
        self._view_mode = mode
        self.endResetModel()

    @property
    def _headers(self) -> list[str]:
        return HEADERS[self._view_mode]

    def record_at(self, row: int) -> LogRecord | None:
        return self._items[row] if 0 <= row < len(self._items) else None

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._items)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._headers)

    def headerData(self, section: int, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None

        if orientation == Qt.Orientation.Horizontal:
            if 0 <= section < len(self._headers):
                return tr(self._headers[section])
            return None
        return str(section + 1)

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        item = self._items[index.row()]
        row = index.row()

        if role == Qt.ItemDataRole.DisplayRole:
            return self._display(item, index.column())

        if role == Qt.ItemDataRole.BackgroundRole:
            if not item.valid:
                return QBrush(QColor(95, 30, 30))
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

    def _display(self, item: LogRecord, col: int):
        if self._view_mode == VIEW_RAW:
            return [
                str(item.timestamp_ms),
                item.source,
                item.direction.upper(),
                item.can_id_hex,
                str(item.frame_count),
                str(item.byte_count),
                tr("logs.value.ok") if item.valid else tr("logs.value.broken"),
                item.payload_hex,
            ][col]

        return [
            str(item.timestamp_ms),
            item.source,
            item.direction.upper(),
            self._message_title(item),
            self._summary(item),
            item.payload_hex,
        ][col]

    def _message_title(self, item: LogRecord) -> str:
        return message_label(item.category, item.msg_id)

    def _summary(self, item: LogRecord) -> str:
        if not item.valid:
            # A frame that failed reassembly has no fields to decode; say what went wrong.
            return item.note or tr("logs.value.broken")
        return build_log_summary(item)
