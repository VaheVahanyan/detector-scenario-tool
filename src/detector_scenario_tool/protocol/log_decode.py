from __future__ import annotations

from detector_scenario_tool.domain.logs import LogRecord


def build_log_summary(record: LogRecord) -> str:
    try:
        if record.category == "KU":
            return _decode_ku_summary(record)
        if record.category == "KT":
            return _decode_kt_summary(record)
        if record.category == "TS":
            return _decode_ts_summary(record)
    except Exception:
        pass

    if record.payload:
        return f"{len(record.payload)} bytes"
    return "No payload"


def _decode_ku_summary(record: LogRecord) -> str:
    payload = record.payload
    msg_id = record.msg_id

    if msg_id == 0x0000:
        return "Telemetry request"

    if msg_id == 0x0001:
        return "Status request"

    if msg_id == 0x0002 and len(payload) >= 6:
        time_ms = int.from_bytes(payload[0:2], "little", signed=False)
        time_s = int.from_bytes(payload[2:6], "little", signed=False)
        return f"time={time_s}s + {time_ms}ms"

    if msg_id == 0x0003 and len(payload) >= 1:
        b = payload[0]
        return (
            f"bank={_bank_name(b)}, "
            f"nand_power={_bit_bool(b, 2)}, "
            f"ped_power={_bit_bool(b, 3)}, "
            f"low_power={_bit_bool(b, 4)}"
        )

    if msg_id == 0x0004 and len(payload) >= 6:
        return f"control payload: {record.payload_hex}"

    if msg_id == 0x0005 and len(payload) >= 1:
        b = payload[0]
        return (
            f"bank={_bank_name(b)}, "
            f"nand_power={_bit_bool(b, 2)}, "
            f"ped_power={_bit_bool(b, 3)}, "
            f"low_power={_bit_bool(b, 4)}"
        )

    if msg_id == 0x0006 and len(payload) >= 6:
        return f"data output payload: {record.payload_hex}"

    if msg_id == 0x0007 and len(payload) >= 6:
        return f"settings payload: {record.payload_hex}"

    if msg_id == 0x0008 and len(payload) >= 1:
        b = payload[0]
        return f"erase { _bank_name(b) }, keep_power={_bit_bool(b, 2)}"

    if msg_id == 0x0009 and len(payload) >= 1:
        b = payload[0]
        return f"test { _bank_name(b) }, keep_power={_bit_bool(b, 2)}"

    if msg_id == 0x000A and len(payload) >= 1:
        b = payload[0]
        return f"request results for { _bank_name(b) }"

    if msg_id == 0x000B:
        return "Power off"

    if msg_id == 0x000C:
        return "Reset emergency status"

    return _fallback_payload_summary(record)


def _decode_kt_summary(record: LogRecord) -> str:
    payload = record.payload
    msg_id = record.msg_id

    if msg_id == 0x0100 and len(payload) >= 6:
        time_ms = int.from_bytes(payload[0:2], "little", signed=False)
        time_s = int.from_bytes(payload[2:6], "little", signed=False)
        return f"sync time={time_s}s + {time_ms}ms"

    if msg_id == 0x0101 and len(payload) >= 20:
        time_ms = int.from_bytes(payload[0:2], "little", signed=False)
        time_s = int.from_bytes(payload[2:6], "little", signed=False)
        x = int.from_bytes(payload[6:10], "little", signed=True)
        y = int.from_bytes(payload[10:14], "little", signed=True)
        z = int.from_bytes(payload[14:18], "little", signed=True)
        return f"t={time_s}.{time_ms}, r=({x}, {y}, {z})"

    if msg_id == 0x0102 and len(payload) >= 22:
        time_ms = int.from_bytes(payload[0:2], "little", signed=False)
        time_s = int.from_bytes(payload[2:6], "little", signed=False)
        q0 = int.from_bytes(payload[6:10], "little", signed=True)
        q1 = int.from_bytes(payload[10:14], "little", signed=True)
        q2 = int.from_bytes(payload[14:18], "little", signed=True)
        q3 = int.from_bytes(payload[18:22], "little", signed=True)
        return f"t={time_s}.{time_ms}, q=({q0}, {q1}, {q2}, {q3})"

    if msg_id == 0x0103 and len(payload) >= 18:
        time_ms = int.from_bytes(payload[0:2], "little", signed=False)
        time_s = int.from_bytes(payload[2:6], "little", signed=False)
        bx = int.from_bytes(payload[6:10], "little", signed=True)
        by = int.from_bytes(payload[10:14], "little", signed=True)
        bz = int.from_bytes(payload[14:18], "little", signed=True)
        return f"t={time_s}.{time_ms}, B=({bx}, {by}, {bz})"

    return _fallback_payload_summary(record)


def _decode_ts_summary(record: LogRecord) -> str:
    payload = record.payload
    msg_id = record.msg_id

    if msg_id == 0x0200:
        if payload:
            return f"status payload: {record.payload_hex}"
        return "Status"

    if msg_id == 0x0201:
        if payload:
            return f"ack payload: {record.payload_hex}"
        return "Ack"

    if msg_id == 0x0202:
        if payload:
            return f"telemetry payload: {len(payload)} bytes"
        return "Telemetry"

    if msg_id == 0x0203:
        if payload:
            return f"data payload: {len(payload)} bytes"
        return "Data"

    return _fallback_payload_summary(record)


def _fallback_payload_summary(record: LogRecord) -> str:
    if record.payload:
        return f"{len(record.payload)} bytes"
    return "No payload"


def _bit_bool(byte_value: int, bit_index: int) -> bool:
    return bool((byte_value >> bit_index) & 0x1)


def _bank_name(byte_value: int) -> str:
    bank_bits = byte_value & 0x03
    if bank_bits == 0:
        return "nand1"
    if bank_bits == 1:
        return "nand2"
    return f"bank_bits={bank_bits}"