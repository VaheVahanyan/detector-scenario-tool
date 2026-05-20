from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QStyleOptionViewItem

from detector_scenario_tool.ui.delegates.row_outline_delegate import RowOutlineDelegate


class WrapTextDelegate(RowOutlineDelegate):
    def initStyleOption(self, option: QStyleOptionViewItem, index) -> None:
        super().initStyleOption(option, index)
        option.features |= QStyleOptionViewItem.ViewItemFeature.WrapText
        option.textElideMode = Qt.TextElideMode.ElideNone

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        fm = opt.fontMetrics
        text = opt.text or ""
        if not text:
            return super().sizeHint(option, index)

        width = max(40, opt.rect.width() if opt.rect.width() > 0 else 140)

        rect = fm.boundingRect(
            0,
            0,
            width - 10,
            10_000,
            Qt.TextFlag.TextWordWrap,
            text,
        )
        return QSize(rect.width() + 12, rect.height() + 12)
