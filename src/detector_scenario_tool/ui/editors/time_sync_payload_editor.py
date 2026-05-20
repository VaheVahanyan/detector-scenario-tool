from __future__ import annotations

from PySide6.QtCore import QRegularExpression
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import QFormLayout, QLabel, QLineEdit, QSpinBox

from detector_scenario_tool.i18n import tr
from detector_scenario_tool.ui.editors.payload_editor_base import PayloadEditorBase


class TimeSyncPayloadEditor(PayloadEditorBase):
    def __init__(self) -> None:
        super().__init__()

        self.layout_form = QFormLayout(self)

        self.board_time_ms_spin = QSpinBox()
        self.board_time_ms_spin.setRange(0, 65535)

        self.board_time_s_edit = QLineEdit()
        self.board_time_s_edit.setValidator(
            QRegularExpressionValidator(QRegularExpression(r"\d{0,10}"))
        )

        self.label_board_time_ms = QLabel()
        self.label_board_time_s = QLabel()

        self.layout_form.addRow(self.label_board_time_ms, self.board_time_ms_spin)
        self.layout_form.addRow(self.label_board_time_s, self.board_time_s_edit)

        self.board_time_ms_spin.valueChanged.connect(self._emit_changed)
        self.board_time_s_edit.textChanged.connect(self._emit_changed)

        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        self.label_board_time_ms.setText(tr("payload.time_sync.board_time_ms"))
        self.label_board_time_s.setText(tr("payload.time_sync.board_time_s"))
        self.board_time_s_edit.setPlaceholderText(tr("payload.time_sync.board_time_s_placeholder"))

    def set_payload(self, payload: dict) -> None:
        self._building = True
        self.board_time_ms_spin.setValue(int(payload.get("board_time_ms", 0)))
        self.board_time_s_edit.setText(str(int(payload.get("board_time_s", 0))))
        self._building = False

    def write_payload(self, payload: dict) -> None:
        payload["board_time_ms"] = self.board_time_ms_spin.value()

        board_time_s_text = self.board_time_s_edit.text().strip()
        payload["board_time_s"] = int(board_time_s_text) if board_time_s_text else 0

    def _emit_changed(self) -> None:
        if self._building:
            return
        self.changed.emit()
