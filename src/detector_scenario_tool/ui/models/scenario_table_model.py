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
        self.beginResetModel()
        self._row_statuses = dict(row_statuses)
        self.endResetModel()

    def refresh(self) -> None:
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
            category = step.message.category if step.message is not None else "?"
            return tr("scenario.step.send", category=category)

        if isinstance(step, WaitForTsStep):
            return tr("scenario.step.wait_ts")

        if isinstance(step, WaitTimeStep):
            return tr("scenario.step.wait")

        if isinstance(step, CommentStep):
            return tr("scenario.step.comment")

        return type(step).__name__

    def _step_message_target_text(self, step) -> str:
        if isinstance(step, SendMessageStep):
            if step.message is None or step.message.msg_id is None:
                return "-"
            return self._message_summary(step)

        if isinstance(step, WaitForTsStep):
            if step.expected is None or step.expected.msg_id is None:
                return "-"
            if step.expected.name:
                return f"TS 0x{step.expected.msg_id:04X} {step.expected.name}"
            return f"TS 0x{step.expected.msg_id:04X}"

        if isinstance(step, WaitTimeStep):
            return tr("scenario.step.ms", value=step.delay_ms)

        if isinstance(step, CommentStep):
            return step.title or ""

        return "-"

    def _step_timeout_text(self, step) -> str:
        if isinstance(step, SendMessageStep):
            return "" if step.ack_timeout_ms is None else str(step.ack_timeout_ms)

        if isinstance(step, WaitForTsStep):
            return str(step.timeout_ms)

        if isinstance(step, WaitTimeStep):
            return str(step.delay_ms)

        return ""

    def _step_comment_text(self, step) -> str:
        return getattr(step, "comment", "") or ""

    def _message_summary(self, step: SendMessageStep) -> str:
        if step.message is None or step.message.msg_id is None:
            return "-"

        name = step.message.name or ""
        base = f"{step.message.category} 0x{step.message.msg_id:04X}"
        if name:
            base += f" {name}"

        if step.message.category == "KU" and step.message.msg_id in (0x0000, 0x0001, 0x000B, 0x000C):
            return f"{base} [fixed=AA AA AA AA AA AA]"

        if step.message.category == "KU" and step.message.msg_id == 0x0002:
            board_time_ms = step.payload.get("board_time_ms")
            board_time_s = step.payload.get("board_time_s")
            if board_time_ms is not None or board_time_s is not None:
                return (
                    f"{base} "
                    f"[ms={board_time_ms if board_time_ms is not None else '-'}, "
                    f"s={board_time_s if board_time_s is not None else '-'}]"
                )

        if step.message.category == "KU" and step.message.msg_id == 0x0003:
            selected_nand_bank = step.payload.get("selected_nand_bank", "-")
            ped_power_enabled = step.payload.get("ped_power_enabled", False)
            ped_low_power = step.payload.get("ped_low_power", False)
            ped_event_registration = step.payload.get("ped_event_registration", False)

            event_format_mode = step.payload.get("event_format_mode", 0)
            event_count_mode = step.payload.get("event_count_mode", 0)
            spectrum_mode = step.payload.get("spectrum_mode", 0)
            histogram_cells = step.payload.get("histogram_cells", 0)
            particle_threshold = step.payload.get("particle_threshold", 0)

            return (
                f"{base} "
                f"[bank={selected_nand_bank}, "
                f"ped_power={ped_power_enabled}, "
                f"low_power={ped_low_power}, "
                f"event_reg={ped_event_registration}, "
                f"event_fmt={event_format_mode}, "
                f"event_cnt={event_count_mode}, "
                f"spectrum={spectrum_mode}, "
                f"hist={histogram_cells}, "
                f"thr={particle_threshold}]"
            )

        if step.message.category == "KU" and step.message.msg_id == 0x0004:
            ped_power_enabled = step.payload.get("ped_power_enabled", False)
            ped_low_power = step.payload.get("ped_low_power", False)
            ped_event_registration = step.payload.get("ped_event_registration", False)

            event_format_mode = step.payload.get("event_format_mode", 0)
            event_count_mode = step.payload.get("event_count_mode", 0)
            spectrum_mode = step.payload.get("spectrum_mode", 0)
            histogram_cells = step.payload.get("histogram_cells", 0)

            return (
                f"{base} "
                f"[ped_power={ped_power_enabled}, "
                f"low_power={ped_low_power}, "
                f"event_reg={ped_event_registration}, "
                f"event_fmt={event_format_mode}, "
                f"event_cnt={event_count_mode}, "
                f"spectrum={spectrum_mode}, "
                f"hist={histogram_cells}]"
            )

        if step.message.category == "KU" and step.message.msg_id == 0x0005:
            return (
                f"{base} "
                f"[bank={step.payload.get('selected_nand_bank', '-')}, "
                f"nand_power={step.payload.get('nand_power_enabled', False)}, "
                f"ped_power={step.payload.get('ped_power_enabled', False)}, "
                f"low_power={step.payload.get('ped_low_power', False)}]"
            )

        if step.message.category == "KU" and step.message.msg_id == 0x0006:
            selected_nand_bank = step.payload.get("selected_nand_bank", "-")
            keep_power_after_output = step.payload.get("keep_power_after_output", False)
            output_interface = step.payload.get("output_interface", "usb")
            output_type = step.payload.get("output_type", "requested_count")
            requested_packet_count = step.payload.get("requested_packet_count", 0)

            return (
                f"{base} "
                f"[bank={selected_nand_bank}, "
                f"keep_power={keep_power_after_output}, "
                f"iface={output_interface}, "
                f"type={output_type}, "
                f"packets={requested_packet_count}]"
            )

        if step.message.category == "KU" and step.message.msg_id == 0x0007:
            return (
                f"{base} "
                f"[session_id={step.payload.get('session_id', 0)}, "
                f"init_rtc={step.payload.get('initial_rtc', 0)}, "
                f"nand1_packets={step.payload.get('nand1_packet_count', 0)}, "
                f"nand2_packets={step.payload.get('nand2_packet_count', 0)}, "
                f"alarm_mask={step.payload.get('alarm_mask', 0)}]"
            )

        if step.message.category == "KU" and step.message.msg_id == 0x0008:
            return (
                f"{base} "
                f"[bank={step.payload.get('selected_nand_bank', '-')}, "
                f"keep_power={step.payload.get('keep_power_after_erase', False)}]"
            )

        if step.message.category == "KU" and step.message.msg_id == 0x0009:
            return (
                f"{base} "
                f"[bank={step.payload.get('selected_nand_bank', '-')}, "
                f"keep_power={step.payload.get('keep_power_after_test', False)}]"
            )

        if step.message.category == "KU" and step.message.msg_id == 0x000A:
            return (
                f"{base} "
                f"[bank={step.payload.get('selected_nand_bank', '-')}]"
            )

        if step.message.category == "KT" and step.message.msg_id == 0x0100:
            board_time_ms = step.payload.get("board_time_ms")
            board_time_s = step.payload.get("board_time_s")

            return (
                f"{base} "
                f"[ms={board_time_ms if board_time_ms is not None else '-'}, "
                f"s={board_time_s if board_time_s is not None else '-'}]"
            )

        if step.message.category == "KT" and step.message.msg_id == 0x0101:
            return (
                f"{base} "
                f"[t={step.payload.get('measurement_time_s', 0)}."
                f"{step.payload.get('measurement_time_ms', 0)}, "
                f"xyz=({step.payload.get('x', 0)}, {step.payload.get('y', 0)}, {step.payload.get('z', 0)}), "
                f"v=({step.payload.get('vx', 0)}, {step.payload.get('vy', 0)}, {step.payload.get('vz', 0)}), "
                f"L={step.payload.get('l_shell', 0)}, "
                f"B={step.payload.get('b_field', 0)}]"
            )

        if step.message.category == "KT" and step.message.msg_id == 0x0102:
            return (
                f"{base} "
                f"[t={step.payload.get('measurement_time_s', 0)}."
                f"{step.payload.get('measurement_time_ms', 0)}, "
                f"q=({step.payload.get('q0', 0)}, {step.payload.get('q1', 0)}, "
                f"{step.payload.get('q2', 0)}, {step.payload.get('q3', 0)})]"
            )

        if step.message.category == "KT" and step.message.msg_id == 0x0103:
            return (
                f"{base} "
                f"[t={step.payload.get('measurement_time_s', 0)}."
                f"{step.payload.get('measurement_time_ms', 0)}, "
                f"B=({step.payload.get('bx', 0)}, {step.payload.get('by', 0)}, {step.payload.get('bz', 0)})]"
            )

        return base
