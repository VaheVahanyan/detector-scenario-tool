from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor, QBrush

from detector_scenario_tool.domain.scenario import (
    CommentStep,
    ScenarioDocument,
    SendMessageStep,
    WaitForTsStep,
    WaitTimeStep,
)
from detector_scenario_tool.i18n import tr
from detector_scenario_tool.protocol import registry
from detector_scenario_tool.protocol.format_values import format_field_value
from detector_scenario_tool.utils.labels import category_short, message_label_from_ref

#: How many payload fields the target column shows before it reports a count.
SUMMARY_FIELD_LIMIT = 3


class ScenarioTableModel(QAbstractTableModel):
    HEADER_KEYS = [
        "scenario.column.index",
        "scenario.column.enabled",
        "scenario.column.kind",
        "scenario.column.message_target",
        "scenario.column.timeout",
        "scenario.column.comment",
    ]

    def __init__(self, document: ScenarioDocument) -> None:
        super().__init__()
        self.document = document
        self._row_statuses: dict[int, str] = {}

    def set_document(self, document: ScenarioDocument) -> None:
        self.beginResetModel()
        self.document = document
        self._row_statuses = {}
        self.endResetModel()

    def set_row_statuses(self, row_statuses: dict[int, str]) -> None:
        # Statuses only affect colours, so signal a repaint instead of resetting the model.
        # A reset clears the view's selection, which used to knock the inspector back to its
        # empty page on every keystroke.
        row_statuses = dict(row_statuses)
        if row_statuses == self._row_statuses:
            return

        self._row_statuses = row_statuses

        row_count = self.rowCount()
        if row_count == 0:
            return

        self.dataChanged.emit(
            self.index(0, 0),
            self.index(row_count - 1, self.columnCount() - 1),
            [Qt.ItemDataRole.BackgroundRole, Qt.ItemDataRole.ForegroundRole],
        )

    def refresh(self) -> None:
        self.layoutAboutToBeChanged.emit()
        self.layoutChanged.emit()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self.document.steps)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self.HEADER_KEYS)

    def headerData(self, section: int, orientation, role=Qt.ItemDataRole.DisplayRole):
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

        row = index.row()
        col = index.column()
        step = self.document.steps[row]

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return str(row + 1)

            if col == 1:
                return "✓" if getattr(step, "enabled", True) else ""

            if col == 2:
                return self._step_kind_text(step)

            if col == 3:
                return self._step_message_target_text(step)

            if col == 4:
                return self._step_timeout_text(step)

            if col == 5:
                return self._step_comment_text(step)

        if role == Qt.ItemDataRole.ToolTipRole and col == 4:
            return self._step_timeout_tooltip(step)

        status = self._row_statuses.get(row, "neutral")

        if role == Qt.ItemDataRole.BackgroundRole:
            if status == "ok":
                return QBrush(QColor(35, 70, 35))
            if status == "warning":
                return QBrush(QColor(80, 70, 30))
            if status == "error":
                return QBrush(QColor(85, 35, 35))
            if status == "current":
                return QBrush(QColor(30, 55, 90))
            if status == "pending":
                return QBrush(QColor(55, 55, 55))

        if role == Qt.ItemDataRole.ForegroundRole:
            if status in {"ok", "warning", "error", "current", "pending"}:
                return QBrush(QColor(235, 235, 235))

        return None

    def _step_kind_text(self, step) -> str:
        if isinstance(step, SendMessageStep):
            category = step.message.category if step.message is not None else None
            return tr(
                "scenario.step.send",
                category=category_short(category) if category else "?",
            )

        if isinstance(step, WaitForTsStep):
            return tr("scenario.step.wait_ts", category=category_short("TS"))

        if isinstance(step, WaitTimeStep):
            return tr("scenario.step.wait")

        if isinstance(step, CommentStep):
            return tr("scenario.step.comment")

        return type(step).__name__

    def _step_message_target_text(self, step) -> str:
        if isinstance(step, SendMessageStep):
            return self._message_summary(step)

        if isinstance(step, WaitForTsStep):
            return message_label_from_ref(step.expected)

        if isinstance(step, WaitTimeStep):
            return tr("scenario.step.ms", value=step.delay_ms)

        if isinstance(step, CommentStep):
            return step.title or ""

        return "-"

    def _step_timeout_text(self, step) -> str:
        """Only real timeouts belong in this column.

        A WAIT step's `delay_ms` is a planned pause, not a deadline, and it is already shown in
        the target column — printing it here under a "Timeout" header said the wrong thing.
        """
        if isinstance(step, SendMessageStep):
            return "" if step.ack_timeout_ms is None else str(step.ack_timeout_ms)

        if isinstance(step, WaitForTsStep):
            return str(step.timeout_ms)

        return ""

    def _step_timeout_tooltip(self, step) -> str | None:
        """The column means a different deadline per step kind, so say which one."""
        if isinstance(step, SendMessageStep):
            if step.ack_timeout_ms is None:
                return None
            return tr("scenario.tooltip.ack_timeout", value=step.ack_timeout_ms)

        if isinstance(step, WaitForTsStep):
            return tr(
                "scenario.tooltip.wait_timeout",
                value=step.timeout_ms,
                category=category_short("TS"),
            )

        if isinstance(step, WaitTimeStep):
            return tr("scenario.tooltip.no_timeout")

        return None

    def _step_comment_text(self, step) -> str:
        return getattr(step, "comment", "") or ""

    def _message_summary(self, step: SendMessageStep) -> str:
        """`КУ 0x0008 Стирание ППЗУ [Банк ППЗУ NAND=NAND2, …]`.

        The interesting payload fields are picked from the message definition rather than from a
        per-message branch, so a new command shows a useful summary with no code here.
        """
        label = message_label_from_ref(step.message)
        if step.message is None or step.message.msg_id is None:
            return label

        spec = registry.find(step.message.category, step.message.msg_id)
        if spec is None:
            return label

        parts = []
        for field_spec in spec.editable_fields:
            if field_spec.key not in step.payload:
                continue
            parts.append(
                f"{field_spec.label}={format_field_value(field_spec, step.payload[field_spec.key])}"
            )
            if len(parts) >= SUMMARY_FIELD_LIMIT:
                break

        if not parts:
            return label

        remaining = sum(1 for f in spec.editable_fields if f.key in step.payload) - len(parts)
        summary = ", ".join(parts)
        if remaining > 0:
            summary += tr("logdecode.more_fields", count=remaining)
        return f"{label} [{summary}]"
