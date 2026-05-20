from __future__ import annotations

import json
from pathlib import Path

from detector_scenario_tool.domain.scenario import SendMessageStep


class PackingError(ValueError):
    pass


def pack_send_message_step(step: SendMessageStep) -> bytes:
    if step.message is None or step.message.msg_id is None:
        raise PackingError("Cannot pack step without selected message.")

    return pack_message_payload(
        category=step.message.category,
        msg_id=step.message.msg_id,
        payload=step.payload,
    )


def pack_message_payload(category: str, msg_id: int, payload: dict) -> bytes:
    if category == "KU":
        return _pack_ku_message(msg_id, payload)

    if category == "KT":
        return _pack_kt_message(msg_id, payload)

    raise PackingError(f"Packing is implemented only for KU and KT right now, got {category=}.")


def _pack_ku_message(msg_id: int, payload: dict) -> bytes:
    if msg_id == 0x0000:
        return bytes([0xAA] * 6)

    if msg_id == 0x0001:
        return bytes([0xAA] * 6)

    if msg_id == 0x0002:
        return _pack_ku_0002(payload)

    if msg_id == 0x0003:
        return _pack_ku_0003(payload)

    if msg_id == 0x0004:
        return _pack_ku_0004(payload)

    if msg_id == 0x0005:
        return _pack_ku_0005(payload)

    if msg_id == 0x0006:
        return _pack_ku_0006(payload)

    if msg_id == 0x0007:
        return _pack_ku_0007(payload)

    if msg_id == 0x0008:
        return _pack_ku_0008(payload)

    if msg_id == 0x0009:
        return _pack_ku_0009(payload)

    if msg_id == 0x000A:
        return _pack_ku_000A(payload)

    if msg_id == 0x000B:
        return bytes([0xAA] * 6)

    if msg_id == 0x000C:
        return bytes([0xAA] * 6)

    raise PackingError(f"Packing for KU 0x{msg_id:04X} is not implemented yet.")


def _pack_kt_message(msg_id: int, payload: dict) -> bytes:
    if msg_id == 0x0100:
        return _pack_kt_0100(payload)

    if msg_id == 0x0101:
        return _pack_kt_0101(payload)

    if msg_id == 0x0102:
        return _pack_kt_0102(payload)

    if msg_id == 0x0103:
        return _pack_kt_0103(payload)

    raise PackingError(f"Packing for KT 0x{msg_id:04X} is not implemented yet.")


def payload_to_hex(payload_bytes: bytes) -> str:
    return " ".join(f"{b:02X}" for b in payload_bytes)


def save_payload_hex_dump(
        category: str,
        msg_id: int,
        payload: dict,
        path: str | Path,
) -> None:
    packed = pack_message_payload(category=category, msg_id=msg_id, payload=payload)
    data = {
        "category": category,
        "msg_id": msg_id,
        "packed_length": len(packed),
        "packed_hex": payload_to_hex(packed),
        "packed_bytes": list(packed),
    }
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _pack_ku_0002(payload: dict) -> bytes:
    board_time_ms = _require_int(payload, "board_time_ms", 0, 0xFFFF)
    board_time_s = _require_int(payload, "board_time_s", 0, 0xFFFFFFFF)

    return _u16_le(board_time_ms) + _u32_le(board_time_s)


def _pack_ku_0003(payload: dict) -> bytes:
    hw = 0
    bank = _require_bank_bits(payload.get("selected_nand_bank", "nand1"))
    hw |= bank
    hw |= _bit(2, _require_bool(payload, "ped_power_enabled", default=False))
    hw |= _bit(3, _require_bool(payload, "ped_low_power", default=False))
    hw |= _bit(4, _require_bool(payload, "ped_event_registration", default=False))
    hw |= _bit(5, _require_bool(payload, "keep_nand_power_after_overflow", default=False))
    hw |= _bit(6, _require_bool(payload, "keep_ped_power_after_overflow", default=False))
    hw |= _bit(7, _require_bool(payload, "keep_ped_low_power_after_overflow", default=False))

    obs_params = _pack_observation_params(payload, with_particle_threshold=True)
    trigger_config = _require_int(payload, "trigger_config", 0, 0xFFFF, default=0)

    return bytes([hw]) + _u16_le(obs_params) + _u16_le(trigger_config) + bytes([0xAA])


