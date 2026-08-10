"""The refresh path must be cheap and must not disturb the user's context.

Phase 2 changed three things that are easy to regress:
  * status/annotation updates repaint instead of resetting the model (which cleared selections);
  * the log panel applies its three overlays in one pass instead of three;
  * the timeline only rebuilds its scene when the scenario geometry actually changed.
"""

from __future__ import annotations

import pytest

from detector_scenario_tool.domain.logs import LogRecord


@pytest.fixture
def window(qtbot):
    from detector_scenario_tool.ui.main_window import MainWindow

    w = MainWindow()
    qtbot.addWidget(w)
    return w


def _records() -> list[LogRecord]:
    return [
        LogRecord(
            timestamp_ms=i * 10,
            direction="tx" if i % 2 == 0 else "rx",
            category="KU" if i % 2 == 0 else "TS",
            msg_id=0x0001 if i % 2 == 0 else 0x0201,
            payload=b"\xaa" * 6,
            source="l476" if i % 2 == 0 else "l496",
        )
        for i in range(6)
    ]


class TestScenarioTableModel:
    def test_status_update_does_not_reset_the_model(self, window):
        window._add_ku_step()

        resets = []
        window.table_model.modelAboutToBeReset.connect(lambda: resets.append(1))

        window.table_model.set_row_statuses({0: "error"})

        assert resets == []

    def test_status_update_emits_a_repaint(self, window):
        window._add_ku_step()

        changed = []
        window.table_model.dataChanged.connect(
            lambda tl, br, roles: changed.append((tl.row(), br.row()))
        )

        window.table_model.set_row_statuses({0: "error"})

        assert changed == [(0, 0)]

    def test_identical_statuses_are_a_no_op(self, window):
        window._add_ku_step()
        window.table_model.set_row_statuses({0: "error"})

        changed = []
        window.table_model.dataChanged.connect(lambda *a: changed.append(1))
        window.table_model.set_row_statuses({0: "error"})

        assert changed == []


class TestLogPanel:
    def test_annotations_are_applied_in_one_pass(self, window):
        window.log_panel.set_records(_records())

        resets = []
        window.log_panel.model.modelAboutToBeReset.connect(lambda: resets.append(1))

        window.log_panel.update_annotations(
            matched_rows={0, 1}, problem_rows={1}, row_tooltips={1: "mismatch"}
        )

        assert resets == [], "annotations must not re-filter and reset the table"

    def test_annotations_reach_the_model_in_filtered_coordinates(self, window):
        window.log_panel.set_records(_records())
        window.log_panel.dir_filter.setCurrentIndex(
            window.log_panel.dir_filter.findData("rx")
        )

        # Original rows 1, 3, 5 are the rx records, so they become filtered rows 0, 1, 2.
        window.log_panel.update_annotations(
            matched_rows={1, 3, 5}, problem_rows={3}, row_tooltips={5: "late"}
        )

        assert window.log_panel.model._matched_rows == {0, 1, 2}
        assert window.log_panel.model._problem_rows == {1}
        assert window.log_panel.model._row_tooltips == {2: "late"}

    def test_problems_only_filter_still_re_filters(self, window):
        """That filter's visible set depends on the annotations, so it must re-run."""
        window.log_panel.set_records(_records())
        window.log_panel.problems_only_checkbox.setChecked(True)

        window.log_panel.update_annotations(
            matched_rows=set(range(6)), problem_rows={2}, row_tooltips={}
        )

        assert window.log_panel.model.rowCount() == 1
        assert window.log_panel.original_row_for_filtered(0) == 2


class TestTimelinePanel:
    def test_status_change_alone_does_not_rebuild_the_scene(self, window):
        window._add_ku_step()
        window._add_wait_step()
        window.flush_pending_refresh()

        panel = window.timeline_panel
        items_before = set(panel._row_to_rect_item.values())

        panel.set_document(window.document, row_statuses={0: "error", 1: "ok"})

        assert set(panel._row_to_rect_item.values()) == items_before, "scene was rebuilt"
        assert panel._row_to_rect_item[0].data(0) == "error"

    def test_geometry_change_does_rebuild_the_scene(self, window):
        window._add_wait_step()
        window.flush_pending_refresh()

        panel = window.timeline_panel
        items_before = set(panel._row_to_rect_item.values())

        window.document.steps[0].delay_ms = 9999
        panel.set_document(window.document, row_statuses={})

        assert set(panel._row_to_rect_item.values()) != items_before

    def test_payload_edits_do_not_rebuild_the_scene(self, window):
        """The timeline does not render payloads, so editing one must not cost a rebuild."""
        window._add_ku_step()
        window.flush_pending_refresh()

        panel = window.timeline_panel
        items_before = set(panel._row_to_rect_item.values())

        window.document.steps[0].payload["board_time_ms"] = 123
        panel.set_document(window.document, row_statuses={})

        assert set(panel._row_to_rect_item.values()) == items_before

    def test_selection_highlight_survives_a_repaint(self, window):
        window._add_ku_step()
        window._add_wait_step()
        window.flush_pending_refresh()

        from detector_scenario_tool.ui.panels.timeline_panel import SELECTION_COLOUR

        panel = window.timeline_panel
        panel.set_selected_row(0)
        panel.set_document(window.document, row_statuses={0: "ok", 1: "error"})

        # Blocks and rotated labels are highlighted with different pen widths, so check the
        # colour rather than the width.
        pen = panel._row_to_rect_item[0].pen()
        assert pen.color() == SELECTION_COLOUR, "selection highlight lost"
        assert pen.width() >= 2
        assert panel._row_to_rect_item[1].data(0) == "error"


class TestTimeoutColumn:
    """The column means a deadline; a pause's duration is not one.

    It used to print `delay_ms` for wait steps under a "Timeout" header — and that value was
    already shown in the target column, so it was both duplicated and mislabelled.
    """

    TIMEOUT_COLUMN = 4
    TARGET_COLUMN = 3

    def test_send_step_shows_the_acknowledgement_timeout(self, window):
        window._add_ku_step()
        window.document.steps[0].ack_timeout_ms = 1500
        model = window.table_model

        assert model.data(model.index(0, self.TIMEOUT_COLUMN)) == "1500"

    def test_wait_for_message_step_shows_its_timeout(self, window):
        window._add_wait_ts_step()
        window.document.steps[0].timeout_ms = 2000
        model = window.table_model

        assert model.data(model.index(0, self.TIMEOUT_COLUMN)) == "2000"

    def test_pause_step_has_no_timeout(self, window):
        window._add_wait_step()
        window.document.steps[0].delay_ms = 2500
        model = window.table_model

        assert model.data(model.index(0, self.TIMEOUT_COLUMN)) == ""

    def test_pause_duration_is_still_visible(self, window):
        window._add_wait_step()
        window.document.steps[0].delay_ms = 2500
        model = window.table_model

        assert "2500" in model.data(model.index(0, self.TARGET_COLUMN))

    def test_each_kind_explains_its_deadline_in_a_tooltip(self, window):
        from PySide6.QtCore import Qt

        window._add_ku_step()
        window._add_wait_ts_step()
        window._add_wait_step()
        model = window.table_model

        tooltips = [
            model.data(model.index(row, self.TIMEOUT_COLUMN), Qt.ItemDataRole.ToolTipRole)
            for row in range(3)
        ]
        assert all(tooltips), "the column is ambiguous without one"
        assert len(set(tooltips)) == 3, "each step kind means something different here"
