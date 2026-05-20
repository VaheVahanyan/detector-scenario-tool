from __future__ import annotations

from PySide6.QtCore import QRegularExpression
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import QFormLayout, QGroupBox, QLineEdit, QLabel, QSpinBox, QVBoxLayout

from detector_scenario_tool.i18n import tr
from detector_scenario_tool.ui.editors.payload_editor_base import PayloadEditorBase


class OrientationParamsPayloadEditor(PayloadEditorBase):
    def __init__(self) -> None:
        super().__init__()

        layout = QVBoxLayout(self)

        self.time_group = QGroupBox()
        self.time_form = QFormLayout(self.time_group)

        self.measurement_time_ms_spin = QSpinBox()
        self.measurement_time_ms_spin.setRange(0, 65535)

        self.measurement_time_s_edit = self._make_u32_edit()

        self.time_labels = [QLabel(), QLabel()]
        self.time_form.addRow(self.time_labels[0], self.measurement_time_ms_spin)
        self.time_form.addRow(self.time_labels[1], self.measurement_time_s_edit)

        self.quat_group = QGroupBox()
        self.quat_form = QFormLayout(self.quat_group)

        self.q0_edit = self._make_i32_edit()
        self.q1_edit = self._make_i32_edit()
        self.q2_edit = self._make_i32_edit()
        self.q3_edit = self._make_i32_edit()

        self.quat_labels = [QLabel(), QLabel(), QLabel(), QLabel()]
        self.quat_form.addRow(self.quat_labels[0], self.q0_edit)
        self.quat_form.addRow(self.quat_labels[1], self.q1_edit)
        self.quat_form.addRow(self.quat_labels[2], self.q2_edit)
        self.quat_form.addRow(self.quat_labels[3], self.q3_edit)

        layout.addWidget(self.time_group)
        layout.addWidget(self.quat_group)
        layout.addStretch(1)

        self.measurement_time_ms_spin.valueChanged.connect(self._emit_changed)
        self.measurement_time_s_edit.textChanged.connect(self._emit_changed)

        self.q0_edit.textChanged.connect(self._emit_changed)
        self.q1_edit.textChanged.connect(self._emit_changed)
        self.q2_edit.textChanged.connect(self._emit_changed)
        self.q3_edit.textChanged.connect(self._emit_changed)

        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        self.time_group.setTitle(tr("payload.orientation.group.time"))
        self.quat_group.setTitle(tr("payload.orientation.group.quaternion"))

        self.time_labels[0].setText(tr("payload.orientation.time_ms"))
        self.time_labels[1].setText(tr("payload.orientation.time_s"))
        self.measurement_time_s_edit.setPlaceholderText(tr("payload.time_sync.board_time_s_placeholder"))

        self.quat_labels[0].setText(tr("payload.orientation.q0"))
        self.quat_labels[1].setText(tr("payload.orientation.q1"))
        self.quat_labels[2].setText(tr("payload.orientation.q2"))
        self.quat_labels[3].setText(tr("payload.orientation.q3"))

        placeholder = tr("payload.orbit.i32_placeholder")
        self.q0_edit.setPlaceholderText(placeholder)
        self.q1_edit.setPlaceholderText(placeholder)
        self.q2_edit.setPlaceholderText(placeholder)
        self.q3_edit.setPlaceholderText(placeholder)

    def _make_u32_edit(self) -> QLineEdit:
        edit = QLineEdit()
        edit.setValidator(QRegularExpressionValidator(QRegularExpression(r"\d{0,10}")))
        return edit

    def _make_i32_edit(self) -> QLineEdit:
        edit = QLineEdit()
        edit.setValidator(
            QRegularExpressionValidator(QRegularExpression(r"-?\d{0,10}"))
        )
        return edit

    def _to_int(self, text: str, default: int = 0) -> int:
        text = text.strip()
        if not text or text == "-":
            return default
        return int(text)

    def set_payload(self, payload: dict) -> None:
        self._building = True

        self.measurement_time_ms_spin.setValue(int(payload.get("measurement_time_ms", 0)))
        self.measurement_time_s_edit.setText(str(int(payload.get("measurement_time_s", 0))))

        self.q0_edit.setText(str(int(payload.get("q0", 0))))
        self.q1_edit.setText(str(int(payload.get("q1", 0))))
        self.q2_edit.setText(str(int(payload.get("q2", 0))))
        self.q3_edit.setText(str(int(payload.get("q3", 0))))

        self._building = False

    def write_payload(self, payload: dict) -> None:
        payload["measurement_time_ms"] = self.measurement_time_ms_spin.value()
        payload["measurement_time_s"] = self._to_int(self.measurement_time_s_edit.text())

        payload["q0"] = self._to_int(self.q0_edit.text())
        payload["q1"] = self._to_int(self.q1_edit.text())
        payload["q2"] = self._to_int(self.q2_edit.text())
        payload["q3"] = self._to_int(self.q3_edit.text())

    def _emit_changed(self) -> None:
        if self._building:
            return
        self.changed.emit()
