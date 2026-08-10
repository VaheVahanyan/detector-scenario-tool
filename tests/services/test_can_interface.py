"""Bringing a SocketCAN interface up through PolicyKit.

This is the only thing in the application that runs with elevated rights, so the tests are mostly
about refusing to pass anything unexpected to a command running as root.
"""

from __future__ import annotations

import subprocess

import pytest

from detector_scenario_tool.services import can_interface


class FakeCompleted:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _runner(returncode: int = 0, stdout: str = "", stderr: str = "", record: list | None = None):
    def run(args, **kwargs):
        if record is not None:
            record.append((args, kwargs))
        return FakeCompleted(returncode, stdout, stderr)

    return run


class TestValidation:
    @pytest.mark.parametrize("channel", ["can0", "vcan0", "can1", "slcan0", "a"])
    def test_ordinary_interface_names_pass(self, channel):
        assert can_interface.validate(channel, 500_000) is None

    @pytest.mark.parametrize(
        "channel",
        [
            "",
            "0can",              # must start with a letter
            "can0; rm -rf /",    # command separators
            "can 0",             # whitespace
            "CAN0",              # upper case is not an interface name
            "../../etc/passwd",
            "a" * 20,            # longer than an interface name can be
            "$(id)",
        ],
    )
    def test_anything_unusual_is_refused(self, channel):
        assert can_interface.validate(channel, 500_000) == "caninterface.bad_channel"

    @pytest.mark.parametrize("bitrate", [0, -1, 9_999, 2_000_000, "500000", None])
    def test_implausible_bitrates_are_refused(self, bitrate):
        assert can_interface.validate("can0", bitrate) == "caninterface.bad_bitrate"

    def test_the_documented_bus_speed_is_allowed(self):
        """CAN1 runs at 1 Mbit/s (SXC РЭ §1.4.11)."""
        assert can_interface.validate("can0", 1_000_000) is None


class TestCommand:
    def test_the_interface_is_taken_down_first(self):
        """`type can bitrate` is rejected on an interface that is already up."""
        script = can_interface.batch_script("can0", 500_000)
        lines = script.strip().splitlines()

        assert lines[0] == "link set can0 down"
        assert lines[1] == "link set can0 type can bitrate 500000"
        assert lines[2] == "link set can0 up"

    def test_the_description_is_something_a_user_could_paste(self):
        text = can_interface.describe_command("can0", 1_000_000)

        assert "ip link set can0" in text
        assert "1000000" in text

    def test_the_script_is_passed_on_stdin_not_through_a_shell(self):
        """No shell means no quoting to get wrong."""
        record = []
        can_interface.configure("can0", 500_000, runner=_runner(record=record))

        args, kwargs = record[0]
        assert isinstance(args, list)
        assert args[0].endswith("pkexec")
        assert args[1].endswith("ip")
        assert args[2:] == ["-batch", "-"]
        assert "shell" not in kwargs
        assert "link set can0 up" in kwargs["input"]


class TestConfigure:
    def test_success(self):
        result = can_interface.configure("can0", 500_000, runner=_runner(0))
        assert result.ok
        assert not result.cancelled

    def test_a_rejected_argument_never_reaches_the_runner(self):
        record = []
        result = can_interface.configure("can0; id", 500_000, runner=_runner(record=record))

        assert not result.ok
        assert result.detail == "caninterface.bad_channel"
        assert record == [], "nothing may be executed after validation fails"

    @pytest.mark.parametrize("code", [126, 127])
    def test_a_dismissed_password_prompt_is_not_an_error(self, code):
        """Cancelling the dialog is a normal outcome, not a failure to report loudly."""
        result = can_interface.configure("can0", 500_000, runner=_runner(code))

        assert not result.ok
        assert result.cancelled

    def test_a_real_failure_carries_the_tool_output(self):
        result = can_interface.configure(
            "can0", 500_000, runner=_runner(1, stderr="Cannot find device \"can0\"")
        )

        assert not result.ok
        assert not result.cancelled
        assert "Cannot find device" in result.detail

    def test_a_timeout_is_reported(self):
        def run(*a, **kw):
            raise subprocess.TimeoutExpired(cmd="pkexec", timeout=60)

        result = can_interface.configure("can0", 500_000, runner=run)

        assert not result.ok
        assert result.detail == "caninterface.timeout"

    def test_a_missing_executable_is_reported(self):
        def run(*a, **kw):
            raise OSError("No such file or directory")

        result = can_interface.configure("can0", 500_000, runner=run)

        assert not result.ok
        assert "No such file" in result.detail


class TestAvailability:
    def test_it_reports_whether_the_tools_exist(self, monkeypatch):
        monkeypatch.setattr(can_interface.shutil, "which", lambda name: None)
        assert not can_interface.is_available()

        monkeypatch.setattr(can_interface.shutil, "which", lambda name: f"/usr/bin/{name}")
        assert can_interface.is_available()

    def test_configure_refuses_when_the_tools_are_missing(self, monkeypatch):
        monkeypatch.setattr(can_interface.shutil, "which", lambda name: None)
        result = can_interface.configure("can0", 500_000, runner=_runner(0))

        assert result.detail == "caninterface.tools_missing"