def _pack_ku_0004(payload: dict) -> bytes:
    hw = 0
    hw |= _bit(2, _require_bool(payload, "ped_power_enabled", default=False))
    hw |= _bit(3, _require_bool(payload, "ped_low_power", default=False))
    hw |= _bit(4, _require_bool(payload, "ped_event_registration", default=False))

    # В 0x0004 биты 11..15 зарезервированы, поэтому threshold не пакуем.
    obs_params = _pack_observation_params(payload, with_particle_threshold=False)
    trigger_config = _require_int(payload, "trigger_config", 0, 0xFFFF, default=0)

    return bytes([hw]) + _u16_le(obs_params) + _u16_le(trigger_config) + bytes([0xAA])


def _pack_ku_0005(payload: dict) -> bytes:
    hw = 0
    bank = _require_bank_bits(payload.get("selected_nand_bank", "nand1"))
    hw |= bank
    hw |= _bit(2, _require_bool(payload, "nand_power_enabled", default=False))
    hw |= _bit(3, _require_bool(payload, "ped_power_enabled", default=False))
    hw |= _bit(4, _require_bool(payload, "ped_low_power", default=False))

    return bytes([hw]) + bytes([0xAA, 0xAA, 0xAA, 0xAA, 0xAA])


def _pack_ku_0006(payload: dict) -> bytes:
    hw = 0
    bank = _require_bank_bits(payload.get("selected_nand_bank", "nand1"))
    hw |= bank
    hw |= _bit(2, _require_bool(payload, "keep_power_after_output", default=False))

    output_interface = payload.get("output_interface", "usb")
    if output_interface not in ("usb", "can"):
        raise PackingError(f"Invalid output_interface={output_interface!r}, expected 'usb' or 'can'.")
    hw |= _bit(3, output_interface == "can")

    output_type = payload.get("output_type", "requested_count")
    if output_type not in ("requested_count", "accumulated"):
        raise PackingError(
            f"Invalid output_type={output_type!r}, expected 'requested_count' or 'accumulated'."
        )
    hw |= _bit(4, output_type == "accumulated")

    requested_packet_count = _require_int(
        payload,
        "requested_packet_count",
        0,
        0xFFFFFF,
        default=0,
    )
    if output_type == "accumulated":
        requested_packet_count = 0

    return bytes([hw]) + _u24_le(requested_packet_count) + bytes([0xAA, 0xAA])


def _pack_ku_0007(payload: dict) -> bytes:
    buf = bytearray()

    control_word = 0
    control_word |= _bit(0, _require_bool(payload, "write_session_id", default=False))
    control_word |= _bit(1, _require_bool(payload, "write_nand1_packet_count", default=False))
    control_word |= _bit(2, _require_bool(payload, "write_nand2_packet_count", default=False))
    control_word |= _bit(3, _require_bool(payload, "write_nand1_erase_count", default=False))
    control_word |= _bit(4, _require_bool(payload, "write_nand2_erase_count", default=False))
    control_word |= _bit(5, _require_bool(payload, "write_nand1_test_count", default=False))
    control_word |= _bit(6, _require_bool(payload, "write_nand2_test_count", default=False))
    buf += _u16_le(control_word)

    # signed int16 temperatures
    buf += _i16_le(_require_int(payload, "min_mc_temp", -32768, 32767, default=0))
    buf += _i16_le(_require_int(payload, "max_mc_temp", -32768, 32767, default=0))
    buf += _i16_le(_require_int(payload, "min_pu_temp", -32768, 32767, default=0))
    buf += _i16_le(_require_int(payload, "max_pu_temp", -32768, 32767, default=0))
    buf += _i16_le(_require_int(payload, "min_ped_temp", -32768, 32767, default=0))
    buf += _i16_le(_require_int(payload, "max_ped_temp", -32768, 32767, default=0))
    buf += _i16_le(_require_int(payload, "min_bd_temp", -32768, 32767, default=0))
    buf += _i16_le(_require_int(payload, "max_bd_temp", -32768, 32767, default=0))

    # uint16 voltages/currents
    buf += _u16_le(_require_int(payload, "min_pu_voltage", 0, 0xFFFF, default=0))
    buf += _u16_le(_require_int(payload, "max_pu_voltage", 0, 0xFFFF, default=0))
    buf += _u16_le(_require_int(payload, "min_pu_current", 0, 0xFFFF, default=0))
    buf += _u16_le(_require_int(payload, "max_pu_current", 0, 0xFFFF, default=0))

    # По смыслу протокола здесь именно min_ped_voltage, несмотря на опечатку в таблице.
    buf += _u16_le(_require_int(payload, "min_ped_voltage", 0, 0xFFFF, default=0))
    buf += _u16_le(_require_int(payload, "max_ped_voltage", 0, 0xFFFF, default=0))
    buf += _u16_le(_require_int(payload, "min_ped_current", 0, 0xFFFF, default=0))
    buf += _u16_le(_require_int(payload, "max_ped_current", 0, 0xFFFF, default=0))

    buf += _u16_le(_require_int(payload, "outer_radiation_lmin", 0, 0xFFFF, default=0))
    buf += _u16_le(_require_int(payload, "outer_radiation_lmax", 0, 0xFFFF, default=0))
    buf += _u16_le(_require_int(payload, "inner_radiation_bmin", 0, 0xFFFF, default=0))
    buf += _u16_le(_require_int(payload, "ac1_max_count", 0, 0xFFFF, default=0))

    buf += _u32_le(_require_int(payload, "initial_rtc", 0, 0xFFFFFFFF, default=0))
    buf += _u16_le(_require_int(payload, "session_id", 0, 0xFFFF, default=0))

    buf += _u24_le(_require_int(payload, "nand1_packet_count", 0, 0xFFFFFF, default=0))
    buf += _u24_le(_require_int(payload, "nand2_packet_count", 0, 0xFFFFFF, default=0))

    buf += _u16_le(_require_int(payload, "nand1_erase_count", 0, 0xFFFF, default=0))
    buf += _u16_le(_require_int(payload, "nand2_erase_count", 0, 0xFFFF, default=0))
    buf += _u16_le(_require_int(payload, "nand1_test_count", 0, 0xFFFF, default=0))
    buf += _u16_le(_require_int(payload, "nand2_test_count", 0, 0xFFFF, default=0))
    buf += _u16_le(_require_int(payload, "alarm_mask", 0, 0xFFFF, default=0))

    if len(buf) != 64:
        raise PackingError(f"KU 0x0007 must pack to 64 bytes, got {len(buf)} bytes.")

    return bytes(buf)


