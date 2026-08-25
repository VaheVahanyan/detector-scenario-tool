"""Timeline rendering: blocks when there is room, rotated labels when there is not.

A 6-byte command occupies ~30 px at 100 % zoom while its label needs ~60 px, so at normal zoom
almost every send is too narrow to caption horizontally. Those now lose the block and get their
title written along the connector, rotated 90°.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QGraphicsSimpleTextItem

from detector_scenario_tool.ui.panels.timeline_panel import (
    _NARROW_ROLE,
    _STATUS_ROLE,
    SELECTION_COLOUR,
)
from message_ids import SET_TIME

SET_TIME = SET_TIME


@pytest.fixture
def window(qtbot):
    from detector_scenario_tool.ui.main_window import MainWindow

    w = MainWindow()
    qtbot.addWidget(w)
    return w


def _add_send(window, msg_id: int = SET_TIME):
    window._add_ku_step()
    row = len(window.document.steps) - 1
    window._select_row(row)
    selector = window.inspector_panel.msg_selector
    for i in range(selector.count()):
        if selector.itemData(i)[1] == msg_id:
            selector.setCurrentIndex(i)
            break
    return row


def _panel(window):
    window.flush_pending_refresh()
    return window.timeline_panel


def _rotated_labels(panel) -> list[QGraphicsSimpleTextItem]:
    return [
        item
        for item in panel.scene.items()
        if isinstance(item, QGraphicsSimpleTextItem) and item.rotation() == -90
    ]


def _horizontal_labels(panel) -> list[QGraphicsSimpleTextItem]:
    return [
        item
        for item in panel.scene.items()
        if isinstance(item, QGraphicsSimpleTextItem) and item.rotation() == 0
    ]


class TestNarrowItems:
    def test_a_short_command_is_drawn_as_a_rotated_label(self, window):
        _add_send(window)
        panel = _panel(window)

        assert panel._row_to_rect_item[0].data(_NARROW_ROLE) is True
        assert panel._row_to_label_item[0].rotation() == -90

    def test_the_rotated_label_carries_the_message_code(self, window):
        _add_send(window)
        panel = _panel(window)

        assert f"0x{SET_TIME:04X}" in panel._row_to_label_item[0].text()

    def test_a_narrow_item_has_no_visible_block(self, window):
        _add_send(window)
        panel = _panel(window)

        rect_item = panel._row_to_rect_item[0]
        assert rect_item.brush().style().name == "NoBrush"

    def test_the_full_name_stays_in_the_tooltip(self, window):
        """The block label is only the code; the name is one hover away."""
        _add_send(window)
        panel = _panel(window)

        tooltip = panel._row_to_label_item[0].toolTip()
        assert f"0x{SET_TIME:04X}" in tooltip
        assert len(tooltip) > len(panel._row_to_label_item[0].text())

    def test_a_narrow_item_is_still_clickable(self, window):
        _add_send(window)
        panel = _panel(window)

        hit = panel._row_to_rect_item[0]
        assert hit.rect().width() > 0
        assert hit.rect().height() > 0
        assert hit.row_index == 0


class TestZoomSwitchesRenderingMode:
    def test_zooming_in_turns_labels_back_into_blocks(self, window):
        _add_send(window)
        panel = _panel(window)
        assert _rotated_labels(panel)

        for _ in range(8):
            panel.zoom_in()

        assert not _rotated_labels(panel), "still rotated after zooming in"
        assert panel._row_to_rect_item[0].data(_NARROW_ROLE) is False
        assert _horizontal_labels(panel)

    def test_zooming_back_out_restores_rotated_labels(self, window):
        _add_send(window)
        panel = _panel(window)
        for _ in range(8):
            panel.zoom_in()
        for _ in range(8):
            panel.zoom_out()

        assert _rotated_labels(panel)


class TestLayout:
    def test_scene_grows_to_fit_rotated_labels(self, window):
        """A fixed 220 px canvas would clip them."""
        _add_send(window)
        panel = _panel(window)
        with_labels = panel.scene.sceneRect().height()

        for _ in range(8):
            panel.zoom_in()
        without_labels = panel.scene.sceneRect().height()

        assert with_labels > without_labels

    def test_labels_stay_inside_the_scene(self, window):
        for _ in range(4):
            _add_send(window)
        panel = _panel(window)

        scene_rect = panel.scene.sceneRect()
        for label in _rotated_labels(panel):
            assert scene_rect.contains(label.sceneBoundingRect()), "label clipped"

    def test_wait_steps_keep_their_block(self, window):
        """A wait is as wide as its duration, so it almost always fits a horizontal caption."""
        window._add_wait_step()
        window.document.steps[0].delay_ms = 5000
        panel = _panel(window)

        assert panel._row_to_rect_item[0].data(_NARROW_ROLE) is False


class TestCollisions:
    def test_overlapping_labels_are_dropped_but_stay_clickable(self, window):
        for _ in range(6):
            _add_send(window)
        panel = _panel(window)

        for _ in range(6):
            panel.zoom_out()

        drawn = len(panel._row_to_label_item)
        assert drawn < 6, "labels should not overprint at low zoom"
        assert len(panel._row_to_rect_item) == 6, "every row keeps a click target"


class TestStatusAndSelection:
    def test_status_colours_the_rotated_label(self, window):
        _add_send(window)
        panel = _panel(window)
        # Selection wins over the status colour, and adding a step selects it.
        panel.set_selected_row(None)
        panel.set_document(window.document, row_statuses={0: "error"})

        assert panel._row_to_rect_item[0].data(_STATUS_ROLE) == "error"
        assert panel._row_to_label_item[0].brush().color().red() > 200

    def test_selecting_a_rotated_item_outlines_it_and_bolds_the_label(self, window):
        _add_send(window)
        panel = _panel(window)
        panel.set_selected_row(0)

        assert panel._row_to_rect_item[0].pen().color() == SELECTION_COLOUR
        assert panel._row_to_label_item[0].font().bold()

    def test_deselecting_restores_the_status_colour(self, window):
        _add_send(window)
        panel = _panel(window)
        panel.set_document(window.document, row_statuses={0: "ok"})
        panel.set_selected_row(0)
        panel.set_selected_row(None)

        label = panel._row_to_label_item[0]
        assert not label.font().bold()
        assert label.brush().color().green() > 200
