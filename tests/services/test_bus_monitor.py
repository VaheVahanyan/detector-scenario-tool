"""Reading the bus when no run owns it.

Being connected used to do nothing on its own: the poll timer only ran during a scenario run, so
anything the board said before, between or after runs was never read at all. These tests cover the
reader itself; `test_run_controller.py` covers when it is allowed to run.
"""

from __future__ import annotations

import pytest

from detector_scenario_tool.domain.logs import LOG_CATEGORY
from detector_scenario_tool.services.bus_monitor import BoardLogAssembler, BusMonitor
from detector_scenario_tool.transport.unican import CanFrame, encode
from detector_scenario_tool.transport.virtual import VirtualBackend
from detector_scenario_tool.transport_defaults import DEFAULT_BOARD_LOG_ID
from message_ids import TM_ACK, TM_STATUS, TM_TELEMETRY


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def backend():
    b = VirtualBackend()
    b.open()
    return b


@pytest.fixture
def monitor():
    return BusMonitor(clock=Clock())


def _from_payload(backend, msg_id: int, payload: bytes):
    return encode(
        msg_id, payload,
        destination=backend.bvs_address, source=backend.na_address,
        extended=backend.settings.extended_ids,
    )


class TestPolling:
    def test_a_closed_backend_yields_nothing(self, monitor, backend):
        backend.close()
        backend.inject(_from_payload(backend, TM_STATUS, bytes(6)))

        assert monitor.poll(backend) == []

    def test_telemetry_is_read_without_any_run(self, monitor, backend):
        backend.inject(_from_payload(backend, TM_ACK, bytes(6)))

        records = monitor.poll(backend)

        assert [r.msg_id for r in records] == [TM_ACK]
        assert records[0].category == "TS"
        assert records[0].source == "detector"
        assert records[0].direction == "rx"

    def test_board_output_is_read_and_classified(self, monitor, backend):
        backend.inject(_from_payload(backend, 0x0123, b"boot ok\n"))

        record = monitor.poll(backend)[0]

        assert record.category == LOG_CATEGORY
        assert record.source == "board"

    def test_a_v2_answer_is_attributed_to_the_payload_not_to_printf(self, monitor, backend):
        """The bench firmware may be a revision behind; that is telemetry, just under old numbers."""
        backend.inject(_from_payload(backend, 0x0201, bytes(6)))

        record = monitor.poll(backend)[0]

        assert record.category == LOG_CATEGORY   # not a v2.1 message, so not matchable
        assert record.source == "detector"       # but not the board talking to itself either

    def test_the_wire_detail_is_kept(self, monitor, backend):
        frames = _from_payload(backend, TM_ACK, bytes(6))
        backend.inject(frames)

        record = monitor.poll(backend)[0]

        assert record.can_id == frames[0].can_id
        assert record.valid

    def test_nothing_on_the_bus_is_no_records(self, monitor, backend):
        assert monitor.poll(backend) == []

    def test_a_long_message_survives_being_split_across_polls(self, monitor, backend):
        """The reassembler is the monitor's own state, so a transfer may span poll calls."""
        frames = _from_payload(backend, TM_TELEMETRY, bytes(109))
        assert len(frames) > 1

        backend.inject(frames[:2])
        assert monitor.poll(backend) == []

        backend.inject(frames[2:])
        records = monitor.poll(backend)

        assert [r.msg_id for r in records] == [TM_TELEMETRY]
        assert len(records[0].payload) == 109

    def test_a_broken_frame_is_recorded_rather_than_dropped(self, monitor, backend):
        # A data frame with no start frame before it: §1.4.4.3 has nothing to attach it to.
        can_id = (backend.na_address << 5) | backend.bvs_address | (1 << 10)
        backend.inject([CanFrame(can_id, b"\x01\x02\x03")])

        record = monitor.poll(backend)[0]

        assert not record.valid
        assert record.note
        assert monitor.problems

    def test_reset_forgets_a_half_received_transfer(self, monitor, backend):
        frames = _from_payload(backend, TM_TELEMETRY, bytes(109))
        backend.inject(frames[:2])
        monitor.poll(backend)

        monitor.reset()
        backend.inject(frames[2:])

        # Without a start frame the remaining data frames are orphans, not a message.
        assert all(not r.valid for r in monitor.poll(backend))
        assert monitor.problems


def _log_frame(data: bytes) -> CanFrame:
    """A frame exactly as `BSP/UART/src/log_backend_can.c` sends one: fixed id, raw text."""
    return CanFrame(DEFAULT_BOARD_LOG_ID, data)