def _pack_ku_0008(payload: dict) -> bytes:
    hw = 0
    bank = _require_bank_bits(payload.get("selected_nand_bank", "nand1"))
    hw |= bank
    hw |= _bit(2, _require_bool(payload, "keep_power_after_erase", default=False))

    return bytes([hw]) + bytes([0xAA, 0xAA, 0xAA, 0xAA, 0xAA])


def _pack_ku_0009(payload: dict) -> bytes:
    hw = 0
    bank = _require_bank_bits(payload.get("selected_nand_bank", "nand1"))
    hw |= bank
    hw |= _bit(2, _require_bool(payload, "keep_power_after_test", default=False))

    return bytes([hw]) + bytes([0xAA, 0xAA, 0xAA, 0xAA, 0xAA])


def _pack_ku_000A(payload: dict) -> bytes:
    hw = 0
    bank = _require_bank_bits(payload.get("selected_nand_bank", "nand1"))
    hw |= bank

    return bytes([hw]) + bytes([0xAA, 0xAA, 0xAA, 0xAA, 0xAA])


def _pack_kt_0100(payload: dict) -> bytes:
    board_time_ms = _require_int(payload, "board_time_ms", 0, 0xFFFF, default=0)
    board_time_s = _require_int(payload, "board_time_s", 0, 0xFFFFFFFF, default=0)

    return _u16_le(board_time_ms) + _u32_le(board_time_s)


def _pack_kt_0101(payload: dict) -> bytes:
    measurement_time_s = _require_int(payload, "measurement_time_s", 0, 0xFFFFFFFF, default=0)
    measurement_time_ms = _require_int(payload, "measurement_time_ms", 0, 0xFFFF, default=0)

    x = _require_int(payload, "x", -0x80000000, 0x7FFFFFFF, default=0)
    y = _require_int(payload, "y", -0x80000000, 0x7FFFFFFF, default=0)
    z = _require_int(payload, "z", -0x80000000, 0x7FFFFFFF, default=0)

    vx = _require_int(payload, "vx", -0x80000000, 0x7FFFFFFF, default=0)
    vy = _require_int(payload, "vy", -0x80000000, 0x7FFFFFFF, default=0)
    vz = _require_int(payload, "vz", -0x80000000, 0x7FFFFFFF, default=0)

    l_shell = _require_int(payload, "l_shell", 0, 0xFFFF, default=0)
    b_field = _require_int(payload, "b_field", 0, 0xFFFF, default=0)

    return (
            _u32_le(measurement_time_s)
            + _u16_le(measurement_time_ms)
            + _i32_le(x)
            + _i32_le(y)
            + _i32_le(z)
            + _i32_le(vx)
            + _i32_le(vy)
            + _i32_le(vz)
            + _u16_le(l_shell)
            + _u16_le(b_field)
    )


