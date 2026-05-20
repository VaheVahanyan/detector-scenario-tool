from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, QPointF, Signal
from PySide6.QtGui import QBrush, QPen, QColor, QFontMetrics, QPolygonF, QPainter
from PySide6.QtWidgets import (
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from detector_scenario_tool.domain.scenario import ScenarioDocument
from detector_scenario_tool.domain.timeline import TimelineItem, build_timeline
from detector_scenario_tool.i18n import tr


class ClickableTimelineRectItem(QGraphicsRectItem):
    def __init__(self, rect: QRectF, row_index: int, on_click) -> None:
        super().__init__(rect)
        self.row_index = row_index
        self._on_click = on_click
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)

    def mousePressEvent(self, event) -> None:
        if self._on_click is not None:
            self._on_click(self.row_index)
        super().mousePressEvent(event)


class TimelineGraphicsView(QGraphicsView):
    def __init__(self) -> None:
        super().__init__()
        self.zoom_wheel_callback = None

    def wheelEvent(self, event) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if self.zoom_wheel_callback is not None:
                delta = event.angleDelta().y()
                self.zoom_wheel_callback(delta)
                event.accept()
                return

        super().wheelEvent(event)


class TimelineGutter(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setFixedWidth(150)
        self.setMinimumHeight(240)

        self.rx_label_y = 36
        self.center_y = 112
        self.tx_label_y = 185

    def set_geometry_params(self, rx_label_y: int, center_y: int, tx_label_y: int, content_h: int) -> None:
        self.rx_label_y = rx_label_y
        self.center_y = center_y
        self.tx_label_y = tx_label_y
        self.setMinimumHeight(content_h)
        self.setMaximumHeight(content_h)
        self.updateGeometry()
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(18, 18, 18))
        painter.setPen(QColor(220, 220, 220))

        painter.drawText(12, self.rx_label_y, tr("timeline.detector_to_board"))
        painter.drawText(12, self.center_y + 4, tr("timeline.time_ms"))
        painter.drawText(12, self.tx_label_y, tr("timeline.board_to_detector"))


