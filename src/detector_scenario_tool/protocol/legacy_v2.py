"""Identifiers from `Протокол_CAN_ГС_v2`, kept for recognition — never for support.

The tool speaks v2.1 and only v2.1 (question C2 in the upgrade plan): a v2 number is not packed,
not validated, not matched against a step, and never satisfies a wait. But a board on the bench may
still be running v2 firmware, and then its answers arrive under the old numbers — `0201h` for the
acknowledgement rather than `0D01h`.

Without this table such an answer is indistinguishable from the debug text the МК prints onto the
same bus, and the log would show the single most useful fact on the bench — *the firmware is a
revision behind* — as an anonymous six-byte log line. So the numbers are recognised and named, and
nothing else about them changes.

`storage/migration.py` reads the same table to renumber saved scenarios; it lives here because the
history of the catalogue is a fact about the protocol, not about file formats.
"""

from __future__ import annotations

#: v2 identifier -> v2.1 identifier, per category. Every v2 message appears exactly once: a message
#: that kept its number (0401h, 0A61h, 0A62h, F210h, F221h) is simply absent from the table.
V2_TO_V2_1: dict[str, dict[int, int]] = {
    "KU": {old: old + 0x0F00 for old in range(0x0000, 0x000D)},
    "KT": {0x0100: 0x0E00},
    "TS": {0x0200: 0x0D00, 0x0201: 0x0D01, 0x0202: 0x0D02, 0x0203: 0x0D03},
}

#: Searched in this order. Anything arriving from the payload is a ТС first and foremost.
_SEARCH_ORDER = ("TS", "KT", "KU")


def current_id(category: str, msg_id: int) -> int | None:
    """The v2.1 identifier a v2 one became, or None if it is not a v2 number that moved."""
    return V2_TO_V2_1.get(category, {}).get(msg_id)


def recognise(msg_id: int) -> tuple[str, int] | None:
    """`(category, current identifier)` for a number the specification has since moved.

    Only ever consulted for identifiers the current catalogue does not hold, so the search order
    cannot mask a live message: no v2 number that moved is in use in v2.1.
    """
    for category in _SEARCH_ORDER:
        moved = V2_TO_V2_1[category].get(msg_id)
        if moved is not None:
            return category, moved
    return None
