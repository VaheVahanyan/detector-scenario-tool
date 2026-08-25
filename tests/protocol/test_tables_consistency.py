"""The "parallel tables" guard rail.

A message is currently described in seven independent places (see CLAUDE.md). Adding one and
forgetting another produces silently wrong output rather than an error. Until phase 1 replaces
these with a single declarative definition, this test is what keeps them in step.
"""

from __future__ import annotations

import pytest

from detector_scenario_tool.protocol.catalog import ProtocolCatalog
from detector_scenario_tool.protocol.expected_responses import (
    get_expected_responses,
    get_send_defaults,
)
from detector_scenario_tool.protocol.message_lengths import (
    EXPECTED_MESSAGE_LENGTHS,
    get_expected_message_length,
)
from detector_scenario_tool.ui.editors.payload_editor_registry import (
    build_payload_editor_registry,
)
from detector_scenario_tool.validation.mode_analyzer import ALLOWED_KU_BY_MODE
from message_ids import TM_ACK

CATALOG = ProtocolCatalog()
ALL_MESSAGES = CATALOG.messages
SENDABLE = [m for m in ALL_MESSAGES if m.category in ("KU", "KT")]

_ids = lambda messages: [f"{m.category}-0x{m.msg_id:04X}" for m in messages]  # noqa: E731


@pytest.mark.parametrize("message", ALL_MESSAGES, ids=_ids(ALL_MESSAGES))
def test_every_catalog_message_has_a_declared_length(message):
    assert get_expected_message_length(message.category, message.msg_id) is not None


@pytest.mark.parametrize("message", ALL_MESSAGES, ids=_ids(ALL_MESSAGES))
def test_catalog_length_agrees_with_length_table(message):
    assert message.payload_length == get_expected_message_length(
        message.category, message.msg_id
    )


@pytest.mark.parametrize("message", ALL_MESSAGES, ids=_ids(ALL_MESSAGES))
def test_is_long_flag_matches_unican_short_message_limit(message):
    """UniCAN short messages carry at most 6 payload bytes; anything longer must be long."""
    assert message.is_long == (message.payload_length > 6)


def test_length_table_has_no_entries_missing_from_catalog():
    catalog_keys = {(m.category, m.msg_id) for m in ALL_MESSAGES}
    assert set(EXPECTED_MESSAGE_LENGTHS) == catalog_keys


@pytest.fixture(scope="module")
def editor_registry(qapp):
    """Payload editors are QWidgets, so a QApplication must exist first."""
    return build_payload_editor_registry()


@pytest.mark.parametrize("message", SENDABLE, ids=_ids(SENDABLE))
def test_every_sendable_message_has_a_payload_editor(message, editor_registry):
    assert (message.category, message.msg_id) in editor_registry


def test_payload_editor_registry_has_no_unknown_messages(editor_registry):
    catalog_keys = {(m.category, m.msg_id) for m in ALL_MESSAGES}
    assert set(editor_registry) <= catalog_keys


@pytest.mark.parametrize("message", SENDABLE, ids=_ids(SENDABLE))
def test_every_sendable_message_has_send_defaults(message):
    assert get_send_defaults(message.category, message.msg_id) is not None


@pytest.mark.parametrize(
    "message",
    [m for m in ALL_MESSAGES if m.category == "KU"],
    ids=_ids([m for m in ALL_MESSAGES if m.category == "KU"]),
)
def test_every_control_command_declares_expected_responses(message):
    """Every КУ/CC gets at least an acknowledgement (ТС «Квитанция», 0201h)."""
    responses = get_expected_responses(message.category, message.msg_id)
    assert responses, "no expected responses declared"
    assert any(r.is_ack and r.msg_id == TM_ACK for r in responses)


@pytest.mark.parametrize(
    "message",
    [m for m in ALL_MESSAGES if m.category == "KU"],
    ids=_ids([m for m in ALL_MESSAGES if m.category == "KU"]),
)
def test_every_control_command_appears_in_the_mode_matrix(message):
    allowed_anywhere = set().union(*ALLOWED_KU_BY_MODE.values())
    assert message.msg_id in allowed_anywhere


def test_mode_matrix_has_no_commands_missing_from_catalog():
    known = {m.msg_id for m in ALL_MESSAGES if m.category == "KU"}
    assert set().union(*ALLOWED_KU_BY_MODE.values()) <= known


@pytest.mark.parametrize(
    "message",
    [m for m in ALL_MESSAGES if m.category == "TS"],
    ids=_ids([m for m in ALL_MESSAGES if m.category == "TS"]),
)
def test_telemetry_messages_are_referenced_by_some_command(message):
    """Every ТС/TM the tool knows about should be reachable as a response to some КУ/CC."""
    referenced = {
        (r.category, r.msg_id)
        for m in ALL_MESSAGES
        if m.category == "KU"
        for r in get_expected_responses(m.category, m.msg_id)
    }
    assert (message.category, message.msg_id) in referenced
