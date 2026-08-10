from __future__ import annotations

from dataclasses import dataclass

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


# Item data slots: the status, lane and rendering mode an item was drawn for, so repainting does
# not have to guess them back out of the pen colour.
_STATUS_ROLE = 0
_LANE_ROLE = 1
_NARROW_ROLE = 2

LEFT_MARGIN = 20
RIGHT_MARGIN = 40
TOP_MARGIN = 10
BOTTOM_MARGIN = 12

BLOCK_H = 30
WAIT_H = 22
#: Visible length of the connector between a block and the time axis.
CONNECTOR_LEN = 46
#: Smallest block a message may be drawn as before it becomes a rotated label.
MIN_BLOCK_W = 18
LABEL_PADDING = 8
#: Clearance from the axis for a rotated label. Below the axis it has to clear the tick numbers.
RX_LABEL_GAP = 8
TX_LABEL_GAP = 26
#: Gap between the connector line and the rotated label running alongside it.
LABEL_LINE_OFFSET = 3
#: How far the click target extends to the left of the connector.
HIT_LEFT_MARGIN = 5

SELECTION_COLOUR = QColor(80, 160, 255)

#: Repeat ticks closer together than this would be a grey smear, so they are dropped.
MIN_REPEAT_MARK_SPACING = 14
REPEAT_MARK_LEN = 14


@dataclass
class _Placement:
    """How one timeline item will be drawn, decided before anything is painted."""

    item: TimelineItem
    x: float
    width: float
    text_width: float
    narrow: bool
    show_label: bool


