"""Board log lines in the log panel, and their (non-)effect on scenario correlation.

The МК prints its own debug output onto the CAN bus in some configurations. Those lines have to be
visible — that is what the log panel is for — while changing nothing about how the scenario is
matched against the capture. Every assertion here is about the second half.
"""

from __future__ import annotations

import pytest

from detector_scenario_tool.domain.logs import LOG_CATEGORY, LogRecord
from detector_scenario_tool.i18n import tr
from detector_scenario_tool.ui.models.log_table_model import VIEW_DECODED
from message_ids import STATUS_REQ, TM_ACK


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    from detector_scenario_tool.ui.main_window import MainWindow

    w = MainWindow()
    qtbot.addWidget(w)
    return w


def _add_send(window, msg_id: int) -> None:
    window._add_ku_step()
    window._select_row(len(window.document.steps) - 1)
    selector = window.inspector_panel.msg_selector
    for i in range(selector.count()):
        if selector.itemData(i)[1] == msg_id:
            selector.setCurrentIndex(i)
            return
    raise AssertionError(f"0x{msg_id:04X} is not offered by the inspector")


def _board_log(ts: int, text: bytes = b"boot ok\n", msg_id: int = 0x0123) -> LogRecord:
    return LogRecord(
        timestamp_ms=ts, direction="rx", category=LOG_CATEGORY, msg_id=msg_id,
        payload=text, source="board",
    )


def _sent(ts: int) -> LogRecord:
    return LogRecord(
        timestamp_ms=ts, direction="tx", category="KU", msg_id=STATUS_REQ,
        payload=b"", source="board",
    )


def _ack(ts: int) -> LogRecord:
    return LogRecord(
        timestamp_ms=ts, direction="rx", category="TS", msg_id=TM_ACK,
        payload=bytes([0x01, 0x00, 0x00, 0xAA, 0xAA, 0xAA]), source="detector",
    )


def _load(window, records) -> None:
    window.log_records = list(records)
    window._refresh_all_views()


class TestCorrelation:
    def test_a_step_still_matches_across_interleaved_log_lines(self, window):
        """The regression this exists for: chatter between two steps must not derail matching."""
        _add_send(window, STATUS_REQ)
        _load(window, [_board_log(1), _sent(10), _board_log(12), _board_log(14)])

        assert window._step_to_log_row == {0: 1}

    def test_log_lines_are_not_the_mismatch_that_blocks_a_run(self, window):
        _add_send(window, STATUS_REQ)
        _load(window, [_board_log(1), _board_log(2)])

        # Nothing has been sent yet, so the step is merely waiting — not wrong.
        assert window.table_model._row_statuses.get(0) != "error"

    def test_a_genuine_mismatch_is_still_reported(self, window):
        """The guard rail: skipping log lines must not skip real traffic."""
        _add_send(window, STATUS_REQ)
        _load(window, [_board_log(1), _ack(5)])

        assert window.table_model._row_statuses.get(0) == "error"

    def test_log_lines_are_not_counted_as_problems(self, window):
        _add_send(window, STATUS_REQ)
        _load(window, [_sent(10), _board_log(12)])

        problems = window._collect_log_problem_rows(window.log_records, window._log_to_step_row)
        assert problems == set()

    def test_a_log_line_says_what_it_is_instead_of_calling_itself_extra(self, window):
        _add_send(window, STATUS_REQ)
        _load(window, [_sent(10), _board_log(12)])

        assert window._log_execution_details[1] == tr(
            "execution.board_log", log_row=2, msg_id=0x0123, time=12
        )

    def test_they_are_left_out_of_the_execution_summary_counts(self, window):
        _add_send(window, STATUS_REQ)
        _load(window, [_sent(10), _board_log(12), _board_log(14)])

        # One protocol record, matched. The board said two more things; neither is an extra log.
        assert window.log_panel.summary_label.text() == tr(
            "summary.execution",
            current=tr("summary.current.none"),
            mismatch=tr("summary.mismatch.none"),
            matched_steps=1,
            total_steps=1,
            unmatched_steps=0,
            matched_logs=1,
            total_logs=1,
            unmatched_logs=0,
        )


class TestPresentation:
    def test_the_row_shows_the_text_rather_than_the_bytes(self, window):
        window.log_panel.set_records([_board_log(1, b"NAND1 erase done\n")])
        model = window.log_panel.model
        model.set_view_mode(VIEW_DECODED)

        assert model._summary(model.record_at(0)) == "NAND1 erase done"

    def test_the_category_filter_offers_them(self, window):
        combo = window.log_panel.category_filter
        assert LOG_CATEGORY in [combo.itemData(i) for i in range(combo.count())]

    def test_filtering_them_out_leaves_the_protocol_traffic(self, window):
        window.log_panel.set_records([_sent(10), _board_log(12)])
        combo = window.log_panel.category_filter
        combo.setCurrentIndex([combo.itemData(i) for i in range(combo.count())].index("KU"))

        assert window.log_panel.model.rowCount() == 1
        assert window.log_panel.model.record_at(0).category == "KU"

    def test_they_are_not_painted_like_a_failure(self, window):
        from PySide6.QtCore import Qt

        window.log_panel.set_records([_board_log(1)])
        model = window.log_panel.model
        colour = model.data(model.index(0, 0), Qt.ItemDataRole.BackgroundRole).color()

        # The unmatched-row red is (80, 35, 35); a log line must not wear it.
        assert (colour.red(), colour.green(), colour.blue()) != (80, 35, 35)
        assert colour.blue() > colour.red()