class TimelinePanel(QWidget):
    row_clicked = Signal(int)

    def __init__(self) -> None:
        super().__init__()

        self.gutter = TimelineGutter()

        self.view = TimelineGraphicsView()
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setBackgroundBrush(QBrush(QColor(18, 18, 18)))
        self.view.setStyleSheet("""
                    QPushButton {
                        color: #aaaaaa; /* Цвет текста в обычном состоянии */
                        background-color: #333333;
                        border: 1px solid #555555;
                        padding: 4px;
                    }
                    QPushButton:hover {
                        color: white; /* Тот самый белый текст при наведении */
                        background-color: #444444;
                        border: 1px solid #888888;
                    }
                    QPushButton:pressed {
                        background-color: #222222;
                    }
                    QPushButton:disabled {
                        color: #555555;
                    }
                """)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.view.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        self.view.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.view.setResizeAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.view.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        self.scene = QGraphicsScene(self)
        self.scene.setBackgroundBrush(QBrush(QColor(18, 18, 18)))
        self.view.setScene(self.scene)

        self.zoom_out_button = QPushButton("−")
        self.zoom_out_button.setFixedWidth(36)

        self.zoom_reset_button = QPushButton("100%")
        self.zoom_reset_button.setFixedWidth(64)

        self.zoom_in_button = QPushButton("+")
        self.zoom_in_button.setFixedWidth(36)

        self.zoom_hint_button = QPushButton("Ctrl+Wheel")
        self.zoom_hint_button.setEnabled(False)

        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(8, 4, 8, 2)
        toolbar.setSpacing(6)
        toolbar.addWidget(self.zoom_out_button)
        toolbar.addWidget(self.zoom_reset_button)
        toolbar.addWidget(self.zoom_in_button)
        toolbar.addWidget(self.zoom_hint_button)
        toolbar.addStretch(1)

        self._row_to_rect_item: dict[int, QGraphicsRectItem] = {}
        self._selected_row: int | None = None

        self._document: ScenarioDocument | None = None
        self._row_statuses: dict[int, str] = {}
        self._zoom_x: float = 1.0
        self._base_px_per_ms: float = 0.25

        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 0, 0, 0)
        bottom.setSpacing(0)
        bottom.addWidget(self.gutter)
        bottom.addWidget(self.view)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addLayout(toolbar)
        root.addLayout(bottom)

        self.zoom_out_button.clicked.connect(self.zoom_out)
        self.zoom_in_button.clicked.connect(self.zoom_in)
        self.zoom_reset_button.clicked.connect(self.reset_zoom)
        self.view.zoom_wheel_callback = self._on_wheel_zoom

        self.retranslate_ui()

    def set_document(
            self,
            document: ScenarioDocument,
            row_statuses: dict[int, str] | None = None,
    ) -> None:
        self._document = document
        self._row_statuses = row_statuses or {}
        self._rerender()

    def set_selected_row(self, row_index: int | None) -> None:
        self._selected_row = row_index
        self._apply_selection_highlight()

    def zoom_in(self) -> None:
        self._set_zoom(self._zoom_x * 1.25)

    def zoom_out(self) -> None:
        self._set_zoom(self._zoom_x / 1.25)

    def reset_zoom(self) -> None:
        self._set_zoom(1.0)

    def _on_wheel_zoom(self, delta: int) -> None:
        if delta > 0:
            self.zoom_in()
        elif delta < 0:
            self.zoom_out()

    def _set_zoom(self, value: float) -> None:
        value = max(0.4, min(8.0, value))
        if abs(value - self._zoom_x) < 1e-9:
            return

        old_scroll = self.view.horizontalScrollBar().value()
        viewport_w = max(1, self.view.viewport().width())
        old_center_ratio = (old_scroll + viewport_w / 2) / max(1.0, self.scene.sceneRect().width())

        self._zoom_x = value
        self.zoom_reset_button.setText(f"{int(round(self._zoom_x * 100))}%")
        self._rerender()

        new_scene_w = max(1.0, self.scene.sceneRect().width())
        target_center = old_center_ratio * new_scene_w
        new_scroll = int(target_center - viewport_w / 2)

        scrollbar = self.view.horizontalScrollBar()
        new_scroll = max(0, min(new_scroll, scrollbar.maximum()))
        scrollbar.setValue(new_scroll)
        self.view.verticalScrollBar().setValue(0)

    def retranslate_ui(self) -> None:
        self.zoom_hint_button.setText(tr("timeline.zoom_hint"))
        self.gutter.update()

    def _rerender(self) -> None:
        if self._document is None:
            self.scene.clear()
            self._row_to_rect_item.clear()
            return

        timeline = build_timeline(self._document, row_statuses=self._row_statuses)
        self._render(timeline.items, timeline.total_duration_ms)

    def _px_per_ms(self) -> float:
        return self._base_px_per_ms * self._zoom_x

    def _render(self, items: list[TimelineItem], total_duration_ms: int) -> None:
        self.scene.clear()
        self._row_to_rect_item.clear()

        left_margin = 20
        right_margin = 40

        center_y = 112
        rx_y = 26
        tx_y = 150
        rx_label_y = 36
        tx_label_y = 185

        wait_y = center_y - 12
        block_h = 30
        px_per_ms = self._px_per_ms()

        content_w = max(1200, left_margin + right_margin + int(total_duration_ms * px_per_ms) + 180)
        content_h = 220
        self.scene.setSceneRect(0, 0, content_w, content_h)

        self.gutter.set_geometry_params(
            rx_label_y=rx_label_y,
            center_y=center_y,
            tx_label_y=tx_label_y,
            content_h=content_h,
        )

        axis_pen = QPen(QColor(180, 180, 180))
        axis_pen.setWidth(2)

        self.scene.addLine(left_margin, center_y, content_w - right_margin, center_y, axis_pen)
        self.scene.addLine(left_margin, center_y - 8, left_margin, center_y + 8, QPen(QColor(170, 170, 170)))

        for item in items:
            self._draw_item(
                item=item,
                left_margin=left_margin,
                tx_y=tx_y,
                rx_y=rx_y,
                wait_y=wait_y,
                center_y=center_y,
                block_h=block_h,
                px_per_ms=px_per_ms,
            )

        self._draw_time_scale(
            left_margin=left_margin,
            center_y=center_y,
            total_duration_ms=total_duration_ms,
            content_w=content_w,
            right_margin=right_margin,
            px_per_ms=px_per_ms,
        )

        self._apply_selection_highlight()
        self.view.verticalScrollBar().setValue(0)

    def _draw_item(
            self,
            item: TimelineItem,
            left_margin: int,
            tx_y: int,
            rx_y: int,
            wait_y: int,
            center_y: int,
            block_h: int,
            px_per_ms: float,
    ) -> None:
        x = left_margin + item.start_ms * px_per_ms

        if item.lane == "tx":
            y = tx_y
            w = max(18, item.duration_ms * px_per_ms)
            h = block_h
            rect = QRectF(x, y, w, h)
            rect_item = ClickableTimelineRectItem(rect, item.row_index, self.row_clicked.emit)
            rect_item.setPen(self._pen_for_status(item.status))
            rect_item.setBrush(self._brush_for_status(item.status, lane="tx"))
            rect_item.setToolTip(item.tooltip)
            self.scene.addItem(rect_item)
            self._row_to_rect_item[item.row_index] = rect_item
            self._maybe_add_text(rect, item.title, y_offset=7)
            self._draw_arrow_to_axis(x + w / 2, y, center_y, upward=True)
            return

        if item.lane == "rx":
            y = rx_y
            w = max(18, item.duration_ms * px_per_ms)
            h = block_h
            rect = QRectF(x, y, w, h)
            rect_item = ClickableTimelineRectItem(rect, item.row_index, self.row_clicked.emit)
            rect_item.setPen(self._pen_for_status(item.status))
            rect_item.setBrush(self._brush_for_status(item.status, lane="rx"))
            rect_item.setToolTip(item.tooltip)
            self.scene.addItem(rect_item)
            self._row_to_rect_item[item.row_index] = rect_item
            self._maybe_add_text(rect, item.title, y_offset=7)
            self._draw_arrow_to_axis(x + w / 2, y + h, center_y, upward=False)
            return

        if item.lane == "wait":
            w = max(20, item.duration_ms * px_per_ms)
            rect = QRectF(x, wait_y, w, 22)
            rect_item = ClickableTimelineRectItem(rect, item.row_index, self.row_clicked.emit)
            rect_item.setPen(self._pen_for_status(item.status))
            rect_item.setBrush(self._brush_for_status(item.status, lane="wait"))
            rect_item.setToolTip(item.tooltip)
            self.scene.addItem(rect_item)
            self._row_to_rect_item[item.row_index] = rect_item
            self._maybe_add_small_text(rect.x() + 4, rect.y() - 16, item.subtitle)
            return

    def _draw_arrow_to_axis(self, x: float, y_from: float, center_y: int, upward: bool) -> None:
        pen = QPen(QColor(120, 120, 120))
        pen.setWidth(1)

        self.scene.addLine(x, y_from, x, center_y, pen)

        arrow_size = 5
        if upward:
            p1 = QPointF(x, center_y)
            p2 = QPointF(x - arrow_size, center_y + arrow_size)
            p3 = QPointF(x + arrow_size, center_y + arrow_size)
        else:
            p1 = QPointF(x, center_y)
            p2 = QPointF(x - arrow_size, center_y - arrow_size)
            p3 = QPointF(x + arrow_size, center_y - arrow_size)

        self.scene.addPolygon(QPolygonF([p1, p2, p3]), pen, QBrush(QColor(120, 120, 120)))

    def _draw_time_scale(
            self,
            left_margin: int,
            center_y: int,
            total_duration_ms: int,
            content_w: int,
            right_margin: int,
            px_per_ms: float,
    ) -> None:
        tick_step_ms = self._pick_tick_step(total_duration_ms)

        tick = 0
        while tick <= total_duration_ms:
            x = left_margin + tick * px_per_ms
            self.scene.addLine(x, center_y - 8, x, center_y + 8, QPen(QColor(170, 170, 170)))
            self._add_text(x - 10, center_y + 14, str(tick), small=True, color=QColor(220, 220, 220))
            tick += tick_step_ms

        end_x = left_margin + total_duration_ms * px_per_ms
        if end_x < content_w - right_margin:
            self.scene.addLine(end_x, center_y - 8, end_x, center_y + 8, QPen(QColor(170, 170, 170)))

    def _pick_tick_step(self, total_duration_ms: int) -> int:
        px_per_ms = self._px_per_ms()
        target_px = 90

        candidates = [50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000, 50000]
        for step in candidates:
            if step * px_per_ms >= target_px:
                return step
        return candidates[-1]

    def _maybe_add_text(self, rect: QRectF, text: str, y_offset: int = 13) -> None:
        font = self.view.font()
        font.setPointSize(max(9, font.pointSize()))
        metrics = QFontMetrics(font)

        if rect.width() < 42:
            return

        if metrics.horizontalAdvance(text) + 16 > rect.width():
            return

        item = QGraphicsSimpleTextItem(text)
        item.setFont(font)
        item.setBrush(QBrush(QColor(245, 245, 245)))
        item.setPos(rect.x() + (rect.width() - metrics.horizontalAdvance(text)) / 2, rect.y() + y_offset)
        self.scene.addItem(item)

    def _maybe_add_small_text(self, x: float, y: float, text: str) -> None:
        if not text:
            return
        self._add_text(x, y, text, small=True, color=QColor(220, 220, 220))

    def _add_text(self, x: float, y: float, text: str, small: bool = False, color: QColor | None = None) -> None:
        item = QGraphicsSimpleTextItem(text)
        font = item.font()
        if small:
            font.setPointSize(max(8, font.pointSize() - 1))
        else:
            font.setPointSize(max(9, font.pointSize()))
        item.setFont(font)
        if color is not None:
            item.setBrush(QBrush(color))
        item.setPos(x, y)
        self.scene.addItem(item)

    def _brush_for_status(self, status: str, lane: str) -> QBrush:
        if status == "ok":
            return QBrush(QColor(60, 130, 60))
        if status == "error":
            return QBrush(QColor(160, 55, 55))
        if status == "warning":
            return QBrush(QColor(150, 125, 45))
        if status == "current":
            return QBrush(QColor(50, 95, 150))
        if status == "pending":
            return QBrush(QColor(110, 110, 110))
        if lane == "rx":
            return QBrush(QColor(60, 60, 60))
        if lane == "wait":
            return QBrush(QColor(90, 90, 90))
        return QBrush(QColor(80, 80, 80))

    def _pen_for_status(self, status: str) -> QPen:
        if status == "ok":
            pen = QPen(QColor(120, 220, 120))
            pen.setWidth(2)
            return pen
        if status == "error":
            pen = QPen(QColor(240, 120, 120))
            pen.setWidth(2)
            return pen
        if status == "warning":
            pen = QPen(QColor(240, 210, 100))
            pen.setWidth(2)
            return pen
        if status == "current":
            pen = QPen(QColor(120, 180, 255))
            pen.setWidth(2)
            return pen
        if status == "pending":
            pen = QPen(QColor(160, 160, 160))
            pen.setWidth(2)
            return pen
        pen = QPen(QColor(180, 180, 180))
        pen.setWidth(1)
        return pen

    def _apply_selection_highlight(self) -> None:
        for row_index, rect_item in self._row_to_rect_item.items():
            pen = rect_item.pen()
            if row_index == self._selected_row:
                pen.setWidth(3)
                pen.setColor(QColor(80, 160, 255))
            else:
                if pen.color() in (
                        QColor(120, 220, 120),
                        QColor(240, 120, 120),
                        QColor(240, 210, 100),
                        QColor(120, 180, 255),
                        QColor(160, 160, 160),
                ):
                    pen.setWidth(2)
                else:
                    pen.setWidth(1)
                    pen.setColor(QColor(180, 180, 180))
            rect_item.setPen(pen)