@dataclass
class _Layout:
    center_y: float
    rx_y: float
    tx_y: float
    content_w: int
    content_h: int
    placements: list[_Placement]


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

        self.zoom_reset_button = QPushButton()
        self.zoom_reset_button.setFixedWidth(64)

        self.zoom_in_button = QPushButton("+")
        self.zoom_in_button.setFixedWidth(36)

        self.zoom_hint_button = QPushButton()
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
        self._row_to_label_item: dict[int, QGraphicsSimpleTextItem] = {}
        self._selected_row: int | None = None

        self._document: ScenarioDocument | None = None
        self._document_signature_cache: tuple | None = None
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
        row_statuses = row_statuses or {}

        # Rebuilding the whole QGraphicsScene on every refresh makes the timeline flicker while
        # the user types. When only the status colours changed, repaint the existing items.
        signature = self._document_signature(document)
        if signature == self._document_signature_cache and self._row_to_rect_item:
            self._row_statuses = row_statuses
            self._apply_statuses_in_place()
            return

        self._document_signature_cache = signature
        self._row_statuses = row_statuses
        self._rerender()

    @staticmethod
    def _document_signature(document: ScenarioDocument | None) -> tuple:
        """Everything build_timeline() reads, except the statuses.

        Deliberately excludes payload, title and enabled: the timeline does not render them, so a
        change there must not cost a scene rebuild.
        """
        if document is None:
            return ()

        def message_key(ref) -> tuple | None:
            return None if ref is None else (ref.category, ref.msg_id, ref.name)

        return tuple(
            (
                step.id,
                step.kind,
                getattr(step, "delay_ms", None),
                getattr(step, "timeout_ms", None),
                message_key(getattr(step, "message", None)),
                message_key(getattr(step, "expected", None)),
                getattr(step, "bind_to_previous_ku", False),
            )
            for step in document.steps
        )

    def _apply_statuses_in_place(self) -> None:
        for row_index, rect_item in self._row_to_rect_item.items():
            status = self._row_statuses.get(row_index, "neutral")
            rect_item.setData(_STATUS_ROLE, status)

            if rect_item.data(_NARROW_ROLE):
                # A rotated item has no block to fill; its colour lives in the label.
                label = self._row_to_label_item.get(row_index)
                if label is not None:
                    label.setBrush(QBrush(self._label_colour_for_status(status)))
                continue

            lane = rect_item.data(_LANE_ROLE) or "tx"
            rect_item.setBrush(self._brush_for_status(status, lane=lane))
            rect_item.setPen(self._pen_for_status(status))

        self._apply_selection_highlight()

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
        self._update_zoom_label()
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
        self._update_zoom_label()
        self.gutter.update()

    def _update_zoom_label(self) -> None:
        if abs(self._zoom_x - 1.0) < 1e-9:
            self.zoom_reset_button.setText(tr("timeline.zoom_reset"))
        else:
            self.zoom_reset_button.setText(f"{int(round(self._zoom_x * 100))}%")

    def _rerender(self) -> None:
        if self._document is None:
            self.scene.clear()
            self._row_to_rect_item.clear()
            self._row_to_label_item.clear()
            return

        timeline = build_timeline(self._document, row_statuses=self._row_statuses)
        self._render(timeline.items, timeline.total_duration_ms)

    def _px_per_ms(self) -> float:
        return self._base_px_per_ms * self._zoom_x

    def _render(self, items: list[TimelineItem], total_duration_ms: int) -> None:
        self.scene.clear()
        self._row_to_rect_item.clear()
        self._row_to_label_item.clear()

        px_per_ms = self._px_per_ms()
        layout = self._plan_layout(items, px_per_ms, total_duration_ms)

        self.scene.setSceneRect(0, 0, layout.content_w, layout.content_h)
        self.gutter.set_geometry_params(
            rx_label_y=layout.rx_y + BLOCK_H // 2,
            center_y=layout.center_y,
            tx_label_y=layout.tx_y + BLOCK_H // 2,
            content_h=layout.content_h,
        )

        axis_pen = QPen(QColor(180, 180, 180))
        axis_pen.setWidth(2)
        self.scene.addLine(
            LEFT_MARGIN, layout.center_y, layout.content_w - RIGHT_MARGIN, layout.center_y, axis_pen
        )
        self.scene.addLine(
            LEFT_MARGIN, layout.center_y - 8, LEFT_MARGIN, layout.center_y + 8,
            QPen(QColor(170, 170, 170)),
        )

        for placement in layout.placements:
            self._draw_item(placement, layout)

        self._draw_time_scale(
            left_margin=LEFT_MARGIN,
            center_y=layout.center_y,
            total_duration_ms=total_duration_ms,
            content_w=layout.content_w,
            right_margin=RIGHT_MARGIN,
            px_per_ms=px_per_ms,
        )

        self._apply_selection_highlight()
        self.view.verticalScrollBar().setValue(0)

    # -- layout ------------------------------------------------------------------------

    def _plan_layout(
            self,
            items: list[TimelineItem],
            px_per_ms: float,
            total_duration_ms: int,
    ) -> _Layout:
        """Decide per item whether it gets a block or a rotated label, then size the scene.

        Rotated labels extend away from the axis, so how much vertical room each lane needs is
        only known once every label has been measured.
        """
        metrics = QFontMetrics(self._label_font())
        placements: list[_Placement] = []

        for item in items:
            x = LEFT_MARGIN + item.start_ms * px_per_ms
            width = max(MIN_BLOCK_W, item.duration_ms * px_per_ms)
            text_w = metrics.horizontalAdvance(item.title)
            narrow = item.lane != "wait" and width < text_w + 2 * LABEL_PADDING

            placements.append(
                _Placement(
                    item=item,
                    x=x,
                    width=width,
                    text_width=text_w,
                    narrow=narrow,
                    show_label=True,
                )
            )

        self._resolve_label_collisions(placements, metrics.height())

        rotated = {"rx": 0.0, "tx": 0.0}
        for placement in placements:
            if placement.narrow and placement.show_label:
                rotated[placement.item.lane] = max(
                    rotated[placement.item.lane], placement.text_width
                )

        above = max(BLOCK_H + CONNECTOR_LEN, rotated["rx"] + RX_LABEL_GAP)
        below = max(BLOCK_H + CONNECTOR_LEN, rotated["tx"] + TX_LABEL_GAP)

        center_y = TOP_MARGIN + above
        content_h = int(center_y + below + BOTTOM_MARGIN)
        content_w = max(
            1200,
            int(LEFT_MARGIN + RIGHT_MARGIN + total_duration_ms * px_per_ms + 180),
        )

        return _Layout(
            center_y=center_y,
            rx_y=center_y - CONNECTOR_LEN - BLOCK_H,
            tx_y=center_y + CONNECTOR_LEN,
            content_w=content_w,
            content_h=content_h,
            placements=placements,
        )

    @staticmethod
    def _resolve_label_collisions(placements: list[_Placement], text_height: int) -> None:
        """Rotated labels are vertical strips; two at the same x would overprint.

        Overlapping ones lose their text but keep their connector and click target, and the
        tooltip still names them — zooming in separates them.
        """
        thickness = text_height + 2
        last_x: dict[str, float] = {}

        for placement in placements:
            if not placement.narrow:
                continue
            lane = placement.item.lane
            centre = placement.x + placement.width / 2
            previous = last_x.get(lane)
            if previous is not None and abs(centre - previous) < thickness:
                placement.show_label = False
                continue
            last_x[lane] = centre

    def _label_font(self):
        font = self.view.font()
        font.setPointSize(max(9, font.pointSize()))
        return font

    # -- drawing -----------------------------------------------------------------------

    def _draw_item(self, placement: _Placement, layout: _Layout) -> None:
        item = placement.item

        if item.lane == "wait":
            self._draw_wait(placement, layout)
            return

        upward = item.lane == "tx"
        if placement.narrow:
            self._draw_narrow(placement, layout, upward=upward)
        else:
            self._draw_block(placement, layout, upward=upward)

    def _draw_block(self, placement: _Placement, layout: _Layout, upward: bool) -> None:
        item = placement.item
        y = layout.tx_y if upward else layout.rx_y
        rect = QRectF(placement.x, y, placement.width, BLOCK_H)

        rect_item = self._add_hit_rect(rect, item)
        rect_item.setPen(self._pen_for_status(item.status))
        rect_item.setBrush(self._brush_for_status(item.status, lane=item.lane))

        self._add_centred_text(rect, item.title)
        arrow_from = y if upward else y + BLOCK_H
        self._draw_arrow_to_axis(
            placement.x + placement.width / 2, arrow_from, layout.center_y, upward=upward
        )
        self._draw_repeat_marks(placement, layout, upward=upward)

    def _draw_narrow(self, placement: _Placement, layout: _Layout, upward: bool) -> None:
        """No block: the connector becomes the mark and the title runs along it, rotated 90°."""
        item = placement.item
        centre_x = placement.x + placement.width / 2

        gap = TX_LABEL_GAP if upward else RX_LABEL_GAP
        if upward:
            label_near = layout.center_y + gap
            label_far = label_near + placement.text_width
        else:
            label_near = layout.center_y - gap
            label_far = label_near - placement.text_width

        # The connector runs the whole length of the label, so the label reads as a caption on
        # the arrow rather than as a detached word.
        self._draw_arrow_to_axis(centre_x, label_far, layout.center_y, upward=upward)

        label_width = 0.0
        if placement.show_label:
            label_item = QGraphicsSimpleTextItem(item.title)
            label_item.setFont(self._label_font())
            label_item.setBrush(QBrush(self._label_colour_for_status(item.status)))
            label_item.setRotation(-90)
            # Rotating -90° about the top-left corner makes the item grow upward from its
            # position, so anchor at the far end when the label runs downward. Offsetting it
            # sideways keeps the connector line from striking through the glyphs.
            label_width = label_item.boundingRect().height()
            anchor_y = label_far if upward else label_near
            label_item.setPos(centre_x + LABEL_LINE_OFFSET, anchor_y)
            label_item.setToolTip(item.tooltip)
            self.scene.addItem(label_item)
            self._row_to_label_item[item.row_index] = label_item

        self._draw_repeat_marks(placement, layout, upward=upward)

        top = min(label_near, label_far)
        bottom = max(label_near, label_far)
        hit = QRectF(
            centre_x - HIT_LEFT_MARGIN,
            top,
            HIT_LEFT_MARGIN + LABEL_LINE_OFFSET + max(label_width, BLOCK_H / 3),
            max(bottom - top, BLOCK_H),
        )
        rect_item = self._add_hit_rect(hit, item, invisible=True)
        rect_item.setData(_NARROW_ROLE, True)

    def _draw_repeat_marks(self, placement: _Placement, layout: _Layout, upward: bool) -> None:
        """Ghost ticks at each repeat, so a cyclic send reads as a cadence rather than one event.

        The timeline models the scenario's own duration, which a repeat outrun by definition, so
        the marks simply continue to the end of the scene.
        """
        period_ms = placement.item.repeat_period_ms
        if not period_ms:
            return

        px_per_ms = self._px_per_ms()
        step_px = period_ms * px_per_ms
        if step_px < MIN_REPEAT_MARK_SPACING:
            return

        pen = QPen(QColor(120, 120, 120))
        pen.setStyle(Qt.PenStyle.DotLine)

        y_from = layout.center_y
        y_to = (layout.center_y + REPEAT_MARK_LEN) if upward else (layout.center_y - REPEAT_MARK_LEN)

        x = placement.x + placement.width / 2 + step_px
        limit = self.scene.sceneRect().width() - RIGHT_MARGIN
        while x < limit:
            self.scene.addLine(x, y_from, x, y_to, pen)
            x += step_px

    def _draw_wait(self, placement: _Placement, layout: _Layout) -> None:
        item = placement.item
        rect = QRectF(placement.x, layout.center_y - WAIT_H / 2, placement.width, WAIT_H)

        rect_item = self._add_hit_rect(rect, item)
        rect_item.setPen(self._pen_for_status(item.status))
        rect_item.setBrush(self._brush_for_status(item.status, lane="wait"))

        if placement.width >= placement.text_width + 2 * LABEL_PADDING:
            self._add_centred_text(rect, item.subtitle or item.title)

    def _add_hit_rect(
            self,
            rect: QRectF,
            item: TimelineItem,
            invisible: bool = False,
    ) -> ClickableTimelineRectItem:
        rect_item = ClickableTimelineRectItem(rect, item.row_index, self.row_clicked.emit)
        rect_item.setToolTip(item.tooltip)
        rect_item.setData(_STATUS_ROLE, item.status)
        rect_item.setData(_LANE_ROLE, item.lane)
        rect_item.setData(_NARROW_ROLE, invisible)
        if invisible:
            rect_item.setPen(QPen(Qt.PenStyle.NoPen))
            rect_item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self.scene.addItem(rect_item)
        self._row_to_rect_item[item.row_index] = rect_item
        return rect_item

    def _add_centred_text(self, rect: QRectF, text: str) -> None:
        if not text:
            return
        font = self._label_font()
        metrics = QFontMetrics(font)
        text_w = metrics.horizontalAdvance(text)
        if text_w + 2 * LABEL_PADDING > rect.width():
            return

        label = QGraphicsSimpleTextItem(text)
        label.setFont(font)
        label.setBrush(QBrush(QColor(245, 245, 245)))
        label.setPos(
            rect.x() + (rect.width() - text_w) / 2,
            rect.y() + (rect.height() - metrics.height()) / 2,
        )
        self.scene.addItem(label)

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
            selected = row_index == self._selected_row
            narrow = bool(rect_item.data(_NARROW_ROLE))
            status = rect_item.data(_STATUS_ROLE) or "neutral"

            if narrow:
                # Nothing is painted for a rotated item, so selection shows the hit area as an
                # outline and bolds the label.
                if selected:
                    pen = QPen(SELECTION_COLOUR)
                    pen.setWidth(2)
                else:
                    pen = QPen(Qt.PenStyle.NoPen)
                rect_item.setPen(pen)

                label = self._row_to_label_item.get(row_index)
                if label is not None:
                    font = label.font()
                    font.setBold(selected)
                    label.setFont(font)
                    label.setBrush(
                        QBrush(SELECTION_COLOUR if selected else self._label_colour_for_status(status))
                    )
                continue

            if selected:
                pen = QPen(SELECTION_COLOUR)
                pen.setWidth(3)
            else:
                # Re-derive from the recorded status instead of guessing it back out of the
                # current pen colour, which broke as soon as an item was repainted.
                pen = self._pen_for_status(status)
            rect_item.setPen(pen)

    def _label_colour_for_status(self, status: str) -> QColor:
        """Rotated labels carry the status themselves, since they have no fill to colour."""
        if status == "ok":
            return QColor(140, 225, 140)
        if status == "error":
            return QColor(245, 140, 140)
        if status == "warning":
            return QColor(240, 215, 120)
        if status == "current":
            return QColor(140, 195, 255)
        if status == "pending":
            return QColor(165, 165, 165)
        return QColor(230, 230, 230)
