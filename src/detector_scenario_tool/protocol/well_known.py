"""The handful of messages the application reasons about by name rather than by number.

An acknowledgement has to be recognised by the runner, the analyzer, the simulator and two panels.
Until v2.1 each of them spelled it `0x0201`, so renumbering the catalogue meant hunting nine literals
through five layers — and the specification has now renumbered twice.

`MessageDef.symbol` is ours and never changes; `msg_id` is the specification's and does. So every
such site asks here, and the next renumbering is a one-line edit in `protocol/definitions/`.

Resolution is deliberately **lazy**: the registry is mutable at runtime (a scenario may hide or
replace a catalogue message, see `services/custom_message_sync.py`), so caching an identifier at
import would go stale. Looking it up costs a dict hit.
"""

from __future__ import annotations

from detector_scenario_tool.protocol import registry
from detector_scenario_tool.protocol.fields import MessageDef

# Symbols, not numbers. These are the names used in `protocol/definitions/`.
ACK = "TM_ACK"
STATUS = "TM_STATUS"
TELEMETRY = "TM_TELEMETRY"
TEST_RESULT = "TM_TEST_RESULT"
VERSION = "TM_VERSION"

SET_DEST_ID = "CMD_SET_DEST_ID"
SET_DEVICE_ID = "CMD_SET_DEVICE_ID"


def definition(symbol: str) -> MessageDef | None:
    """The current definition for a symbol, or None if the document has hidden it."""
    return registry.by_symbol(symbol)


def msg_id(symbol: str) -> int | None:
    """The identifier a symbol currently carries."""
    spec = registry.by_symbol(symbol)
    return None if spec is None else spec.msg_id


def is_(symbol: str, category: str, message_id: int | None) -> bool:
    """Whether `(category, message_id)` is the message known as `symbol`.

    Returns False rather than raising when the symbol is not registered, so a scenario that hid a
    catalogue message degrades to "this is not an acknowledgement" instead of crashing the runner.
    """
    if message_id is None:
        return False
    spec = registry.by_symbol(symbol)
    return spec is not None and spec.category == category and spec.msg_id == message_id


def is_ack(category: str, message_id: int | None) -> bool:
    return is_(ACK, category, message_id)


def is_status(category: str, message_id: int | None) -> bool:
    return is_(STATUS, category, message_id)


def is_telemetry(category: str, message_id: int | None) -> bool:
    return is_(TELEMETRY, category, message_id)


def is_address_command(category: str, message_id: int | None) -> str | None:
    """Which address a control command changes, if any: `SET_DEST_ID` / `SET_DEVICE_ID` / None."""
    for symbol in (SET_DEST_ID, SET_DEVICE_ID):
        if is_(symbol, category, message_id):
            return symbol
    return None
