from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QFormLayout, QLabel

from detector_scenario_tool.i18n import tr
from detector_scenario_tool.ui.editors.payload_editor_base import PayloadEditorBase


class TestResultsRequestPayloadEditor(PayloadEditorBase):
    def __init__(self) -> None:
        super().__init__()

        self.layout_form = QFormLayout(self)

        self.bank_combo = QComboBox()
        self.label_bank = QLabel()

        self.layout_form.addRow(self.label_bank, self.bank_combo)

        self.bank_combo.currentIndexChanged.connect(self._emit_changed)

        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        self.label_bank.setText(tr("payload.test_results.bank"))

        current_bank = self.bank_combo.currentData()

        self.bank_combo.blockSignals(True)
        self.bank_combo.clear()
        self.bank_combo.addItem(tr("payload.option.bank.nand1"), "nand1")
        self.bank_combo.addItem(tr("payload.option.bank.nand2"), "nand2")
        idx = self.bank_combo.findData(current_bank if current_bank is not None else "nand1")
        self.bank_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.bank_combo.blockSignals(False)

    def set_payload(self, payload: dict) -> None:
        self._building = True

        bank = payload.get("selected_nand_bank", "nand1")
        bank_index = self.bank_combo.findData(bank)
        if bank_index < 0:
            bank_index = 0
        self.bank_combo.setCurrentIndex(bank_index)

        self._building = False

    def write_payload(self, payload: dict) -> None:
        payload["selected_nand_bank"] = self.bank_combo.currentData()

    def _emit_changed(self) -> None:
        if self._building:
            return
        self.changed.emit()
