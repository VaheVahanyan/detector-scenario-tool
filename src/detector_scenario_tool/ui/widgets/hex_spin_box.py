"""A spin box that reads and writes hexadecimal.

Bus addresses are written `1Eh` in the specification and `0x1E` everywhere in this application, so
a decimal spin box would be the one place a user has to convert in their head. Qt's own hex mode
(`setDisplayIntegerBase`) renders lowercase and without padding, which does not match how the rest
of the UI writes an identifier, hence the three overrides.
"""

from __future__ import annotations

from PySide6.QtGui import QValidator
from PySide6.QtWidgets import QSpinBox, QWidget

#: Hex digits shown, padded. An address is two, a CAN identifier three.
DEFAULT_DIGITS = 2


class HexSpinBox(QSpinBox):
    def __init__(self, digits: int = DEFAULT_DIGITS, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.digits = digits
        self.setPrefix("0x")

    def textFromValue(self, value: int) -> str:
        return f"{value:0{self.digits}X}"

    def valueFromText(self, text: str) -> int:
        digits = self._digits(text)
        return int(digits, 16) if digits else 0

    def validate(self, text: str, pos: int):
        digits = self._digits(text)
        if not digits:
            # Mid-edit: the field is empty, which is neither right nor wrong yet.
            return QValidator.State.Intermediate, text, pos

        try:
            value = int(digits, 16)
        except ValueError:
            return QValidator.State.Invalid, text, pos

        if self.minimum() <= value <= self.maximum():
            return QValidator.State.Acceptable, text, pos
        return QValidator.State.Intermediate, text, pos

    def _digits(self, text: str) -> str:
        stripped = text.strip()
        prefix = self.prefix()
        if prefix and stripped.lower().startswith(prefix.lower()):
            stripped = stripped[len(prefix):]
        return stripped.strip()
