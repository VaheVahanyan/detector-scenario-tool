"""Lookup for message definitions, plus registration of user-defined messages at runtime.

`register` exists so the manual command builder (upgrade plan phase 7) can add a message the
catalogue has never seen and have packing, validation and log decoding work on it unchanged.
"""

from __future__ import annotations

from detector_scenario_tool.protocol.definitions import ALL_MESSAGE_DEFS
from detector_scenario_tool.protocol.fields import MessageDef

_BY_KEY: dict[tuple[str, int], MessageDef] = {}
_BY_SYMBOL: dict[str, MessageDef] = {}
_ORDER: list[tuple[str, int]] = []


def register(spec: MessageDef, replace: bool = False) -> None:
    key = (spec.category, spec.msg_id)
    if key in _BY_KEY and not replace:
        raise ValueError(
            f"{spec.category} 0x{spec.msg_id:04X} is already registered "
            f"as {_BY_KEY[key].symbol}"
        )
    if key not in _BY_KEY:
        _ORDER.append(key)
    _BY_KEY[key] = spec
    _BY_SYMBOL[spec.symbol] = spec


def unregister(category: str, msg_id: int) -> None:
    key = (category, msg_id)
    spec = _BY_KEY.pop(key, None)
    if spec is None:
        return
    _BY_SYMBOL.pop(spec.symbol, None)
    _ORDER.remove(key)


def find(category: str, msg_id: int) -> MessageDef | None:
    return _BY_KEY.get((category, msg_id))


def by_symbol(symbol: str) -> MessageDef | None:
    return _BY_SYMBOL.get(symbol)


def all_messages() -> list[MessageDef]:
    return [_BY_KEY[key] for key in _ORDER]


def by_category(category: str) -> list[MessageDef]:
    return [spec for spec in all_messages() if spec.category == category]


def reset_to_builtin() -> None:
    """Drop runtime registrations; used by tests and when loading a different scenario."""
    _BY_KEY.clear()
    _BY_SYMBOL.clear()
    _ORDER.clear()
    for spec in ALL_MESSAGE_DEFS:
        register(spec)


reset_to_builtin()
