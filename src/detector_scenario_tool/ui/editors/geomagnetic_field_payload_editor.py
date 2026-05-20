from __future__ import annotations

from PySide6.QtCore import QRegularExpression
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import QFormLayout, QGroupBox, QLineEdit, QLabel, QSpinBox, QVBoxLayout

from detector_scenario_tool.i18n import tr
from detector_scenario_tool.ui.editors.payload_editor_base import PayloadEditorBase


class GeomagneticFieldPayloadEditor(PayloadEditorBase):
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

        self.field_group = QGroupBox()
        self.field_form = QFormLayout(self.field_group)

        self.bx_edit = self._make_i32_edit()
        self.by_edit = self._make_i32_edit()
        self.bz_edit = self._make_i32_edit()

        self.field_labels = [QLabel(), QLabel(), QLabel()]
        self.field_form.addRow(self.field_labels[0], self.bx_edit)
        self.field_form.addRow(self.field_labels[1], self.by_edit)
        self.field_form.addRow(self.field_labels[2], self.bz_edit)

        layout.addWidget(self.time_group)
        layout.addWidget(self.field_group)
        layout.addStretch(1)

        self.measurement_time_ms_spin.valueChanged.connect(self._emit_changed)
        self.measurement_time_s_edit.textChanged.connect(self._emit_changed)

        self.bx_edit.textChanged.connect(self._emit_changed)
        self.by_edit.textChanged.connect(self._emit_changed)
        self.bz_edit.textChanged.connect(self._emit_changed)

        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        self.time_group.setTitle(tr("payload.geomagnetic.group.time"))
        self.field_group.setTitle(tr("payload.geomagnetic.group.vector"))

        self.time_labels[0].setText(tr("payload.geomagnetic.time_ms"))
        self.time_labels[1].setText(tr("payload.geomagnetic.time_s"))
        self.measurement_time_s_edit.setPlaceholderText(tr("payload.time_sync.board_time_s_placeholder"))

        self.field_labels[0].setText(tr("payload.geomagnetic.bx"))
        self.field_labels[1].setText(tr("payload.geomagnetic.by"))
        self.field_labels[2].setText(tr("payload.geomagnetic.bz"))

        placeholder = tr("payload.orbit.i32_placeholder")
        self.bx_edit.setPlaceholderText(placeholder)
        self.by_edit.setPlaceholderText(placeholder)
        self.bz_edit.setPlaceholderText(placeholder)

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

        self.bx_edit.setText(str(int(payload.get("bx", 0))))
        self.by_edit.setText(str(int(payload.get("by", 0))))
        self.bz_edit.setText(str(int(payload.get("bz", 0))))

        self._building = False

    def write_payload(self, payload: dict) -> None:
        payload["measurement_time_ms"] = self.measurement_time_ms_spin.value()
        payload["measurement_time_s"] = self._to_int(self.measurement_time_s_edit.text())

        payload["bx"] = self._to_int(self.bx_edit.text())
        payload["by"] = self._to_int(self.by_edit.text())
        payload["bz"] = self._to_int(self.bz_edit.text())

    def _emit_changed(self) -> None:
        if self._building:
            return
        self.changed.emit()
