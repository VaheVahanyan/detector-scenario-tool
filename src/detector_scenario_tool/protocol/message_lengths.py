from __future__ import annotations

EXPECTED_MESSAGE_LENGTHS: dict[tuple[str, int], int] = {
    ("KU", 0x0000): 6,
    ("KU", 0x0001): 6,
    ("KU", 0x0002): 6,
    ("KU", 0x0003): 6,
    ("KU", 0x0004): 6,
    ("KU", 0x0005): 6,
    ("KU", 0x0006): 6,
    ("KU", 0x0007): 64,
    ("KU", 0x0008): 6,
    ("KU", 0x0009): 6,
    ("KU", 0x000A): 6,
    ("KU", 0x000B): 6,
    ("KU", 0x000C): 6,

    ("KT", 0x0100): 6,
    ("KT", 0x0101): 34,
    ("KT", 0x0102): 22,
    ("KT", 0x0103): 18,

    ("TS", 0x0200): 6,
    ("TS", 0x0201): 6,
    ("TS", 0x0202): 96,
    ("TS", 0x0203): 6144,
}


def get_expected_message_length(category: str, msg_id: int) -> int | None:
    return EXPECTED_MESSAGE_LENGTHS.get((category, msg_id))