class TestBoardLogAssembler:
    """`log_backend_can.c`: one fixed standard identifier, up to 8 raw text bytes, no framing."""

    @pytest.fixture
    def clock(self):
        return Clock()

    @pytest.fixture
    def assembler(self, clock):
        return BoardLogAssembler(DEFAULT_BOARD_LOG_ID, clock=clock)

    def test_it_claims_its_own_identifier_only(self, assembler):
        assert assembler.owns(_log_frame(b"x"))
        assert not assembler.owns(CanFrame(0x3C5, b"x"))

    def test_an_extended_frame_with_the_same_number_is_not_it(self, assembler):
        """The firmware sends a standard frame; a 29-bit one carrying that value is something else."""
        assert not assembler.owns(CanFrame(DEFAULT_BOARD_LOG_ID, b"x", extended=True))

    def test_frames_are_joined_into_a_line(self, assembler):
        records = []
        for chunk in (b"NAND1 er", b"ase done", b"\r\n"):
            records += assembler.feed(_log_frame(chunk))

        assert [r.payload for r in records] == [b"NAND1 erase done\r\n"]
        assert records[0].frame_count == 3
        assert records[0].category == LOG_CATEGORY
        assert records[0].source == "board"
        assert records[0].can_id == DEFAULT_BOARD_LOG_ID

    def test_an_unfinished_line_waits_for_the_rest(self, assembler):
        assert assembler.feed(_log_frame(b"boot ")) == []

    def test_two_lines_in_one_frame_become_two_records(self, assembler):
        records = assembler.feed(_log_frame(b"a\r\nb\r\n"))

        assert [r.payload for r in records] == [b"a\r\n", b"b\r\n"]

    def test_a_line_is_timestamped_when_it_started(self, assembler, clock):
        assembler.feed(_log_frame(b"star"))
        clock.now = 40.0
        records = assembler.feed(_log_frame(b"t\n"))

        assert records[0].timestamp_ms == 0

    def test_a_tail_with_no_newline_comes_out_once_the_board_falls_silent(self, assembler, clock):
        """`debug_log_write_u32_inline` prints a number with no newline after it."""
        assembler.feed(_log_frame(b"count="))

        assert assembler.flush() == []

        clock.now = BoardLogAssembler.LINE_TIMEOUT_MS + 1
        records = assembler.flush()

        assert [r.payload for r in records] == [b"count="]

    def test_flushing_can_be_forced(self, assembler):
        assembler.feed(_log_frame(b"partial"))

        assert [r.payload for r in assembler.flush(force=True)] == [b"partial"]

    def test_a_firmware_that_never_writes_a_newline_still_reports(self, assembler):
        records = []
        for _ in range((BoardLogAssembler.MAX_LINE_BYTES // 8) + 1):
            records += assembler.feed(_log_frame(b"12345678"))

        assert records
        assert len(records[0].payload) >= BoardLogAssembler.MAX_LINE_BYTES

    def test_reset_forgets_a_half_written_line(self, assembler):
        assembler.feed(_log_frame(b"half"))
        assembler.reset()

        assert assembler.flush(force=True) == []


class TestBoardLogOnTheBus:
    def test_a_log_line_is_read_as_a_line(self, monitor, backend):
        backend.inject([_log_frame(b"boot ok\r\n")])

        records = monitor.poll(backend)

        assert [r.payload for r in records] == [b"boot ok\r\n"]
        assert records[0].category == LOG_CATEGORY

    def test_it_never_reaches_the_reassembler(self, monitor, backend):
        """0x7DB read as UniCAN is a continuation frame; the reassembler would report an error."""
        backend.inject([_log_frame(b"boot ok\r\n")])

        monitor.poll(backend)

        assert monitor.problems == []

    def test_log_frames_do_not_corrupt_a_long_telemetry_message(self, monitor, backend):
        """The reason this is filtered before reassembly, not after.

        `0x7DB` decodes to sender `0x1E` — the payload's own address — with the data bit set, so
        before the filter its bytes were appended into whatever long transfer that sender had in
        flight, and the telemetry died of a length or CRC error.
        """
        payload = bytes(range(109))
        frames = _from_payload(backend, TM_TELEMETRY, payload)
        backend.inject([frames[0], _log_frame(b"tick\r\n"), *frames[1:]])

        records = monitor.poll(backend)

        assert monitor.problems == []
        telemetry = [r for r in records if r.category == "TS"]
        assert [r.msg_id for r in telemetry] == [TM_TELEMETRY]
        assert telemetry[0].payload == payload
        assert [r.payload for r in records if r.category == LOG_CATEGORY] == [b"tick\r\n"]

    def test_the_identifier_is_configurable(self, backend):
        """It is a firmware constant, not a protocol one: another build may use another number."""
        monitor = BusMonitor(clock=Clock(), board_log_id=0x123)
        backend.inject([CanFrame(0x123, b"hello\r\n")])

        assert [r.payload for r in monitor.poll(backend)] == [b"hello\r\n"]

    def test_an_unfinished_line_is_flushed_by_a_later_poll(self, backend):
        clock = Clock()
        monitor = BusMonitor(clock=clock)
        backend.inject([_log_frame(b"no newline here")])

        assert monitor.poll(backend) == []

        clock.now = BoardLogAssembler.LINE_TIMEOUT_MS + 1
        assert [r.payload for r in monitor.poll(backend)] == [b"no newline here"]
