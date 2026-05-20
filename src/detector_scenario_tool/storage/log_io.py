from __future__ import annotations

import json
from pathlib import Path

from detector_scenario_tool.domain.logs import LogRecord


class LogLoadError(ValueError):
    pass


def load_log_records(path: str | Path) -> list[LogRecord]:
    text = Path(path).read_text(encoding="utf-8").strip()

    if not text:
        return []

    if text.startswith("["):
        return _load_json_records(text)

    return parse_log_text(text)


def parse_log_text(text: str) -> list[LogRecord]:
    result: list[LogRecord] = []

    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        record = parse_log_line(raw_line, line_no=line_no)
        if record is not None:
            result.append(record)

    return result


def parse_log_line(raw_line: str, line_no: int = 1) -> LogRecord | None:
    line = raw_line.strip()
    if not line:
        return None

    if not line.startswith("DSTLOG|"):
        return None

    parts = line.split("|")
    if len(parts) < 7:
        raise LogLoadError(f"Line {line_no}: not enough fields.")

    if parts[0] != "DSTLOG":
        raise LogLoadError(f"Line {line_no}: invalid prefix.")

    fields: dict[str, str] = {}
    for part in parts[1:]:
        if "=" not in part:
            raise LogLoadError(f"Line {line_no}: invalid field '{part}'.")
        key, value = part.split("=", 1)
        fields[key.strip()] = value.strip()

    version = fields.get("v")
    if version != "1":
        raise LogLoadError(f"Line {line_no}: unsupported log version '{version}'.")

    source = fields.get("src", "")
    ts_text = fields.get("ts")
    direction = fields.get("dir", "").lower()
    msg_id_text = fields.get("id", "")
    data_text = fields.get("data", "")

    if ts_text is None:
        raise LogLoadError(f"Line {line_no}: missing ts field.")
    try:
        timestamp_ms = int(ts_text)
    except ValueError as exc:
        raise LogLoadError(f"Line {line_no}: invalid ts value.") from exc

    if direction not in ("tx", "rx"):
        raise LogLoadError(f"Line {line_no}: dir must be tx or rx.")

    try:
        msg_id = int(msg_id_text, 16)
    except ValueError as exc:
        raise LogLoadError(f"Line {line_no}: invalid hex id value.") from exc

    category = _category_from_msg_id(msg_id, line_no)
    payload = _parse_compact_hex(data_text, line_no)

    return LogRecord(
        timestamp_ms=timestamp_ms,
        direction=direction,
        category=category,
        msg_id=msg_id,
        payload=payload,
        source=source,
        note="",
    )


def _load_json_records(text: str) -> list[LogRecord]:
    raw = json.loads(text)

    if not isinstance(raw, list):
        raise LogLoadError("Log file must contain a JSON array.")

    result: list[LogRecord] = []

    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise LogLoadError(f"Log record #{i} must be an object.")

        timestamp_ms = _read_int(item, "timestamp_ms", default=0)
        direction = str(item.get("direction", "")).strip().lower()
        category = str(item.get("category", "")).strip().upper()
        msg_id = _read_int(item, "msg_id")
        source = str(item.get("source", "")).strip()
        note = str(item.get("note", ""))

        if direction not in ("tx", "rx"):
            raise LogLoadError(f"Record #{i}: direction must be 'tx' or 'rx'.")

        if category not in ("KU", "KT", "TS"):
            raise LogLoadError(f"Record #{i}: category must be KU, KT, or TS.")

        payload = _read_payload(item, i)

        result.append(
            LogRecord(
                timestamp_ms=timestamp_ms,
                direction=direction,
                category=category,
                msg_id=msg_id,
                payload=payload,
                source=source,
                note=note,
            )
        )

    return result


def _category_from_msg_id(msg_id: int, line_no: int) -> str:
    if 0x0000 <= msg_id <= 0x00FF:
        return "KU"
    if 0x0100 <= msg_id <= 0x01FF:
        return "KT"
    if 0x0200 <= msg_id <= 0x02FF:
        return "TS"

    raise LogLoadError(
        f"Line {line_no}: msg id 0x{msg_id:04X} does not belong to KU/KT/TS ranges."
    )


def _read_int(item: dict, key: str, default=None) -> int:
    if key not in item:
        if default is None:
            raise LogLoadError(f"Missing required field: {key}")
        return default

    value = item[key]
    if not isinstance(value, int):
        raise LogLoadError(f"Field {key!r} must be int.")
    return value


def _read_payload(item: dict, index: int) -> bytes:
    if "payload_hex" in item:
        return _parse_payload_hex(str(item["payload_hex"]), index)

    if "payload_bytes" in item:
        return _parse_payload_bytes(item["payload_bytes"], index)

    if "bytes" in item:
        return _parse_payload_bytes(item["bytes"], index)

    return b""


def _parse_payload_hex(value: str, index: int) -> bytes:
    text = value.strip()
    if not text:
        return b""

    normalized = text.replace(",", " ").replace("0x", "").replace("0X", "")
    parts = [part for part in normalized.split() if part]
    try:
        data = bytes(int(part, 16) for part in parts)
    except ValueError as exc:
        raise LogLoadError(f"Record #{index}: invalid payload_hex.") from exc

    return data


def _parse_payload_bytes(value, index: int) -> bytes:
    if not isinstance(value, list):
        raise LogLoadError(f"Record #{index}: payload byte list must be a JSON array.")

    result = []
    for b in value:
        if not isinstance(b, int) or not (0 <= b <= 255):
            raise LogLoadError(f"Record #{index}: payload bytes must be ints in range 0..255.")
        result.append(b)

    return bytes(result)


def _parse_compact_hex(value: str, line_no: int) -> bytes:
    text = value.strip()
    if not text:
        return b""

    if len(text) % 2 != 0:
        raise LogLoadError(f"Line {line_no}: data hex must contain even number of digits.")

    try:
        return bytes.fromhex(text)
    except ValueError as exc:
        raise LogLoadError(f"Line {line_no}: invalid data hex.") from exc


def format_log_record_line(record: LogRecord) -> str:
    return (
        f"DSTLOG|v=1|src={record.source}|ts={record.timestamp_ms}|"
        f"dir={record.direction}|id={record.msg_id:04X}|data={record.payload.hex().upper()}"
    )
