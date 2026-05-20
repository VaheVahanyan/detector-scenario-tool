from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout

from detector_scenario_tool.i18n import tr
from detector_scenario_tool.ui.editors.payload_editor_base import PayloadEditorBase


class FixedAaPayloadEditor(PayloadEditorBase):
    def __init__(self, title: str = "fixed_payload") -> None:
        super().__init__()

        self.title_key = title

        layout = QVBoxLayout(self)

        self.title_label = QLabel()
        self.info_label = QLabel()
        self.info_label.setWordWrap(True)

        layout.addWidget(self.title_label)
        layout.addWidget(self.info_label)
        layout.addStretch(1)

        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        self.title_label.setText(tr(f"payload.fixed.title.{self.title_key}"))
        self.info_label.setText(tr("payload.fixed.info"))

    def set_payload(self, payload: dict) -> None:
        pass

    def write_payload(self, payload: dict) -> None:
        payload.clear()
