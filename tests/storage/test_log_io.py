"""The DSTLOG line format.

v=2 adds the wire detail the raw log view needs, v=3 the category. Older files must keep
loading — captures from
before the change are the only record of earlier bench sessions.
"""

from __future__ import annotations

import pytest

from detector_scenario_tool.domain.logs import LogRecord
from detector_scenario_tool.storage.log_io import (
    LOG_VERSION,
    LogLoadError,
    format_log_record_line,
    parse_log_line,
    parse_log_text,
)
from message_ids import OBSERVE_START

V1_LINE = f"DSTLOG|v=1|src=board|ts=120|dir=tx|id={OBSERVE_START:04X}|data=0102030405"


def _record(**kw) -> LogRecord:
    defaults = dict(
        timestamp_ms=120,
        direction="tx",
        category="KU",
        msg_id=OBSERVE_START,
        payload=bytes(range(6)),
        source="host",
    )
    defaults.update(kw)
    return LogRecord(**defaults)


class TestWriting:
    def test_the_current_version_is_written(self):
        assert f"|v={LOG_VERSION}|" in format_log_record_line(_record())

    def test_wire_detail_is_appended_when_present(self):
        line = format_log_record_line(_record(can_id=0x0BE, frame_count=3, valid=False))

        assert "|can=0BE" in line
        assert "|frames=3" in line
        assert "|valid=0" in line

    def test_defaults_are_left_out(self):
        """A short, valid, single-frame message is the common case; do not pad every line."""
        line = format_log_record_line(_record())

        assert "|frames=" not in line
        assert "|valid=" not in line
        assert "|can=" not in line


class TestReading:
    def test_round_trip(self):
        original = _record(can_id=0x3C5, frame_count=2, valid=False)
        restored = parse_log_line(format_log_record_line(original))

        assert restored.can_id == 0x3C5
        assert restored.frame_count == 2
        assert restored.valid is False
        assert restored.payload == original.payload

    def test_a_v1_line_still_loads(self):
        record = parse_log_line(V1_LINE)

        assert record.msg_id == OBSERVE_START
        assert record.payload == bytes(range(1, 6))

    def test_a_v1_line_gets_sensible_defaults(self):
        record = parse_log_line(V1_LINE)

        assert record.can_id is None
        assert record.frame_count == 1
        assert record.valid is True

    def test_an_unknown_version_is_refused(self):
        with pytest.raises(LogLoadError, match="unsupported log version"):
            parse_log_line(f"DSTLOG|v=9|src=board|ts=1|dir=tx|id={OBSERVE_START:04X}|data=00")

    def test_a_bad_can_field_is_refused_rather_than_ignored(self):
        with pytest.raises(LogLoadError, match="can"):
            parse_log_line(
                f"DSTLOG|v=2|src=board|ts=1|dir=tx|id={OBSERVE_START:04X}|data=00|can=zz"
            )

    def test_non_dstlog_lines_are_skipped(self):
        assert parse_log_line("some other output") is None

    def test_a_mixed_file_loads(self):
        text = "\n".join([V1_LINE, "noise", format_log_record_line(_record(can_id=1))])
        records = parse_log_text(text)

        assert len(records) == 2
        assert records[0].can_id is None
        assert records[1].can_id == 1
