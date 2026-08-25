"""Running a scenario from the window, against the simulated detector.

The point of the dry run is that it exercises the real path — packing, UniCAN framing,
acknowledgement matching, mode checks — so these tests go through the UI rather than the runner.
"""

from __future__ import annotations

import pytest

from detector_scenario_tool.services.scenario_runner import RunState
from detector_scenario_tool.transport.backend import ConnectionSettings
from message_ids import OBSERVE_CTRL, STATUS_REQ, TM_ACK


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    # Keep the test off the developer's real settings file.
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    from detector_scenario_tool.ui.main_window import MainWindow

    w = MainWindow()
    qtbot.addWidget(w)
    return w


def _add_send(window, msg_id: int):
    window._add_ku_step()
    window._select_row(len(window.document.steps) - 1)
    selector = window.inspector_panel.msg_selector
    for i in range(selector.count()):
        if selector.itemData(i)[1] == msg_id:
            selector.setCurrentIndex(i)
            return


def _connect(window) -> None:
    assert window.run_controller.connect_to(ConnectionSettings(backend="virtual"))


def _run_to_completion(window, max_ticks: int = 300):
    runner = window.runner
    assert runner is not None
    for _ in range(max_ticks):
        if not runner.state.is_active:
            return runner
        runner.tick()
    raise AssertionError(f"run did not finish; state={runner.state}")


class TestDryRun:
    def test_a_scenario_runs_to_completion(self, window):
        _add_send(window, STATUS_REQ)
        window._add_wait_ts_step()
        _connect(window)

        window._start_run()
        runner = _run_to_completion(window)

        assert runner.state is RunState.FINISHED
        assert runner.summary.failures == 0

    def test_traffic_lands_in_the_log(self, window):
        _add_send(window, STATUS_REQ)
        _connect(window)

        window._start_run()
        _run_to_completion(window)

        sources = {record.source for record in window.log_records}
        assert sources == {"host", "detector"}
        assert any(r.direction == "tx" and r.msg_id == STATUS_REQ for r in window.log_records)
        assert any(r.direction == "rx" and r.msg_id == TM_ACK for r in window.log_records)

    def test_step_statuses_reach_the_table_and_the_timeline(self, window):
        _add_send(window, STATUS_REQ)
        _connect(window)

        window._start_run()
        _run_to_completion(window)

        assert window._run_statuses[0] == "ok"
        assert window.table_model._row_statuses[0] == "ok"
        assert window.timeline_panel._row_statuses[0] == "ok"

    def test_a_command_invalid_in_the_current_mode_is_reported(self, window):
        """CMD_OBSERVE_CTRL outside OBSERVE gets ERR_MODE back from the simulated detector."""
        _add_send(window, OBSERVE_CTRL)
        _connect(window)

        window._start_run()
        runner = _run_to_completion(window)

        assert runner.state is RunState.FAILED
        assert window._run_statuses[0] == "error"
        assert "ERR_MODE" in runner.summary.detail

    def test_the_summary_is_shown(self, window):
        _add_send(window, STATUS_REQ)
        _connect(window)

        window._start_run()
        _run_to_completion(window)

        assert window.run_panel.status_label.text()


class TestSafety:
    def test_a_simulated_backend_needs_no_confirmation(self, window):
        _connect(window)
        assert window._confirm_live_run() is True

    def test_the_live_banner_is_hidden_while_simulating(self, window):
        _connect(window)
        assert not window.run_panel.live_banner.isVisible()

    def test_a_real_backend_asks_before_transmitting(self, window, monkeypatch):
        from PySide6.QtWidgets import QMessageBox

        _connect(window)
        monkeypatch.setattr(
            window.run_controller.backend.__class__, "is_simulated", property(lambda self: False)
        )

        asked = []
        monkeypatch.setattr(
            QMessageBox,
            "question",
            lambda *a, **k: (asked.append(1), QMessageBox.StandardButton.No)[1],
        )

        assert window._confirm_live_run() is False
        assert asked, "no confirmation was requested before touching hardware"

    def test_declining_the_confirmation_starts_nothing(self, window, monkeypatch):
        from PySide6.QtWidgets import QMessageBox

        _add_send(window, STATUS_REQ)
        _connect(window)
        monkeypatch.setattr(
            window.run_controller.backend.__class__, "is_simulated", property(lambda self: False)
        )
        monkeypatch.setattr(
            QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No
        )

        window._start_run()

        assert window.runner is None

    def test_confirming_once_does_not_arm_the_next_connection(self, window, monkeypatch):
        from PySide6.QtWidgets import QMessageBox

        _connect(window)
        monkeypatch.setattr(
            window.run_controller.backend.__class__, "is_simulated", property(lambda self: False)
        )
        monkeypatch.setattr(
            QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes
        )
        assert window._confirm_live_run() is True

        window._disconnect_transport()
        _connect(window)

        assert window._live_run_confirmed is False


class TestControls:
    def test_run_controls_are_disabled_until_connected(self, window):
        assert not window.run_panel.run_button.isEnabled()

        _connect(window)

        assert window.run_panel.run_button.isEnabled()

    def test_single_stepping_pauses_between_steps(self, window):
        _add_send(window, STATUS_REQ)
        _add_send(window, STATUS_REQ)
        _connect(window)

        window._step_run()
        runner = window.runner
        for _ in range(50):
            if runner.state is not RunState.RUNNING:
                break
            runner.tick()

        assert runner.state is RunState.PAUSED
        assert runner.summary.steps_done == 1

    def test_stopping_ends_the_run(self, window):
        _add_send(window, STATUS_REQ)
        _connect(window)

        window._start_run()
        window.run_controller.stop()

        assert window.runner.state is RunState.STOPPED


class TestSettingsPersistence:
    def test_connecting_saves_the_settings(self, window, tmp_path):
        from detector_scenario_tool.app import settings as app_settings

        settings = ConnectionSettings(backend="virtual", channel="can0", bitrate=500000)
        window._connect_transport(settings)

        restored = app_settings.load_connection_settings()
        assert restored.channel == "can0"
        assert restored.bitrate == 500000

    def test_a_corrupt_settings_file_is_ignored(self, tmp_path, monkeypatch):
        from detector_scenario_tool.app import settings as app_settings

        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        path = app_settings.settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not json", encoding="utf-8")

        assert app_settings.load() == {}
        assert app_settings.load_connection_settings().backend == "virtual"
