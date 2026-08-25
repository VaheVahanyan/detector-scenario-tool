"""Migration of scenario files written against an earlier revision of the protocol.

Two upgrades live here, and they are deliberately different in character.

**v1 → v2** could not be done safely. `KT 0100h` meant «Сверка времени» at 6 bytes in the old
tables and `TLM_MCILWAIN` at 24 bytes in v2 — same number, different message. Reinterpreting it
would turn a valid old scenario into a plausible-looking wrong one, so such steps are
**quarantined**: the original JSON is preserved on a disabled comment step and the user re-enters
it by hand.

**v2 → v3** can. `Протокол_CAN_ГС_v2_1_Спутникс` renumbered the whole catalogue, but it is a pure
relabelling: КУ 1-13 moved by a flat +0F00h, `KT 0100h` became `0E00h`, ТС moved from `0200h…0203h`
to `0D00h…0D03h`, and the contents did not change. No identifier acquired a *different* meaning, so
the mapping below is exact rather than a guess, and quarantining would only destroy work.

The one place v2 → v3 does more than relabel is the initial RTC — see `_migrate_initial_rtc`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

CURRENT_SCHEMA_VERSION = 3

#: Stamped into every saved document, so a file says which protocol revision it was authored
#: against. Lives here rather than in `scenario_io` because the migrations are what interpret it.
PROTOCOL_VERSION = "CAN_v2_1"

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

#: CMD_SET_CFG grew from 64 to 66 bytes in v2; the two new fields have no counterpart in v1 files.
_SET_CFG_NEW_FIELDS = ("can_reply_address_source", "bvs_time_reaction")

#: v2 identifier -> v2.1 identifier, per category. Every v2 message appears exactly once: a message
#: that kept its number (0401h, 0A61h, 0A62h, F210h, F221h) is simply absent from the table.
_V2_TO_V2_1: dict[str, dict[int, int]] = {
    "KU": {old: old + 0x0F00 for old in range(0x0000, 0x000D)},
    "KT": {0x0100: 0x0E00},
    "TS": {0x0200: 0x0D00, 0x0201: 0x0D01, 0x0202: 0x0D02, 0x0203: 0x0D03},
}

#: v2 payload key -> v2.1 key, for the fields v2.1 split or renamed.
_V2_FIELD_RENAMES: dict[str, str] = {
    # v2 had one bare u32 «Начальное приборное время RTC»; v2.1 puts a milliseconds word in front
    # of it and keeps the seconds as a u32, so the old value is the seconds half by position.
    "initial_rtc": "initial_rtc_s",
    "rtc": "rtc_s",
    # §2.14 renamed the command itself from «от «Спутникс»» to «от БВС».
    "sputniks_time_reaction": "bvs_time_reaction",
}


@dataclass
class MigrationNote:
    code: str
    step_index: int | None = None
    params: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.params is None:
            self.params = {}


def migrate_document(raw: dict) -> tuple[dict, list[MigrationNote]]:
    """Bring a loaded document up to the current schema. Returns (data, notes).

    The upgrades chain, so a v1 file goes through v2 on its way to v3 and picks up the notes from
    both. Doing it in one step would mean maintaining a v1 → v3 path that nothing exercises.
    """
    version = raw.get("schema_version", 1)
    if version >= CURRENT_SCHEMA_VERSION:
        return raw, []

    data = raw
    notes: list[MigrationNote] = []

    if version < 2:
        data, step_notes = _migrate_v1_to_v2(data)
        notes.extend(step_notes)

    data, step_notes = _migrate_v2_to_v3(data)
    notes.extend(step_notes)

    return data, notes


def _migrate_v1_to_v2(raw: dict) -> tuple[dict, list[MigrationNote]]:
    notes: list[MigrationNote] = []
    steps: list[dict] = []

    for index, item in enumerate(raw.get("steps", [])):
        migrated = _migrate_step(item, index, notes)
        steps.append(migrated)

    data = dict(raw)
    data["steps"] = steps
    data["schema_version"] = 2
    data["protocol_version"] = "CAN_v2"

    notes.insert(0, MigrationNote("migration.upgraded", None, {"from": 1, "to": 2}))
    return data, notes


def _migrate_v2_to_v3(raw: dict) -> tuple[dict, list[MigrationNote]]:
    """Renumber a v2 document onto `Протокол_CAN_ГС_v2_1_Спутникс`.

    Safe to do silently, unlike v1 → v2: no identifier changed meaning, only its number.
    """
    notes: list[MigrationNote] = []
    steps: list[dict] = []
    renumbered = 0

    for index, item in enumerate(raw.get("steps", [])):
        item = dict(item)

        for key in ("message", "expected"):
            ref = item.get(key)
            if isinstance(ref, dict) and _renumber_ref(ref):
                renumbered += 1

        if isinstance(item.get("payload"), dict):
            item["payload"] = _migrate_v2_payload(item["payload"], index, notes)

        steps.append(item)

    for record in raw.get("custom_messages", []) or []:
        # A user-defined message may now collide with a catalogue identifier that did not exist
        # before — 0F01h, for instance, was free in v2 and is CMD_STATUS_REQ in v2.1.
        if isinstance(record, dict):
            _note_custom_collision(record, notes)

    data = dict(raw)
    data["steps"] = steps
    data["schema_version"] = CURRENT_SCHEMA_VERSION
    data["protocol_version"] = PROTOCOL_VERSION

    notes.insert(
        0, MigrationNote("migration.renumbered_v2_1", None, {"count": renumbered})
    )
    return data, notes


def _renumber_ref(ref: dict) -> bool:
    table = _V2_TO_V2_1.get(ref.get("category", ""))
    if table is None:
        return False
    new_id = table.get(ref.get("msg_id"))
    if new_id is None:
        return False
    ref["msg_id"] = new_id
    # The stored name is only a fallback; `utils/labels.message_label` reads the catalogue. Drop it
    # so a renumbered step cannot show a name from a revision that no longer exists.
    ref["name"] = ""
    return True


def _migrate_v2_payload(payload: dict, index: int, notes: list[MigrationNote]) -> dict:
    migrated = {}
    for key, value in payload.items():
        migrated[_V2_FIELD_RENAMES.get(key, key)] = value

    if "initial_rtc" in payload:
        migrated.setdefault("initial_rtc_ms", 0)
        notes.append(MigrationNote("migration.rtc_split", index, {"field": "initial_rtc"}))
    if "rtc" in payload:
        migrated.setdefault("rtc_ms", 0)
        notes.append(MigrationNote("migration.rtc_split", index, {"field": "rtc"}))

    return migrated


def _note_custom_collision(record: dict, notes: list[MigrationNote]) -> None:
    from detector_scenario_tool.protocol import registry

    category = record.get("category", "KU")
    msg_id = record.get("msg_id")
    if not isinstance(msg_id, int):
        return
    if record.get("overrides_builtin"):
        return

    spec = registry.find(category, msg_id)
    if spec is not None and not spec.custom:
        notes.append(
            MigrationNote(
                "migration.custom_now_collides",
                None,
                {"msg": f"0x{msg_id:04X}", "symbol": spec.symbol},
            )
        )


def _migrate_step(item: dict, index: int, notes: list[MigrationNote]) -> dict:
    item = dict(item)
    kind = item.get("kind")

    if kind == "send_kt":
        return _quarantine_telemetry_command(item, index, notes)

    if kind in ("send_ku", "send_kt"):
        item["payload"] = _migrate_payload(item.get("payload", {}))

    if kind == "send_ku":
        message = item.get("message") or {}
        if message.get("msg_id") == 0x0007:  # v1/v2 CMD_SET_CFG
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
