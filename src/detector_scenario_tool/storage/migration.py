"""Migration of scenario files written against the pre-v2 protocol.

The dangerous case is `KT 0100h`: in the old tables it meant «Сверка времени» and was 6 bytes long,
in `Протокол_CAN_ГС_v2` it is `TLM_MCILWAIN` and is 24 bytes long. Reinterpreting it silently would
turn a valid old scenario into a plausible-looking wrong one, so such steps are **quarantined**:
the original JSON is preserved on a comment step and the user is told to re-enter it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

CURRENT_SCHEMA_VERSION = 2

#: Telemetry commands as they were numbered before Протокол_CAN_ГС_v2. Every one of these either
#: disappeared or changed meaning, so none can be carried over automatically.
PRE_V2_TELEMETRY_COMMANDS: dict[int, str] = {
    0x0100: "Сверка времени",
    0x0101: "Параметры орбиты",
    0x0102: "Параметры ориентации",
    0x0103: "Геомагнитное поле",
}

#: Bank selectors used to be stored as strings.
_BANK_VALUES: dict[str, int] = {"nand1": 1, "nand2": 2, "mram1": 1, "mram2": 2}

#: Enumerations that used to be stored as strings, keyed by payload field.
_STRING_ENUMS: dict[str, dict[str, int]] = {
    "selected_nand_bank": _BANK_VALUES,
    "selected_mram_bank": _BANK_VALUES,
    "output_interface": {"usb": 0, "can": 1},
    "output_type": {"requested_count": 0, "accumulated": 1},
}

#: CMD_SET_CFG grew from 64 to 66 bytes; the two new fields have no counterpart in old files.
_SET_CFG_NEW_FIELDS = ("can_reply_address_source", "sputniks_time_reaction")


@dataclass
class MigrationNote:
    code: str
    step_index: int | None = None
    params: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.params is None:
            self.params = {}


def migrate_document(raw: dict) -> tuple[dict, list[MigrationNote]]:
    """Bring a loaded document up to the current schema. Returns (data, notes)."""
    version = raw.get("schema_version", 1)
    if version >= CURRENT_SCHEMA_VERSION:
        return raw, []

    notes: list[MigrationNote] = []
    steps: list[dict] = []

    for index, item in enumerate(raw.get("steps", [])):
        migrated = _migrate_step(item, index, notes)
        steps.append(migrated)

    data = dict(raw)
    data["steps"] = steps
    data["schema_version"] = CURRENT_SCHEMA_VERSION
    data["protocol_version"] = "CAN_v2"

    notes.insert(0, MigrationNote("migration.upgraded", None, {"from": version,
                                                              "to": CURRENT_SCHEMA_VERSION}))
    return data, notes


def _migrate_step(item: dict, index: int, notes: list[MigrationNote]) -> dict:
    item = dict(item)
    kind = item.get("kind")

    if kind == "send_kt":
        return _quarantine_telemetry_command(item, index, notes)

    if kind in ("send_ku", "send_kt"):
        item["payload"] = _migrate_payload(item.get("payload", {}))

    if kind == "send_ku":
        message = item.get("message") or {}
        if message.get("msg_id") == 0x0007:
            notes.append(
                MigrationNote("migration.set_cfg_extended", index,
                              {"fields": ", ".join(_SET_CFG_NEW_FIELDS)})
            )

    if kind == "wait_for_ts":
        item["expected"] = item.get("expected")

    return item


def _quarantine_telemetry_command(item: dict, index: int, notes: list[MigrationNote]) -> dict:
    """Turn a pre-v2 КТ step into a comment that preserves the original JSON verbatim."""
    message = item.get("message") or {}
    msg_id = message.get("msg_id")
    old_name = PRE_V2_TELEMETRY_COMMANDS.get(msg_id, message.get("name", ""))

    notes.append(
        MigrationNote(
            "migration.telemetry_command_quarantined",
            index,
            {
                "msg": f"0x{msg_id:04X}" if isinstance(msg_id, int) else "?",
                "old_name": old_name,
            },
        )
    )

    preserved = json_compact(item)
    return {
        "id": item.get("id", f"migrated-{index}"),
        "kind": "comment",
        "title": item.get("title", "") or old_name,
        "comment": item.get("comment", ""),
        "enabled": False,
        "text": preserved,
        "migrated_from": item,
    }


def _migrate_payload(payload: dict) -> dict:
    migrated: dict[str, Any] = {}

    for key, value in payload.items():
        mapping = _STRING_ENUMS.get(key)
        if mapping is not None and isinstance(value, str):
            migrated[key] = mapping.get(value, value)
        elif isinstance(value, bool):
            # Bit fields are stored as integers now.
            migrated[key] = int(value)
        else:
            migrated[key] = value

    return migrated


def json_compact(item: dict) -> str:
    import json

    return json.dumps(item, ensure_ascii=False, sort_keys=True)
