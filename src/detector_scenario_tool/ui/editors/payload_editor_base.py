from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget


class PayloadEditorBase(QWidget):
    changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._building = False

    def set_payload(self, payload: dict) -> None:
        raise NotImplementedError

    def write_payload(self, payload: dict) -> None:
        raise NotImplementedError

    def retranslate_ui(self) -> None:
        pass