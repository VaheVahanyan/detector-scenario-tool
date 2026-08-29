"""Text the board prints onto the CAN bus.

In some firmware configurations the МК sends its own debug output over CAN under identifiers that
belong to no protocol revision. Those frames are logs, not answers, and the two things the tool
must get right are telling them apart from telemetry and showing them as text rather than bytes.
"""

from __future__ import annotations

import pytest

from detector_scenario_tool.domain.logs import (
    LOG_CATEGORY,
    LogRecord,
    decode_log_text,
    log_text_line,
    looks_like_text,
)
from detector_scenario_tool.i18n import set_language, tr
from detector_scenario_tool.protocol import registry
from detector_scenario_tool.protocol.log_decode import build_log_detail, build_log_summary, incoming_category
from detector_scenario_tool.utils.labels import category_long, category_short, message_label
from message_ids import STATUS_REQ, TM_ACK, TM_STATUS, UNKNOWN


@pytest.fixture(autouse=True)
def restore_language():
    yield
    set_language("ru")


def _log_record(payload: bytes, msg_id: int = 0x0123) -> LogRecord:
    return LogRecord(
        timestamp_ms=10,
        direction="rx",
        category=LOG_CATEGORY,
        msg_id=msg_id,
        payload=payload,
        source="board",
    )


class TestClassification:
    @pytest.mark.parametrize("symbol", ["TM_ACK", "TM_STATUS", "TM_TELEMETRY", "TM_VERSION"])
    def test_a_catalogue_telemetry_message_stays_telemetry(self, symbol):
        assert incoming_category(registry.by_symbol(symbol).msg_id) == "TS"

    def test_an_identifier_no_catalogue_holds_is_a_log(self):
        assert incoming_category(UNKNOWN) == LOG_CATEGORY

    def test_a_control_command_coming_back_is_a_log_not_an_answer(self):
        """Only a ТС is an answer. A КУ on the bus was sent by somebody, not by the НА."""
        assert incoming_category(STATUS_REQ) == LOG_CATEGORY

    def test_a_user_defined_telemetry_message_counts_as_telemetry(self):
        """The registry is the authority, and a scenario may add to it at runtime."""
        from detector_scenario_tool.protocol.fields import MessageDef

        spec = MessageDef(
            category="TS", msg_id=0x0FFE, symbol="TM_USER", name_key="msg.tm_user",
            length=1, fields=(),
        )
        registry.register(spec, replace=True)
        try:
            assert incoming_category(0x0FFE) == "TS"
        finally:
            registry.unregister("TS", 0x0FFE)

        assert incoming_category(0x0FFE) == LOG_CATEGORY


class TestTextDetection:
    @pytest.mark.parametrize(
        "payload",
        [b"INIT ok", b"adc=1024\r\n", "температура 21\n".encode(), b"..."],
    )
    def test_printable_payloads_read_as_text(self, payload):
        assert looks_like_text(payload)

    @pytest.mark.parametrize(
        "payload",
        [b"", b"\x00\x00\x00", bytes(range(8)), bytes([0x01, 0x00, 0x00, 0xAA, 0xAA, 0xAA])],
    )
    def test_binary_payloads_do_not(self, payload):
        assert not looks_like_text(payload)

    def test_padding_is_not_content(self):
        assert looks_like_text(b"ok\x00\x00\x00\x00")

    def test_a_frame_that_starts_mid_character_still_reads_as_text(self):
        """The МК splits a long line across 6-byte frames, so cyrillic gets cut in half."""
        chunk = "температура 21".encode()[3:9]
        assert looks_like_text(chunk)


class TestRendering:
    def test_trailing_padding_and_line_breaks_are_dropped(self):
        assert decode_log_text(b"INIT ok\r\n\x00\x00") == "INIT ok"

    def test_cyrillic_survives(self):
        assert decode_log_text("датчик 3: 12.5\n".encode()) == "датчик 3: 12.5"

    def test_control_characters_are_made_visible_rather_than_hidden(self):
        assert decode_log_text(b"a\x01b") == "a·b"

    def test_a_table_cell_gets_one_line(self):
        assert log_text_line(b"line one\nline two\n") == "line one line two"

    def test_the_summary_is_the_text(self):
        assert build_log_summary(_log_record(b"NAND1 erase done\n")) == "NAND1 erase done"

    def test_a_binary_payload_says_so_instead_of_printing_mojibake(self):
        summary = build_log_summary(_log_record(bytes(range(8))))
        assert summary == tr("logdecode.board_log.binary", length=8)

    def test_the_detail_names_the_identifier_and_shows_the_text(self):
        detail = build_log_detail(_log_record(b"boot\n", msg_id=0x0123))
        assert "0x0123" in detail
        assert "boot" in detail

    def test_the_detail_of_a_binary_payload_falls_back_to_hex(self):
        detail = build_log_detail(_log_record(b"\x01\x02\x03\x00\x99"))
        assert "01 02 03 00 99" in detail

    def test_telemetry_is_still_decoded_as_telemetry(self):
        """The board-log branch must not swallow real messages."""
        record = LogRecord(
            timestamp_ms=1, direction="rx", category="TS", msg_id=TM_ACK,
            payload=bytes([0x01, 0x00, 0x00, 0xAA, 0xAA, 0xAA]), source="detector",
        )
        assert tr("logdecode.board_log.binary", length=6) not in build_log_summary(record)


class TestLabels:
    def test_the_row_is_labelled_by_its_identifier(self):
        set_language("ru")
        assert message_label(LOG_CATEGORY, 0x0123) == "Лог 0x0123"

    @pytest.mark.parametrize("language", ["ru", "en"])
    def test_both_languages_name_the_category(self, language):
        set_language(language)
        assert category_short(LOG_CATEGORY) != f"category.{LOG_CATEGORY}.short"
        assert category_long(LOG_CATEGORY) != f"category.{LOG_CATEGORY}.long"

    def test_a_log_record_knows_what_it_is(self):
        assert _log_record(b"x").is_board_log
        assert not LogRecord(
            timestamp_ms=1, direction="rx", category="TS", msg_id=TM_STATUS,
            payload=b"", source="detector",
        ).is_board_log


class TestLegacyV2Numbering:
    """The bench firmware may still be on `Протокол_CAN_ГС_v2`.

    Its answers then arrive under the old numbers. They are still not v2.1 messages — the tool
    speaks one revision only (C2) — but showing them as anonymous board output would hide the one
    fact worth knowing at the bench.
    """

    def test_an_old_acknowledgement_is_named_rather_than_shown_as_text(self):
        set_language("ru")
        summary = build_log_summary(_log_record(bytes(6), msg_id=0x0201))

        assert "0x0D01" in summary
        assert "Квитанция" in summary

    def test_the_detail_says_what_is_going_on(self):
        set_language("ru")
        detail = build_log_detail(_log_record(bytes(6), msg_id=0x0201))

        assert "0x0201" in detail
        assert "v2" in detail

    def test_it_is_still_not_a_message_the_tool_will_match(self):
        """Recognition is not support: the identifier stays outside the catalogue."""
        assert incoming_category(0x0201) == LOG_CATEGORY
        assert registry.find("TS", 0x0201) is None

    def test_an_identifier_that_never_moved_is_ordinary_board_output(self):
        assert build_log_summary(_log_record(b"plain text", msg_id=0x0123)) == "plain text"
