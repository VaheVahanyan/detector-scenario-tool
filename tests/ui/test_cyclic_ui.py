"""Cyclic controls in the window.

The inspector only offers repeating for messages the protocol repeats, and the run panel carries
the master switch that turns telemetry commands off for a whole run.
"""

from __future__ import annotations

import pytest
from message_ids import STATUS_REQ, TLM_MAGFIELD, TLM_MCILWAIN

MCILWAIN = TLM_MCILWAIN


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    from detector_scenario_tool.ui.main_window import MainWindow

    w = MainWindow()
    qtbot.addWidget(w)
    return w


def _pick(window, selector, msg_id: int) -> None:
    for i in range(selector.count()):
        if selector.itemData(i)[1] == msg_id:
            selector.setCurrentIndex(i)
            return
    raise AssertionError(f"0x{msg_id:04X} not in the selector")


def _add_tc(window, msg_id: int = MCILWAIN):
    window._add_kt_step()
    window._select_row(len(window.document.steps) - 1)
    _pick(window, window.inspector_panel.msg_selector, msg_id)
    return window.document.steps[-1]


def _add_cc(window, msg_id: int = STATUS_REQ):
    window._add_ku_step()
    window._select_row(len(window.document.steps) - 1)
    _pick(window, window.inspector_panel.msg_selector, msg_id)
    return window.document.steps[-1]


class TestInspector:
    def test_a_telemetry_command_starts_out_repeating(self, window):
        step = _add_tc(window)

        assert step.cyclic is not None
        assert step.cyclic.enabled
        assert step.cyclic.period_ms == 20_000

    def test_the_cyclic_group_is_shown_for_telemetry_commands(self, window):
        _add_tc(window)
        assert window.inspector_panel.cyclic_group.isVisibleTo(window.inspector_panel)

    def test_the_cyclic_group_is_hidden_for_control_commands(self, window):
        _add_cc(window)
        assert not window.inspector_panel.cyclic_group.isVisibleTo(window.inspector_panel)

    def test_a_control_command_carries_no_policy(self, window):
        step = _add_cc(window)
        assert step.cyclic is None

    def test_repeating_can_be_turned_off_for_a_single_shot(self, window):
        """Sending one КТ on its own is what bench testing needs."""
        step = _add_tc(window)

        window.inspector_panel.cyclic_enabled_checkbox.setChecked(False)

        assert step.cyclic is not None
        assert step.cyclic.enabled is False

    def test_the_period_is_edited_in_seconds(self, window):
        step = _add_tc(window)

        window.inspector_panel.cyclic_period_spin.setValue(5)

        assert step.cyclic.period_ms == 5000

    def test_the_period_field_follows_the_checkbox(self, window):
        _add_tc(window)
        panel = window.inspector_panel

        panel.cyclic_enabled_checkbox.setChecked(False)
        assert not panel.cyclic_period_spin.isEnabled()

        panel.cyclic_enabled_checkbox.setChecked(True)
        assert panel.cyclic_period_spin.isEnabled()

    def test_switching_from_a_telemetry_to_a_control_command_drops_the_policy(self, window):
        step = _add_tc(window)
        assert step.cyclic is not None

        _pick(window, window.inspector_panel.msg_selector, TLM_MAGFIELD)
        assert step.cyclic is not None, "another telemetry command still repeats"

    def test_the_setting_survives_a_save_and_load(self, window, tmp_path):
        from detector_scenario_tool.storage.scenario_io import load_scenario, save_scenario

        step = _add_tc(window)
        window.inspector_panel.cyclic_period_spin.setValue(7)
        window.inspector_panel.cyclic_enabled_checkbox.setChecked(True)

        path = tmp_path / "cyclic.json"
        save_scenario(window.document, path)
        loaded = load_scenario(path)

        assert loaded.steps[0].cyclic.enabled is True
        assert loaded.steps[0].cyclic.period_ms == 7000


class TestRunPanelSwitch:
    def test_telemetry_sending_is_on_by_default(self, window):
        assert window.run_panel.send_telemetry_commands() is True

    def test_the_switch_reaches_the_runner(self, window):
        from detector_scenario_tool.transport.backend import ConnectionSettings

        _add_tc(window)
        window.run_panel.send_telemetry_checkbox.setChecked(False)
        window.run_controller.connect_to(ConnectionSettings(backend="virtual"))

        window._start_run()

        assert window.runner.send_telemetry_commands is False

    def test_disabling_skips_telemetry_but_not_control_commands(self, window):
        from detector_scenario_tool.transport.backend import ConnectionSettings

        _add_tc(window)
        _add_cc(window)
        window.run_panel.send_telemetry_checkbox.setChecked(False)
        window.run_controller.connect_to(ConnectionSettings(backend="virtual"))

        window._start_run()
        runner = window.runner
        for _ in range(50):
            if not runner.state.is_active:
                break
            runner.tick()

        sent = [msg_id for msg_id, _ in window.run_controller.backend.simulator.received]
        assert MCILWAIN not in sent
        assert STATUS_REQ in sent


class TestValidation:
    def test_a_repeating_telemetry_command_explains_its_mode_scope(self, window):
        _add_tc(window)
        window.flush_pending_refresh()

        codes = [window.warnings_model.items[i].code for i in range(window.warnings_model.rowCount())]
        assert "cyclic.mode_scope" in codes

    def test_a_scenario_that_ends_immediately_is_flagged(self, window):
        """Repeats stop with the run, so a missing trailing wait means no repeat ever happens."""
        _add_tc(window)
        window.flush_pending_refresh()

        codes = [window.warnings_model.items[i].code for i in range(window.warnings_model.rowCount())]
        assert "cyclic.no_time_to_repeat" in codes

    def test_a_trailing_wait_satisfies_it(self, window):
        _add_tc(window)
        window._add_wait_step()
        window.document.steps[-1].delay_ms = 60_000
        window.flush_pending_refresh()

        codes = [window.warnings_model.items[i].code for i in range(window.warnings_model.rowCount())]
        assert "cyclic.no_time_to_repeat" not in codes

    def test_the_note_is_gone_once_repeating_is_off(self, window):
        _add_tc(window)
        window.inspector_panel.cyclic_enabled_checkbox.setChecked(False)
        window.flush_pending_refresh()

        codes = [window.warnings_model.items[i].code for i in range(window.warnings_model.rowCount())]
        assert "cyclic.mode_scope" not in codes


class TestTimeline:
    def test_a_repeating_send_is_marked_on_the_timeline(self, window):
        _add_tc(window)
        window.flush_pending_refresh()

        from detector_scenario_tool.domain.timeline import build_timeline

        items = build_timeline(window.document).items
        assert items[0].repeat_period_ms == 20_000
        assert "20" in items[0].tooltip

    def test_a_single_shot_carries_no_period(self, window):
        _add_tc(window)
        window.inspector_panel.cyclic_enabled_checkbox.setChecked(False)
        window.flush_pending_refresh()

        from detector_scenario_tool.domain.timeline import build_timeline

        assert build_timeline(window.document).items[0].repeat_period_ms == 0
