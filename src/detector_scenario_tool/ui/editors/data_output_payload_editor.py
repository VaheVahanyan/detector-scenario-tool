from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QComboBox, QFormLayout, QLabel, QSpinBox

from detector_scenario_tool.i18n import tr
from detector_scenario_tool.ui.editors.payload_editor_base import PayloadEditorBase


class DataOutputPayloadEditor(PayloadEditorBase):
    def __init__(self) -> None:
        super().__init__()

        self.layout_form = QFormLayout(self)

        self.bank_combo = QComboBox()
        self.keep_power_checkbox = QCheckBox()
        self.output_interface_combo = QComboBox()
        self.output_type_combo = QComboBox()

        self.requested_packet_count_spin = QSpinBox()
        self.requested_packet_count_spin.setRange(0, 16_777_215)

        self.label_bank = QLabel()
        self.label_keep_power = QLabel()
        self.label_output_interface = QLabel()
        self.label_output_type = QLabel()
        self.label_requested_packet_count = QLabel()

        self.layout_form.addRow(self.label_bank, self.bank_combo)
        self.layout_form.addRow(self.label_keep_power, self.keep_power_checkbox)
        self.layout_form.addRow(self.label_output_interface, self.output_interface_combo)
        self.layout_form.addRow(self.label_output_type, self.output_type_combo)
        self.layout_form.addRow(self.label_requested_packet_count, self.requested_packet_count_spin)

        self.bank_combo.currentIndexChanged.connect(self._emit_changed)
        self.keep_power_checkbox.stateChanged.connect(self._emit_changed)
        self.output_interface_combo.currentIndexChanged.connect(self._emit_changed)
        self.output_type_combo.currentIndexChanged.connect(self._emit_changed)
        self.requested_packet_count_spin.valueChanged.connect(self._emit_changed)

        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        self.label_bank.setText(tr("payload.data_output.bank"))
        self.label_keep_power.setText(tr("payload.data_output.keep_power"))
        self.label_output_interface.setText(tr("payload.data_output.output_interface"))
        self.label_output_type.setText(tr("payload.data_output.output_type"))
        self.label_requested_packet_count.setText(tr("payload.data_output.requested_packet_count"))

        current_bank = self.bank_combo.currentData()
        current_interface = self.output_interface_combo.currentData()
        current_type = self.output_type_combo.currentData()

        self.bank_combo.blockSignals(True)
        self.bank_combo.clear()
        self.bank_combo.addItem(tr("payload.option.bank.nand1"), "nand1")
        self.bank_combo.addItem(tr("payload.option.bank.nand2"), "nand2")
        idx = self.bank_combo.findData(current_bank if current_bank is not None else "nand1")
        self.bank_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.bank_combo.blockSignals(False)

        self.output_interface_combo.blockSignals(True)
        self.output_interface_combo.clear()
        self.output_interface_combo.addItem(tr("payload.option.output_interface.usb"), "usb")
        self.output_interface_combo.addItem(tr("payload.option.output_interface.can"), "can")
        idx = self.output_interface_combo.findData(current_interface if current_interface is not None else "usb")
        self.output_interface_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.output_interface_combo.blockSignals(False)

        self.output_type_combo.blockSignals(True)
        self.output_type_combo.clear()
        self.output_type_combo.addItem(tr("payload.option.output_type.requested_count"), "requested_count")
        self.output_type_combo.addItem(tr("payload.option.output_type.accumulated"), "accumulated")
        idx = self.output_type_combo.findData(current_type if current_type is not None else "requested_count")
        self.output_type_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.output_type_combo.blockSignals(False)

    def set_payload(self, payload: dict) -> None:
        self._building = True

        bank = payload.get("selected_nand_bank", "nand1")
        bank_index = self.bank_combo.findData(bank)
        if bank_index < 0:
            bank_index = 0
        self.bank_combo.setCurrentIndex(bank_index)

        self.keep_power_checkbox.setChecked(bool(payload.get("keep_power_after_output", False)))

        output_interface = payload.get("output_interface", "usb")
        interface_index = self.output_interface_combo.findData(output_interface)
        if interface_index < 0:
            interface_index = 0
        self.output_interface_combo.setCurrentIndex(interface_index)

        output_type = payload.get("output_type", "requested_count")
        output_type_index = self.output_type_combo.findData(output_type)
        if output_type_index < 0:
            output_type_index = 0
        self.output_type_combo.setCurrentIndex(output_type_index)

        self.requested_packet_count_spin.setValue(int(payload.get("requested_packet_count", 0)))

        self._building = False

    def write_payload(self, payload: dict) -> None:
        payload["selected_nand_bank"] = self.bank_combo.currentData()
        payload["keep_power_after_output"] = self.keep_power_checkbox.isChecked()
        payload["output_interface"] = self.output_interface_combo.currentData()
        payload["output_type"] = self.output_type_combo.currentData()
        payload["requested_packet_count"] = self.requested_packet_count_spin.value()

    def _emit_changed(self) -> None:
        if self._building:
            return
        self.changed.emit()
