from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPen
from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QStyle


class RowOutlineDelegate(QStyledItemDelegate):
    def __init__(
        self,
        parent=None,
        outline_color: QColor | None = None,
        outline_width: int = 3,
        make_text_bold: bool = True,
    ) -> None:
        super().__init__(parent)
        self._outline_color = outline_color or QColor(140, 190, 255)
        self._outline_width = outline_width
        self._make_text_bold = make_text_bold

    def paint(self, painter, option: QStyleOptionViewItem, index) -> None:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        selected = bool(opt.state & QStyle.StateFlag.State_Selected)

        # Не даём Qt закрашивать selection поверх наших status colors.
        if selected:
            opt.state &= ~QStyle.StateFlag.State_HasFocus
            opt.state &= ~QStyle.StateFlag.State_Selected

            if self._make_text_bold:
                font = QFont(opt.font)
                font.setBold(True)
                opt.font = font

        super().paint(painter, opt, index)

        if not selected:
            return

        model = index.model()
        column_count = model.columnCount()
        col = index.column()

        rect = option.rect.adjusted(1, 1, -1, -1)

        painter.save()
        pen = QPen(self._outline_color)
        pen.setWidth(self._outline_width)
        pen.setCosmetic(True)
        painter.setPen(pen)

        # Верх и низ по всей строке
        painter.drawLine(rect.topLeft(), rect.topRight())
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())

        # Левая граница только у первой ячейки
        if col == 0:
            painter.drawLine(rect.topLeft(), rect.bottomLeft())

        # Правая граница только у последней ячейки
        if col == column_count - 1:
            painter.drawLine(rect.topRight(), rect.bottomRight())

        painter.restore()