def _pack_kt_0102(payload: dict) -> bytes:
    measurement_time_s = _require_int(payload, "measurement_time_s", 0, 0xFFFFFFFF, default=0)
    measurement_time_ms = _require_int(payload, "measurement_time_ms", 0, 0xFFFF, default=0)

    q0 = _require_int(payload, "q0", -0x80000000, 0x7FFFFFFF, default=0)
    q1 = _require_int(payload, "q1", -0x80000000, 0x7FFFFFFF, default=0)
    q2 = _require_int(payload, "q2", -0x80000000, 0x7FFFFFFF, default=0)
    q3 = _require_int(payload, "q3", -0x80000000, 0x7FFFFFFF, default=0)

    return (
            _u32_le(measurement_time_s)
            + _u16_le(measurement_time_ms)
            + _i32_le(q0)
            + _i32_le(q1)
            + _i32_le(q2)
            + _i32_le(q3)
    )


def _pack_kt_0103(payload: dict) -> bytes:
    measurement_time_s = _require_int(payload, "measurement_time_s", 0, 0xFFFFFFFF, default=0)
    measurement_time_ms = _require_int(payload, "measurement_time_ms", 0, 0xFFFF, default=0)

    bx = _require_int(payload, "bx", -0x80000000, 0x7FFFFFFF, default=0)
    by = _require_int(payload, "by", -0x80000000, 0x7FFFFFFF, default=0)
    bz = _require_int(payload, "bz", -0x80000000, 0x7FFFFFFF, default=0)

    return (
            _u32_le(measurement_time_s)
            + _u16_le(measurement_time_ms)
            + _i32_le(bx)
            + _i32_le(by)
            + _i32_le(bz)
    )


def _pack_observation_params(payload: dict, with_particle_threshold: bool) -> int:
    event_format_mode = _require_int(payload, "event_format_mode", 0, 4, default=0)
    event_count_mode = _require_int(payload, "event_count_mode", 0, 5, default=0)
    spectrum_mode = _require_int(payload, "spectrum_mode", 0, 2, default=0)
    histogram_cells = _require_int(payload, "histogram_cells", 0, 4, default=0)

    value = 0
    value |= event_format_mode
    value |= event_count_mode << 3
    value |= spectrum_mode << 6
    value |= histogram_cells << 8

    if with_particle_threshold:
        particle_threshold = _require_int(payload, "particle_threshold", 0, 15, default=0)
        value |= particle_threshold << 12

    return value


def _require_bank_bits(bank_value: str) -> int:
    if bank_value == "nand1":
        return 1
    if bank_value == "nand2":
        return 2
    raise PackingError(f"Invalid bank value {bank_value!r}, expected 'nand1' or 'nand2'.")


def _require_bool(payload: dict, key: str, default: bool | None = None) -> bool:
    if key not in payload:
        if default is None:
            raise PackingError(f"Missing boolean field: {key}")
        return default
    value = payload[key]
    if not isinstance(value, bool):
        raise PackingError(f"Field {key!r} must be bool, got {type(value).__name__}.")
    return value


def _require_int(
        payload: dict,
        key: str,
        min_value: int,
        max_value: int,
        default: int | None = None,
) -> int:
    if key not in payload:
        if default is None:
            raise PackingError(f"Missing integer field: {key}")
        value = default
    else:
        value = payload[key]

    if not isinstance(value, int):
        raise PackingError(f"Field {key!r} must be int, got {type(value).__name__}.")

    if not (min_value <= value <= max_value):
        raise PackingError(
            f"Field {key!r} out of range: {value}, expected {min_value}..{max_value}."
        )
    return value


def _bit(bit_index: int, enabled: bool) -> int:
    return (1 << bit_index) if enabled else 0


def _u16_le(value: int) -> bytes:
    return value.to_bytes(2, byteorder="little", signed=False)


def _i16_le(value: int) -> bytes:
    return value.to_bytes(2, byteorder="little", signed=True)


def _u24_le(value: int) -> bytes:
    return value.to_bytes(3, byteorder="little", signed=False)


def _u32_le(value: int) -> bytes:
    return value.to_bytes(4, byteorder="little", signed=False)


def _i32_le(value: int) -> bytes:
    return value.to_bytes(4, byteorder="little", signed=True)
