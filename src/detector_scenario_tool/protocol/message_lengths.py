"""Expected content lengths, derived from the message definitions.

Kept as a module so existing call sites keep working, but there is no separate table to maintain
any more — a length now lives in exactly one place, `MessageDef.length`.
"""

from __future__ import annotations

from detector_scenario_tool.protocol import registry


def get_expected_message_length(category: str, msg_id: int) -> int | None:
    spec = registry.find(category, msg_id)
    return None if spec is None else spec.length


def is_long_message(category: str, msg_id: int) -> bool | None:
    spec = registry.find(category, msg_id)
    return None if spec is None else spec.is_long


class _LengthTable:
    """Mapping-shaped view kept for callers that iterated the old dict."""

    def _mapping(self) -> dict[tuple[str, int], int]:
        return {(s.category, s.msg_id): s.length for s in registry.all_messages()}

    def __getitem__(self, key: tuple[str, int]) -> int:
        return self._mapping()[key]

    def get(self, key: tuple[str, int], default=None):
        return self._mapping().get(key, default)

    def __contains__(self, key: object) -> bool:
        return key in self._mapping()

    def __iter__(self):
        return iter(self._mapping())

    def __len__(self) -> int:
        return len(self._mapping())

    def items(self):
        return self._mapping().items()

    def keys(self):
        return self._mapping().keys()

    def values(self):
        return self._mapping().values()

    def __eq__(self, other: object) -> bool:
        return self._mapping() == other


EXPECTED_MESSAGE_LENGTHS = _LengthTable()
