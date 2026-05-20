from __future__ import annotations

from PySide6.QtCore import QRegularExpression
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import QFormLayout, QGroupBox, QLineEdit, QLabel, QSpinBox, QVBoxLayout

from detector_scenario_tool.i18n import tr
from detector_scenario_tool.ui.editors.payload_editor_base import PayloadEditorBase


class OrbitParamsPayloadEditor(PayloadEditorBase):
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

        self.coords_group = QGroupBox()
        self.coords_form = QFormLayout(self.coords_group)

        self.x_edit = self._make_i32_edit()
        self.y_edit = self._make_i32_edit()
        self.z_edit = self._make_i32_edit()

        self.coords_labels = [QLabel(), QLabel(), QLabel()]
        self.coords_form.addRow(self.coords_labels[0], self.x_edit)
        self.coords_form.addRow(self.coords_labels[1], self.y_edit)
        self.coords_form.addRow(self.coords_labels[2], self.z_edit)

        self.velocity_group = QGroupBox()
        self.velocity_form = QFormLayout(self.velocity_group)

        self.vx_edit = self._make_i32_edit()
        self.vy_edit = self._make_i32_edit()
        self.vz_edit = self._make_i32_edit()

        self.velocity_labels = [QLabel(), QLabel(), QLabel()]
        self.velocity_form.addRow(self.velocity_labels[0], self.vx_edit)
        self.velocity_form.addRow(self.velocity_labels[1], self.vy_edit)
        self.velocity_form.addRow(self.velocity_labels[2], self.vz_edit)

        self.misc_group = QGroupBox()
        self.misc_form = QFormLayout(self.misc_group)

        self.l_shell_spin = QSpinBox()
        self.l_shell_spin.setRange(0, 65535)

        self.b_field_spin = QSpinBox()
        self.b_field_spin.setRange(0, 65535)

        self.misc_labels = [QLabel(), QLabel()]
        self.misc_form.addRow(self.misc_labels[0], self.l_shell_spin)
        self.misc_form.addRow(self.misc_labels[1], self.b_field_spin)

        layout.addWidget(self.time_group)
        layout.addWidget(self.coords_group)
        layout.addWidget(self.velocity_group)
        layout.addWidget(self.misc_group)
        layout.addStretch(1)

        self.measurement_time_ms_spin.valueChanged.connect(self._emit_changed)
        self.measurement_time_s_edit.textChanged.connect(self._emit_changed)
        self.x_edit.textChanged.connect(self._emit_changed)
        self.y_edit.textChanged.connect(self._emit_changed)
        self.z_edit.textChanged.connect(self._emit_changed)
        self.vx_edit.textChanged.connect(self._emit_changed)
        self.vy_edit.textChanged.connect(self._emit_changed)
        self.vz_edit.textChanged.connect(self._emit_changed)
        self.l_shell_spin.valueChanged.connect(self._emit_changed)
        self.b_field_spin.valueChanged.connect(self._emit_changed)

        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        self.time_group.setTitle(tr("payload.orbit.group.time"))
        self.coords_group.setTitle(tr("payload.orbit.group.coords"))
        self.velocity_group.setTitle(tr("payload.orbit.group.velocity"))
        self.misc_group.setTitle(tr("payload.orbit.group.misc"))

        self.time_labels[0].setText(tr("payload.orbit.time_ms"))
        self.time_labels[1].setText(tr("payload.orbit.time_s"))
        self.measurement_time_s_edit.setPlaceholderText(tr("payload.time_sync.board_time_s_placeholder"))

        self.coords_labels[0].setText(tr("payload.orbit.x"))
        self.coords_labels[1].setText(tr("payload.orbit.y"))
        self.coords_labels[2].setText(tr("payload.orbit.z"))

        self.velocity_labels[0].setText(tr("payload.orbit.vx"))
        self.velocity_labels[1].setText(tr("payload.orbit.vy"))
        self.velocity_labels[2].setText(tr("payload.orbit.vz"))

        self.misc_labels[0].setText(tr("payload.orbit.l_shell"))
        self.misc_labels[1].setText(tr("payload.orbit.b_field"))

        placeholder = tr("payload.orbit.i32_placeholder")
        self.x_edit.setPlaceholderText(placeholder)
        self.y_edit.setPlaceholderText(placeholder)
        self.z_edit.setPlaceholderText(placeholder)
        self.vx_edit.setPlaceholderText(placeholder)
        self.vy_edit.setPlaceholderText(placeholder)
        self.vz_edit.setPlaceholderText(placeholder)

    def _make_u32_edit(self) -> QLineEdit:
        edit = QLineEdit()
        edit.setValidator(QRegularExpressionValidator(QRegularExpression(r"\d{0,10}")))
        return edit

    def _make_i32_edit(self) -> QLineEdit:
        edit = QLineEdit()
        edit.setValidator(QRegularExpressionValidator(QRegularExpression(r"-?\d{0,10}")))
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

        self.x_edit.setText(str(int(payload.get("x", 0))))
        self.y_edit.setText(str(int(payload.get("y", 0))))
        self.z_edit.setText(str(int(payload.get("z", 0))))

        self.vx_edit.setText(str(int(payload.get("vx", 0))))
        self.vy_edit.setText(str(int(payload.get("vy", 0))))
        self.vz_edit.setText(str(int(payload.get("vz", 0))))

        self.l_shell_spin.setValue(int(payload.get("l_shell", 0)))
        self.b_field_spin.setValue(int(payload.get("b_field", 0)))

        self._building = False

    def write_payload(self, payload: dict) -> None:
        payload["measurement_time_ms"] = self.measurement_time_ms_spin.value()
        payload["measurement_time_s"] = self._to_int(self.measurement_time_s_edit.text())

        payload["x"] = self._to_int(self.x_edit.text())
        payload["y"] = self._to_int(self.y_edit.text())
        payload["z"] = self._to_int(self.z_edit.text())

        payload["vx"] = self._to_int(self.vx_edit.text())
        payload["vy"] = self._to_int(self.vy_edit.text())
        payload["vz"] = self._to_int(self.vz_edit.text())

        payload["l_shell"] = self.l_shell_spin.value()
        payload["b_field"] = self.b_field_spin.value()

    def _emit_changed(self) -> None:
        if self._building:
            return
        self.changed.emit()
