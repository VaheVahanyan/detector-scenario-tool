from __future__ import annotations

import json
from pathlib import Path

from detector_scenario_tool.domain.logs import LOG_CATEGORY, LogRecord


#: Written by this version; older files are still accepted.
LOG_VERSION = "3"
SUPPORTED_LOG_VERSIONS = ("1", "2", "3")

#: What `cat=` may say. The three protocol categories, plus the board's own log output, which
#: is not a protocol message at all (see `domain/logs.LOG_CATEGORY`).
LOG_CATEGORIES = ("KU", "KT", "TS", LOG_CATEGORY)


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
    if version not in SUPPORTED_LOG_VERSIONS:
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

    category = _read_category(fields, msg_id, line_no)
    payload = _parse_compact_hex(data_text, line_no)

    # v=2 adds the wire detail. A v=1 line simply has none of it, and the defaults are right.
    can_id = _parse_optional_hex(fields.get("can"), line_no)
    frame_count = _parse_optional_int(fields.get("frames"), line_no) or 1
    valid = fields.get("valid", "1") not in ("0", "false", "no")

    return LogRecord(
        timestamp_ms=timestamp_ms,
        direction=direction,
        category=category,
        msg_id=msg_id,
        payload=payload,
        source=source,
        note="",
        can_id=can_id,
        frame_count=frame_count,
        valid=valid,
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

        if category not in LOG_CATEGORIES:
            raise LogLoadError(
                f"Record #{i}: category must be one of {', '.join(LOG_CATEGORIES)}."
            )

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


def _read_category(fields: dict[str, str], msg_id: int, line_no: int) -> str:
    """The category of a logged message: from the line if it says, otherwise from the catalogue.

    v=3 writes `cat=` because identifiers are no longer grouped by category at all. Until
    `Протокол_CAN_ГС_v2_1_Спутникс` they were (`0000…00FF` КУ, `0100…01FF` КТ, `0200…02FF` ТС) and
    this function guessed from the range; v2.1 scatters КУ across `0F00…0F0C`, `0401`, `0A61`,
    `0A62` and `FFE0`, so there is nothing left to guess from.

    `cat=LOG` is the one value that cannot be worked out from a catalogue at all: it marks text the
    board printed onto the bus under an identifier of its own, which is exactly why it has to be
    written down at capture time.
    """
    stated = fields.get("cat", "").strip().upper()
    if stated:
        if stated not in LOG_CATEGORIES:
            raise LogLoadError(
                f"Line {line_no}: cat must be one of {', '.join(LOG_CATEGORIES)}, "
                f"not '{stated}'."
            )
        return stated

    return _category_from_catalogue(msg_id, line_no)


def _category_from_catalogue(msg_id: int, line_no: int) -> str:
    """For a v=1/v=2 line, which carries no category. Only the catalogue can say."""
    from detector_scenario_tool.protocol import registry

    for category in ("KU", "KT", "TS"):
        if registry.find(category, msg_id) is not None:
            return category

    raise LogLoadError(
        f"Line {line_no}: msg id 0x{msg_id:04X} is not in the catalogue, and the line does not "
        f"say which category it belongs to. Re-record it, or add 'cat=' to the line."
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
    """Write the current format.

    v=2 added `can`, `frames` and `valid`; v=3 adds `cat`, without which a line can only be
    understood by looking its identifier up in whatever catalogue happens to be loaded. The extra
    fields are appended and the reader treats unknown ones as absent, so a v=3 line stays readable
    by anything that parsed v=1 loosely and older files still load here.
    """
    line = (
        f"DSTLOG|v={LOG_VERSION}|src={record.source}|ts={record.timestamp_ms}|"
        f"dir={record.direction}|cat={record.category}|id={record.msg_id:04X}|"
        f"data={record.payload.hex().upper()}"
    )
    if record.can_id is not None:
        line += f"|can={record.can_id:03X}"
    if record.frame_count != 1:
        line += f"|frames={record.frame_count}"
    if not record.valid:
        line += "|valid=0"
    return line


def _parse_optional_hex(value: str | None, line_no: int) -> int | None:
    if value is None or not value.strip():
        return None
    try:
        return int(value, 16)
    except ValueError as exc:
        raise LogLoadError(f"Line {line_no}: invalid hex can value.") from exc


def _parse_optional_int(value: str | None, line_no: int) -> int | None:
    if value is None or not value.strip():
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise LogLoadError(f"Line {line_no}: invalid frames value.") from exc
