"""The v2 identifier table — recognition only, never support."""

from __future__ import annotations

import pytest

from detector_scenario_tool.protocol import legacy_v2, registry


class TestTable:
    def test_every_moved_number_is_free_in_the_current_catalogue(self):
        """Otherwise recognising an old number would shadow a live message."""
        collisions = [
            (category, old)
            for category, table in legacy_v2.V2_TO_V2_1.items()
            for old in table
            if registry.find(category, old) is not None
        ]
        assert collisions == []

    def test_every_destination_exists(self):
        missing = [
            (category, new)
            for category, table in legacy_v2.V2_TO_V2_1.items()
            for new in table.values()
            if registry.find(category, new) is None
        ]
        assert missing == []

    @pytest.mark.parametrize(
        "old, category, symbol",
        [
            (0x0200, "TS", "TM_STATUS"),
            (0x0201, "TS", "TM_ACK"),
            (0x0202, "TS", "TM_TELEMETRY"),
            (0x0203, "TS", "TM_TEST_RESULT"),
            (0x0100, "KT", "TLM_MCILWAIN"),
            (0x0001, "KU", "CMD_STATUS_REQ"),
        ],
    )
    def test_recognition(self, old, category, symbol):
        assert legacy_v2.recognise(old) == (category, registry.by_symbol(symbol).msg_id)

    def test_a_current_identifier_is_not_recognised_as_legacy(self):
        assert legacy_v2.recognise(registry.by_symbol("TM_ACK").msg_id) is None

    def test_an_identifier_that_never_moved_is_not_recognised(self):
        """0401h, 0A61h, 0A62h kept their numbers, so there is nothing to translate."""
        assert legacy_v2.recognise(0x0401) is None

    def test_current_id_needs_the_right_category(self):
        assert legacy_v2.current_id("TS", 0x0201) == registry.by_symbol("TM_ACK").msg_id
        assert legacy_v2.current_id("KU", 0x0201) is None
