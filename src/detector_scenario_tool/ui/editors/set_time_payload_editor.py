from __future__ import annotations

from PySide6.QtWidgets import QFormLayout, QLabel, QSpinBox

from detector_scenario_tool.i18n import tr
from detector_scenario_tool.ui.editors.payload_editor_base import PayloadEditorBase


class SetTimePayloadEditor(PayloadEditorBase):
    def __init__(self) -> None:
        super().__init__()

        self.layout_form = QFormLayout(self)

        self.board_time_ms_spin = QSpinBox()
        self.board_time_ms_spin.setRange(0, 65535)

        self.board_time_s_spin = QSpinBox()
        self.board_time_s_spin.setRange(0, 2_147_483_647)

        self.label_board_time_ms = QLabel()
        self.label_board_time_s = QLabel()

        self.layout_form.addRow(self.label_board_time_ms, self.board_time_ms_spin)
        self.layout_form.addRow(self.label_board_time_s, self.board_time_s_spin)

        self.board_time_ms_spin.valueChanged.connect(self._emit_changed)
        self.board_time_s_spin.valueChanged.connect(self._emit_changed)

        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        self.label_board_time_ms.setText(tr("payload.set_time.board_time_ms"))
        self.label_board_time_s.setText(tr("payload.set_time.board_time_s"))

    def set_payload(self, payload: dict) -> None:
        self._building = True
        self.board_time_ms_spin.setValue(int(payload.get("board_time_ms", 0)))
        self.board_time_s_spin.setValue(int(payload.get("board_time_s", 0)))
        self._building = False

    def write_payload(self, payload: dict) -> None:
        payload["board_time_ms"] = self.board_time_ms_spin.value()
        payload["board_time_s"] = self.board_time_s_spin.value()

    def _emit_changed(self) -> None:
        if self._building:
            return
        self.changed.emit()