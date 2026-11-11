"""The board's serial output — LPUART1, USART2, FTDI — is captured whole, not only `DSTLOG` lines.

On those backends the firmware prints plain text (`STATE IDLE -> DUTY`, a driver's bring-up
report); until this, every such line was silently dropped.
"""

from __future__ import annotations

import pytest

from detector_scenario_tool.domain.logs import LOG_CATEGORY, is_clean_text
from detector_scenario_tool.logs.text_lines import TextLineSplitter
from detector_scenario_tool.protocol.log_decode import build_log_summary
from detector_scenario_tool.services.serial_log_controller import SerialLogController
from detector_scenario_tool.storage.log_io import format_log_record_line, parse_log_line, parse_log_text
from message_ids import STATUS_REQ, TELEM_REQ


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def controller(qapp):
    clock = FakeClock()
    ctl = SerialLogController("/dev/null", clock=clock)
    ctl.clock = clock
    ctl.records = []
    ctl.record_received.connect(ctl.records.append)
    return ctl


class TestSerialCapture:
    def test_a_text_line_becomes_a_board_log_record(self, controller):
        controller.feed(b"STATE IDLE -> DUTY\r\n")

        (record,) = controller.records
        assert record.category == LOG_CATEGORY
        assert record.source == "board"
        assert record.is_text_only
        assert build_log_summary(record) == "STATE IDLE -> DUTY"

    def test_a_dstlog_line_is_still_a_protocol_record(self, controller):
        controller.feed(f"DSTLOG|v=1|src=detector|ts=55|dir=rx|id={STATUS_REQ:04X}|data=\r\n".encode())

        (record,) = controller.records
        assert record.category == "KU"
        assert record.msg_id == STATUS_REQ
        assert record.timestamp_ms == 55

    def test_text_and_protocol_lines_interleave_in_order(self, controller):
        controller.feed(
            b"boot\r\n"
            + f"DSTLOG|v=1|src=detector|ts=5|dir=rx|id={STATUS_REQ:04X}|data=\r\n".encode()
            + b"STATE IDLE -> DUTY\r\n"
        )

        assert [r.category for r in controller.records] == [LOG_CATEGORY, "KU", LOG_CATEGORY]

    def test_a_line_split_across_reads_is_put_back_together(self, controller):
        controller.feed(b"erase_st")
        controller.feed(b"age=2 bank=1\r\n")

        assert [build_log_summary(r) for r in controller.records] == ["erase_stage=2 bank=1"]

    def test_an_unterminated_number_comes_out_after_a_pause(self, controller):
        """`debug_log_write_u32_inline` prints with no newline at all."""
        controller.feed(b"12345")
        assert controller.records == []

        controller.clock.now += TextLineSplitter.LINE_TIMEOUT_MS + 1
        controller.feed(b"")

        assert [build_log_summary(r) for r in controller.records] == ["12345"]

    def test_a_dstlog_line_this_version_cannot_place_is_kept_as_text(self, controller):
        controller.feed(b"DSTLOG|v=1|src=detector|ts=5|dir=rx|id=7777|data=\r\n")

        (record,) = controller.records
        assert record.category == LOG_CATEGORY
        assert "7777" in record.note

    def test_cyrillic_text_survives(self, controller):
        controller.feed("НАНД1: стирание завершено\r\n".encode())

        assert build_log_summary(controller.records[0]) == "НАНД1: стирание завершено"

    def test_binary_data_is_counted_not_logged(self, controller):
        """The FTDI port carries science packets too; they belong to the packet monitor."""
        controller.feed(bytes([0xFF, 0x46, 0xD7, 0xC9, 0x00, 0x9C, 0x81]) + b"\n")

        assert controller.records == []
        assert controller.binary_bytes_skipped == 7


class TestCleanText:
    @pytest.mark.parametrize("data", [b"STATE IDLE -> DUTY", "стирание".encode(), b"  indented"])
    def test_text(self, data):
        assert is_clean_text(data)

    @pytest.mark.parametrize("data", [bytes(range(256)), b"\xff\x46\xd7\xc9", b"\x00\x01\x02ab", b""])
    def test_not_text(self, data):
        assert not is_clean_text(data)


class TestImportKeepsText:
    def test_a_terminal_capture_keeps_every_line(self):
        text = "\n".join([
            "boot ok",
            f"DSTLOG|v=1|src=detector|ts=40|dir=rx|id={TELEM_REQ:04X}|data=",
            "STATE IDLE -> DUTY",
        ])

        records = parse_log_text(text, keep_text=True)

        assert [r.category for r in records] == [LOG_CATEGORY, "KU", LOG_CATEGORY]
        # A text line has no time of its own and inherits the last one seen.
        assert [r.timestamp_ms for r in records] == [0, 40, 40]

    def test_without_keep_text_the_old_behaviour_stands(self):
        assert parse_log_text("boot ok\nmore text") == []

    def test_a_saved_text_line_round_trips(self):
        records = parse_log_text("STATE IDLE -> DUTY", keep_text=True)

        restored = parse_log_line(format_log_record_line(records[0]))

        assert restored.is_text_only
        assert build_log_summary(restored) == "STATE IDLE -> DUTY"

    def test_a_text_line_is_never_read_as_a_v2_identifier(self):
        """0x0000 was a control command in v2; a line of text must not be called "a revision behind"."""
        (record,) = parse_log_text("hello", keep_text=True)

        assert build_log_summary(record) == "hello"
