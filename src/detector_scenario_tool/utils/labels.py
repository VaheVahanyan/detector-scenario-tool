"""Display names for message categories.

`KU` / `KT` / `TS` are transliterated Russian abbreviations. They stay as the internal codes —
they appear in saved scenarios, in the `DSTLOG` log format and in generated C, so renaming them
would break files for no benefit — but they are never shown to the user directly. Everything the
user sees goes through here:

| code | Russian | meaning                    | English | meaning            |
|------|---------|----------------------------|---------|--------------------|
| `KU` | КУ      | команда управления         | CC      | control command    |
| `KT` | КТ      | команда телеметрии         | TC      | telemetry command  |
| `TS` | ТС      | телеметрическое сообщение  | TM      | telemetry message  |

The English forms are *not* KU/KT/TS: those are meaningless outside Russian.

`LOG` is deliberately **not** one of `CATEGORY_CODES`: it is not a protocol category, so it must
never be offered as one (a user-defined message cannot be a log, and the catalogue holds none).
It only ever labels a captured `LogRecord`, so the log panel builds its filter from
`LOG_RECORD_CATEGORY_CODES` instead.
"""

from __future__ import annotations

from detector_scenario_tool.domain.logs import LOG_CATEGORY
from detector_scenario_tool.i18n import tr

CATEGORY_CODES: tuple[str, ...] = ("KU", "KT", "TS")

#: What a captured record's category may say — the protocol categories plus the board's own output.
LOG_RECORD_CATEGORY_CODES: tuple[str, ...] = CATEGORY_CODES + (LOG_CATEGORY,)


def category_short(code: str) -> str:
    """Abbreviation for tables, buttons and timeline labels: КУ / CC."""
    if code not in LOG_RECORD_CATEGORY_CODES:
        return code
    return tr(f"category.{code}.short")


def category_long(code: str) -> str:
    """Spelled-out name for tooltips and prose: команда управления / control command."""
    if code not in LOG_RECORD_CATEGORY_CODES:
        return code
    return tr(f"category.{code}.long")


def message_code(category: str, msg_id: int) -> str:
    """`КУ 0x0003` — the identifier alone, for places where the full name will not fit."""
    return f"{category_short(category)} 0x{msg_id:04X}"


def message_label(category: str, msg_id: int, name: str = "") -> str:
    """`КУ 0x0003 Включение режима наблюдений`, the standard way to name a message.

    The name is resolved from the catalogue so it follows the language switch. `name` is only a
    fallback, used for messages the catalogue does not know (a stale file, or a user-defined
    command).
    """
    from detector_scenario_tool.protocol import registry

    spec = registry.find(category, msg_id)
    if spec is None:
        resolved = name
    else:
        resolved = spec.custom_name or tr(spec.name_key)

    head = message_code(category, msg_id)
    return f"{head} {resolved}" if resolved else head


def message_label_from_ref(ref) -> str:
    """Same, from a `MessageRef`; falls back gracefully on an incomplete reference."""
    if ref is None or ref.msg_id is None:
        return tr("label.no_message")
    return message_label(ref.category, ref.msg_id, ref.name)
