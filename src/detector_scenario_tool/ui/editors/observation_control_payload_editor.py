from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QComboBox, QFormLayout, QLabel

from detector_scenario_tool.i18n import tr
from detector_scenario_tool.ui.editors.payload_editor_base import PayloadEditorBase


class ObservationControlPayloadEditor(PayloadEditorBase):
    def __init__(self) -> None:
        super().__init__()

        self.layout_form = QFormLayout(self)

        self.ped_power_checkbox = QCheckBox()
        self.ped_low_power_checkbox = QCheckBox()
        self.ped_event_registration_checkbox = QCheckBox()

        self.event_format_combo = QComboBox()
        self.event_count_combo = QComboBox()
        self.spectrum_mode_combo = QComboBox()
        self.hist_cells_combo = QComboBox()

        self.label_ped_power = QLabel()
        self.label_ped_low_power = QLabel()
        self.label_ped_event_registration = QLabel()
        self.label_event_format = QLabel()
        self.label_event_count = QLabel()
        self.label_spectrum_mode = QLabel()
        self.label_hist_cells = QLabel()

        self.layout_form.addRow(self.label_ped_power, self.ped_power_checkbox)
        self.layout_form.addRow(self.label_ped_low_power, self.ped_low_power_checkbox)
        self.layout_form.addRow(self.label_ped_event_registration, self.ped_event_registration_checkbox)
        self.layout_form.addRow(self.label_event_format, self.event_format_combo)
        self.layout_form.addRow(self.label_event_count, self.event_count_combo)
        self.layout_form.addRow(self.label_spectrum_mode, self.spectrum_mode_combo)
        self.layout_form.addRow(self.label_hist_cells, self.hist_cells_combo)

        self.ped_power_checkbox.stateChanged.connect(self._emit_changed)
        self.ped_low_power_checkbox.stateChanged.connect(self._emit_changed)
        self.ped_event_registration_checkbox.stateChanged.connect(self._emit_changed)
        self.event_format_combo.currentIndexChanged.connect(self._emit_changed)
        self.event_count_combo.currentIndexChanged.connect(self._emit_changed)
        self.spectrum_mode_combo.currentIndexChanged.connect(self._emit_changed)
        self.hist_cells_combo.currentIndexChanged.connect(self._emit_changed)

        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        self.label_ped_power.setText(tr("payload.obs_control.ped_power"))
        self.label_ped_low_power.setText(tr("payload.obs_control.ped_low_power"))
        self.label_ped_event_registration.setText(tr("payload.obs_control.ped_event_registration"))
        self.label_event_format.setText(tr("payload.obs_control.event_format"))
        self.label_event_count.setText(tr("payload.obs_control.event_count"))
        self.label_spectrum_mode.setText(tr("payload.obs_control.spectrum_mode"))
        self.label_hist_cells.setText(tr("payload.obs_control.hist_cells"))

        current_event_format = self.event_format_combo.currentData()
        current_event_count = self.event_count_combo.currentData()
        current_spectrum = self.spectrum_mode_combo.currentData()
        current_hist = self.hist_cells_combo.currentData()

        self.event_format_combo.blockSignals(True)
        self.event_format_combo.clear()
        self.event_format_combo.addItem(tr("payload.option.event_format.0"), 0)
        self.event_format_combo.addItem(tr("payload.option.event_format.1"), 1)
        self.event_format_combo.addItem(tr("payload.option.event_format.2"), 2)
        self.event_format_combo.addItem(tr("payload.option.event_format.3_short"), 3)
        self.event_format_combo.addItem(tr("payload.option.event_format.4"), 4)
        idx = self.event_format_combo.findData(current_event_format if current_event_format is not None else 0)
        self.event_format_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.event_format_combo.blockSignals(False)

        self.event_count_combo.blockSignals(True)
        self.event_count_combo.clear()
        self.event_count_combo.addItem(tr("payload.option.event_count.0"), 0)
        self.event_count_combo.addItem(tr("payload.option.event_count.1"), 1)
        self.event_count_combo.addItem(tr("payload.option.event_count.2"), 2)
        self.event_count_combo.addItem(tr("payload.option.event_count.3"), 3)
        self.event_count_combo.addItem(tr("payload.option.event_count.4"), 4)
        self.event_count_combo.addItem(tr("payload.option.event_count.5"), 5)
        idx = self.event_count_combo.findData(current_event_count if current_event_count is not None else 0)
        self.event_count_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.event_count_combo.blockSignals(False)

        self.spectrum_mode_combo.blockSignals(True)
        self.spectrum_mode_combo.clear()
        self.spectrum_mode_combo.addItem(tr("payload.option.spectrum_mode.0"), 0)
        self.spectrum_mode_combo.addItem(tr("payload.option.spectrum_mode.1"), 1)
        self.spectrum_mode_combo.addItem(tr("payload.option.spectrum_mode.2"), 2)
        idx = self.spectrum_mode_combo.findData(current_spectrum if current_spectrum is not None else 0)
        self.spectrum_mode_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.spectrum_mode_combo.blockSignals(False)

        self.hist_cells_combo.blockSignals(True)
        self.hist_cells_combo.clear()
        self.hist_cells_combo.addItem(tr("payload.option.hist_cells.0"), 0)
        self.hist_cells_combo.addItem(tr("payload.option.hist_cells.1"), 1)
        self.hist_cells_combo.addItem(tr("payload.option.hist_cells.2"), 2)
        self.hist_cells_combo.addItem(tr("payload.option.hist_cells.3"), 3)
        self.hist_cells_combo.addItem(tr("payload.option.hist_cells.4"), 4)
        idx = self.hist_cells_combo.findData(current_hist if current_hist is not None else 0)
        self.hist_cells_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.hist_cells_combo.blockSignals(False)

    def set_payload(self, payload: dict) -> None:
        self._building = True

        self.ped_power_checkbox.setChecked(bool(payload.get("ped_power_enabled", False)))
        self.ped_low_power_checkbox.setChecked(bool(payload.get("ped_low_power", False)))
        self.ped_event_registration_checkbox.setChecked(bool(payload.get("ped_event_registration", False)))

        event_format_mode = int(payload.get("event_format_mode", 0))
        event_format_index = self.event_format_combo.findData(event_format_mode)
        if event_format_index < 0:
            event_format_index = 0
        self.event_format_combo.setCurrentIndex(event_format_index)

        event_count_mode = int(payload.get("event_count_mode", 0))
        event_count_index = self.event_count_combo.findData(event_count_mode)
        if event_count_index < 0:
            event_count_index = 0
        self.event_count_combo.setCurrentIndex(event_count_index)

        spectrum_mode = int(payload.get("spectrum_mode", 0))
        spectrum_index = self.spectrum_mode_combo.findData(spectrum_mode)
        if spectrum_index < 0:
            spectrum_index = 0
        self.spectrum_mode_combo.setCurrentIndex(spectrum_index)

        hist_cells = int(payload.get("histogram_cells", 0))
        hist_cells_index = self.hist_cells_combo.findData(hist_cells)
        if hist_cells_index < 0:
            hist_cells_index = 0
        self.hist_cells_combo.setCurrentIndex(hist_cells_index)

        self._building = False

    def write_payload(self, payload: dict) -> None:
        payload["ped_power_enabled"] = self.ped_power_checkbox.isChecked()
        payload["ped_low_power"] = self.ped_low_power_checkbox.isChecked()
        payload["ped_event_registration"] = self.ped_event_registration_checkbox.isChecked()
        payload["event_format_mode"] = self.event_format_combo.currentData()
        payload["event_count_mode"] = self.event_count_combo.currentData()
        payload["spectrum_mode"] = self.spectrum_mode_combo.currentData()
        payload["histogram_cells"] = self.hist_cells_combo.currentData()

    def _emit_changed(self) -> None:
        if self._building:
            return
        self.changed.emit()