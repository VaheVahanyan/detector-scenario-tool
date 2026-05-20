from __future__ import annotations

from PySide6.QtCore import QRegularExpression
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QLineEdit,
    QLabel,
    QSpinBox,
    QVBoxLayout,
)

from detector_scenario_tool.i18n import tr
from detector_scenario_tool.ui.editors.payload_editor_base import PayloadEditorBase


class SettingsPayloadEditor(PayloadEditorBase):
    def __init__(self) -> None:
        super().__init__()

        layout = QVBoxLayout(self)

        self.control_group = QGroupBox()
        self.control_form = QFormLayout(self.control_group)

        self.write_session_id_checkbox = QCheckBox()
        self.write_nand1_packet_count_checkbox = QCheckBox()
        self.write_nand2_packet_count_checkbox = QCheckBox()
        self.write_nand1_erase_count_checkbox = QCheckBox()
        self.write_nand2_erase_count_checkbox = QCheckBox()
        self.write_nand1_test_count_checkbox = QCheckBox()
        self.write_nand2_test_count_checkbox = QCheckBox()

        self.control_labels = [QLabel() for _ in range(7)]
        self.control_form.addRow(self.control_labels[0], self.write_session_id_checkbox)
        self.control_form.addRow(self.control_labels[1], self.write_nand1_packet_count_checkbox)
        self.control_form.addRow(self.control_labels[2], self.write_nand2_packet_count_checkbox)
        self.control_form.addRow(self.control_labels[3], self.write_nand1_erase_count_checkbox)
        self.control_form.addRow(self.control_labels[4], self.write_nand2_erase_count_checkbox)
        self.control_form.addRow(self.control_labels[5], self.write_nand1_test_count_checkbox)
        self.control_form.addRow(self.control_labels[6], self.write_nand2_test_count_checkbox)

        self.temp_group = QGroupBox()
        self.temp_form = QFormLayout(self.temp_group)

        self.min_mc_temp_spin = self._make_i16_spin()
        self.max_mc_temp_spin = self._make_i16_spin()
        self.min_pu_temp_spin = self._make_i16_spin()
        self.max_pu_temp_spin = self._make_i16_spin()
        self.min_ped_temp_spin = self._make_i16_spin()
        self.max_ped_temp_spin = self._make_i16_spin()
        self.min_bd_temp_spin = self._make_i16_spin()
        self.max_bd_temp_spin = self._make_i16_spin()

        self.temp_labels = [QLabel() for _ in range(8)]
        self.temp_form.addRow(self.temp_labels[0], self.min_mc_temp_spin)
        self.temp_form.addRow(self.temp_labels[1], self.max_mc_temp_spin)
        self.temp_form.addRow(self.temp_labels[2], self.min_pu_temp_spin)
        self.temp_form.addRow(self.temp_labels[3], self.max_pu_temp_spin)
        self.temp_form.addRow(self.temp_labels[4], self.min_ped_temp_spin)
        self.temp_form.addRow(self.temp_labels[5], self.max_ped_temp_spin)
        self.temp_form.addRow(self.temp_labels[6], self.min_bd_temp_spin)
        self.temp_form.addRow(self.temp_labels[7], self.max_bd_temp_spin)

        self.power_group = QGroupBox()
        self.power_form = QFormLayout(self.power_group)

        self.min_pu_voltage_spin = self._make_u16_spin()
        self.max_pu_voltage_spin = self._make_u16_spin()
        self.min_pu_current_spin = self._make_u16_spin()
        self.max_pu_current_spin = self._make_u16_spin()
        self.min_ped_voltage_spin = self._make_u16_spin()
        self.max_ped_voltage_spin = self._make_u16_spin()
        self.min_ped_current_spin = self._make_u16_spin()
        self.max_ped_current_spin = self._make_u16_spin()

        self.power_labels = [QLabel() for _ in range(8)]
        self.power_form.addRow(self.power_labels[0], self.min_pu_voltage_spin)
        self.power_form.addRow(self.power_labels[1], self.max_pu_voltage_spin)
        self.power_form.addRow(self.power_labels[2], self.min_pu_current_spin)
        self.power_form.addRow(self.power_labels[3], self.max_pu_current_spin)
        self.power_form.addRow(self.power_labels[4], self.min_ped_voltage_spin)
        self.power_form.addRow(self.power_labels[5], self.max_ped_voltage_spin)
        self.power_form.addRow(self.power_labels[6], self.min_ped_current_spin)
        self.power_form.addRow(self.power_labels[7], self.max_ped_current_spin)

        self.radiation_group = QGroupBox()
        self.radiation_form = QFormLayout(self.radiation_group)

        self.outer_radiation_lmin_spin = self._make_u16_spin()
        self.outer_radiation_lmax_spin = self._make_u16_spin()
        self.inner_radiation_bmin_spin = self._make_u16_spin()
        self.ac1_max_count_spin = self._make_u16_spin()

        self.radiation_labels = [QLabel() for _ in range(4)]
        self.radiation_form.addRow(self.radiation_labels[0], self.outer_radiation_lmin_spin)
        self.radiation_form.addRow(self.radiation_labels[1], self.outer_radiation_lmax_spin)
        self.radiation_form.addRow(self.radiation_labels[2], self.inner_radiation_bmin_spin)
        self.radiation_form.addRow(self.radiation_labels[3], self.ac1_max_count_spin)

        self.rtc_group = QGroupBox()
        self.rtc_form = QFormLayout(self.rtc_group)

        self.initial_rtc_edit = QLineEdit()
        self.initial_rtc_edit.setValidator(
            QRegularExpressionValidator(QRegularExpression(r"\d{0,10}"))
        )
        self.rtc_label = QLabel()
        self.rtc_form.addRow(self.rtc_label, self.initial_rtc_edit)

        self.misc_group = QGroupBox()
        self.misc_form = QFormLayout(self.misc_group)

        self.session_id_spin = self._make_u16_spin()
        self.nand1_packet_count_spin = self._make_u24_spin()
        self.nand2_packet_count_spin = self._make_u24_spin()
        self.nand1_erase_count_spin = self._make_u16_spin()
        self.nand2_erase_count_spin = self._make_u16_spin()
        self.nand1_test_count_spin = self._make_u16_spin()
        self.nand2_test_count_spin = self._make_u16_spin()
        self.alarm_mask_spin = self._make_u16_spin()

        self.misc_labels = [QLabel() for _ in range(8)]
        self.misc_form.addRow(self.misc_labels[0], self.session_id_spin)
        self.misc_form.addRow(self.misc_labels[1], self.nand1_packet_count_spin)
        self.misc_form.addRow(self.misc_labels[2], self.nand2_packet_count_spin)
        self.misc_form.addRow(self.misc_labels[3], self.nand1_erase_count_spin)
        self.misc_form.addRow(self.misc_labels[4], self.nand2_erase_count_spin)
        self.misc_form.addRow(self.misc_labels[5], self.nand1_test_count_spin)
        self.misc_form.addRow(self.misc_labels[6], self.nand2_test_count_spin)
        self.misc_form.addRow(self.misc_labels[7], self.alarm_mask_spin)

        layout.addWidget(self.control_group)
        layout.addWidget(self.temp_group)
        layout.addWidget(self.power_group)
        layout.addWidget(self.radiation_group)
        layout.addWidget(self.rtc_group)
        layout.addWidget(self.misc_group)
        layout.addStretch(1)

        self._connect_changed()
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        self.control_group.setTitle(tr("payload.settings.group.control"))
        self.temp_group.setTitle(tr("payload.settings.group.temp"))
        self.power_group.setTitle(tr("payload.settings.group.power"))
        self.radiation_group.setTitle(tr("payload.settings.group.radiation"))
        self.rtc_group.setTitle(tr("payload.settings.group.rtc"))
        self.misc_group.setTitle(tr("payload.settings.group.misc"))

        control_keys = [
            "payload.settings.write_session_id",
            "payload.settings.write_nand1_packet_count",
            "payload.settings.write_nand2_packet_count",
            "payload.settings.write_nand1_erase_count",
            "payload.settings.write_nand2_erase_count",
            "payload.settings.write_nand1_test_count",
            "payload.settings.write_nand2_test_count",
        ]
        for label, key in zip(self.control_labels, control_keys):
            label.setText(tr(key))

        temp_keys = [
            "payload.settings.min_mc_temp",
            "payload.settings.max_mc_temp",
            "payload.settings.min_pu_temp",
            "payload.settings.max_pu_temp",
            "payload.settings.min_ped_temp",
            "payload.settings.max_ped_temp",
            "payload.settings.min_bd_temp",
            "payload.settings.max_bd_temp",
        ]
        for label, key in zip(self.temp_labels, temp_keys):
            label.setText(tr(key))

        power_keys = [
            "payload.settings.min_pu_voltage",
            "payload.settings.max_pu_voltage",
            "payload.settings.min_pu_current",
            "payload.settings.max_pu_current",
            "payload.settings.min_ped_voltage",
            "payload.settings.max_ped_voltage",
            "payload.settings.min_ped_current",
            "payload.settings.max_ped_current",
        ]
        for label, key in zip(self.power_labels, power_keys):
            label.setText(tr(key))

        radiation_keys = [
            "payload.settings.outer_radiation_lmin",
            "payload.settings.outer_radiation_lmax",
            "payload.settings.inner_radiation_bmin",
            "payload.settings.ac1_max_count",
        ]
        for label, key in zip(self.radiation_labels, radiation_keys):
            label.setText(tr(key))

        self.rtc_label.setText(tr("payload.settings.initial_rtc"))
        self.initial_rtc_edit.setPlaceholderText(tr("payload.time_sync.board_time_s_placeholder"))

        misc_keys = [
            "payload.settings.session_id",
            "payload.settings.nand1_packet_count",
            "payload.settings.nand2_packet_count",
            "payload.settings.nand1_erase_count",
            "payload.settings.nand2_erase_count",
            "payload.settings.nand1_test_count",
            "payload.settings.nand2_test_count",
            "payload.settings.alarm_mask",
        ]
        for label, key in zip(self.misc_labels, misc_keys):
            label.setText(tr(key))

    def _make_i16_spin(self) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(-32768, 32767)
        return spin

    def _make_u16_spin(self) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(0, 65535)
        return spin

    def _make_u24_spin(self) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(0, 16777215)
        return spin

    def _connect_changed(self) -> None:
        widgets = [
            self.write_session_id_checkbox,
            self.write_nand1_packet_count_checkbox,
            self.write_nand2_packet_count_checkbox,
            self.write_nand1_erase_count_checkbox,
            self.write_nand2_erase_count_checkbox,
            self.write_nand1_test_count_checkbox,
            self.write_nand2_test_count_checkbox,
            self.min_mc_temp_spin,
            self.max_mc_temp_spin,
            self.min_pu_temp_spin,
            self.max_pu_temp_spin,
            self.min_ped_temp_spin,
            self.max_ped_temp_spin,
            self.min_bd_temp_spin,
            self.max_bd_temp_spin,
            self.min_pu_voltage_spin,
            self.max_pu_voltage_spin,
            self.min_pu_current_spin,
            self.max_pu_current_spin,
            self.min_ped_voltage_spin,
            self.max_ped_voltage_spin,
            self.min_ped_current_spin,
            self.max_ped_current_spin,
            self.outer_radiation_lmin_spin,
            self.outer_radiation_lmax_spin,
            self.inner_radiation_bmin_spin,
            self.ac1_max_count_spin,
            self.initial_rtc_edit,
            self.session_id_spin,
            self.nand1_packet_count_spin,
            self.nand2_packet_count_spin,
            self.nand1_erase_count_spin,
            self.nand2_erase_count_spin,
            self.nand1_test_count_spin,
            self.nand2_test_count_spin,
            self.alarm_mask_spin,
        ]

        for widget in widgets:
            if hasattr(widget, "stateChanged"):
                widget.stateChanged.connect(self._emit_changed)
            elif hasattr(widget, "valueChanged"):
                widget.valueChanged.connect(self._emit_changed)
            elif hasattr(widget, "textChanged"):
                widget.textChanged.connect(self._emit_changed)

    def set_payload(self, payload: dict) -> None:
        self._building = True

        self.write_session_id_checkbox.setChecked(bool(payload.get("write_session_id", False)))
        self.write_nand1_packet_count_checkbox.setChecked(bool(payload.get("write_nand1_packet_count", False)))
        self.write_nand2_packet_count_checkbox.setChecked(bool(payload.get("write_nand2_packet_count", False)))
        self.write_nand1_erase_count_checkbox.setChecked(bool(payload.get("write_nand1_erase_count", False)))
        self.write_nand2_erase_count_checkbox.setChecked(bool(payload.get("write_nand2_erase_count", False)))
        self.write_nand1_test_count_checkbox.setChecked(bool(payload.get("write_nand1_test_count", False)))
        self.write_nand2_test_count_checkbox.setChecked(bool(payload.get("write_nand2_test_count", False)))

        self.min_mc_temp_spin.setValue(int(payload.get("min_mc_temp", 0)))
        self.max_mc_temp_spin.setValue(int(payload.get("max_mc_temp", 0)))
        self.min_pu_temp_spin.setValue(int(payload.get("min_pu_temp", 0)))
        self.max_pu_temp_spin.setValue(int(payload.get("max_pu_temp", 0)))
        self.min_ped_temp_spin.setValue(int(payload.get("min_ped_temp", 0)))
        self.max_ped_temp_spin.setValue(int(payload.get("max_ped_temp", 0)))
        self.min_bd_temp_spin.setValue(int(payload.get("min_bd_temp", 0)))
        self.max_bd_temp_spin.setValue(int(payload.get("max_bd_temp", 0)))

        self.min_pu_voltage_spin.setValue(int(payload.get("min_pu_voltage", 0)))
        self.max_pu_voltage_spin.setValue(int(payload.get("max_pu_voltage", 0)))
        self.min_pu_current_spin.setValue(int(payload.get("min_pu_current", 0)))
        self.max_pu_current_spin.setValue(int(payload.get("max_pu_current", 0)))
        self.min_ped_voltage_spin.setValue(int(payload.get("min_ped_voltage", 0)))
        self.max_ped_voltage_spin.setValue(int(payload.get("max_ped_voltage", 0)))
        self.min_ped_current_spin.setValue(int(payload.get("min_ped_current", 0)))
        self.max_ped_current_spin.setValue(int(payload.get("max_ped_current", 0)))

        self.outer_radiation_lmin_spin.setValue(int(payload.get("outer_radiation_lmin", 0)))
        self.outer_radiation_lmax_spin.setValue(int(payload.get("outer_radiation_lmax", 0)))
        self.inner_radiation_bmin_spin.setValue(int(payload.get("inner_radiation_bmin", 0)))
        self.ac1_max_count_spin.setValue(int(payload.get("ac1_max_count", 0)))

        self.initial_rtc_edit.setText(str(int(payload.get("initial_rtc", 0))))

        self.session_id_spin.setValue(int(payload.get("session_id", 0)))
        self.nand1_packet_count_spin.setValue(int(payload.get("nand1_packet_count", 0)))
        self.nand2_packet_count_spin.setValue(int(payload.get("nand2_packet_count", 0)))
        self.nand1_erase_count_spin.setValue(int(payload.get("nand1_erase_count", 0)))
        self.nand2_erase_count_spin.setValue(int(payload.get("nand2_erase_count", 0)))
        self.nand1_test_count_spin.setValue(int(payload.get("nand1_test_count", 0)))
        self.nand2_test_count_spin.setValue(int(payload.get("nand2_test_count", 0)))
        self.alarm_mask_spin.setValue(int(payload.get("alarm_mask", 0)))

        self._building = False

    def write_payload(self, payload: dict) -> None:
        payload["write_session_id"] = self.write_session_id_checkbox.isChecked()
        payload["write_nand1_packet_count"] = self.write_nand1_packet_count_checkbox.isChecked()
        payload["write_nand2_packet_count"] = self.write_nand2_packet_count_checkbox.isChecked()
        payload["write_nand1_erase_count"] = self.write_nand1_erase_count_checkbox.isChecked()
        payload["write_nand2_erase_count"] = self.write_nand2_erase_count_checkbox.isChecked()
        payload["write_nand1_test_count"] = self.write_nand1_test_count_checkbox.isChecked()
        payload["write_nand2_test_count"] = self.write_nand2_test_count_checkbox.isChecked()

        payload["min_mc_temp"] = self.min_mc_temp_spin.value()
        payload["max_mc_temp"] = self.max_mc_temp_spin.value()
        payload["min_pu_temp"] = self.min_pu_temp_spin.value()
        payload["max_pu_temp"] = self.max_pu_temp_spin.value()
        payload["min_ped_temp"] = self.min_ped_temp_spin.value()
        payload["max_ped_temp"] = self.max_ped_temp_spin.value()
        payload["min_bd_temp"] = self.min_bd_temp_spin.value()
        payload["max_bd_temp"] = self.max_bd_temp_spin.value()

        payload["min_pu_voltage"] = self.min_pu_voltage_spin.value()
        payload["max_pu_voltage"] = self.max_pu_voltage_spin.value()
        payload["min_pu_current"] = self.min_pu_current_spin.value()
        payload["max_pu_current"] = self.max_pu_current_spin.value()
        payload["min_ped_voltage"] = self.min_ped_voltage_spin.value()
        payload["max_ped_voltage"] = self.max_ped_voltage_spin.value()
        payload["min_ped_current"] = self.min_ped_current_spin.value()
        payload["max_ped_current"] = self.max_ped_current_spin.value()

        payload["outer_radiation_lmin"] = self.outer_radiation_lmin_spin.value()
        payload["outer_radiation_lmax"] = self.outer_radiation_lmax_spin.value()
        payload["inner_radiation_bmin"] = self.inner_radiation_bmin_spin.value()
        payload["ac1_max_count"] = self.ac1_max_count_spin.value()

        initial_rtc_text = self.initial_rtc_edit.text().strip()
        payload["initial_rtc"] = int(initial_rtc_text) if initial_rtc_text else 0

        payload["session_id"] = self.session_id_spin.value()
        payload["nand1_packet_count"] = self.nand1_packet_count_spin.value()
        payload["nand2_packet_count"] = self.nand2_packet_count_spin.value()
        payload["nand1_erase_count"] = self.nand1_erase_count_spin.value()
        payload["nand2_erase_count"] = self.nand2_erase_count_spin.value()
        payload["nand1_test_count"] = self.nand1_test_count_spin.value()
        payload["nand2_test_count"] = self.nand2_test_count_spin.value()
        payload["alarm_mask"] = self.alarm_mask_spin.value()

    def _emit_changed(self) -> None:
        if self._building:
            return
        self.changed.emit()
