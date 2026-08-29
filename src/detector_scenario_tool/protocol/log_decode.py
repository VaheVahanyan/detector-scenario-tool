"""Human-readable rendering of captured messages.

The per-message summaries are generated from the definitions, so a new message is decodable the
moment it is defined. Only the three messages whose meaning is not a flat field list — ТС «Статус»,
ТС «Квитанция» and ТС «Телеметрия» — get extra interpretation on top.
"""

from __future__ import annotations

from detector_scenario_tool.domain.logs import (
    LOG_CATEGORY,
    LogRecord,
    decode_log_text,
    log_text_line,
    looks_like_text,
)
from detector_scenario_tool.i18n import tr
from detector_scenario_tool.protocol import legacy_v2, registry, well_known
from detector_scenario_tool.protocol.errors import (
    ALARM_BITS,
    STATUS_BITS,
    AckErrorCode,
    decode_ack_status,
    decode_bit_names,
)
from detector_scenario_tool.protocol.fields import MessageDef, unpack_message
from detector_scenario_tool.protocol.format_values import format_field_value
from detector_scenario_tool.protocol.modes import decode_mode_byte

#: How many fields a one-line summary shows before it gives up and reports a count.
SUMMARY_FIELD_LIMIT = 4


def incoming_category(msg_id: int) -> str:
    """What a message arriving from the bus is: a telemetry message, or the board's own log.

    Only the catalogue can say. Until `Протокол_CAN_ГС_v2_1_Спутникс` an identifier's range gave
    it away, but v2.1 scatters the catalogue across `0D00…0D03`, `0E00` and `FFE1`, and the МК
    prints its debug output over the same bus under identifiers of its own choosing.

    Anything the catalogue does not hold as a ТС is therefore *not an answer from the НА* — a
    control command echoed back by another device included — and is captured as board log output
    instead. Getting this wrong in the other direction is what matters: a stray printf must never
    be able to satisfy a wait step.
    """
    return "TS" if registry.find("TS", msg_id) is not None else LOG_CATEGORY


def build_log_summary(record: LogRecord) -> str:
    """One line for the log table."""
    if record.category == LOG_CATEGORY:
        return _summarise_board_log(record)

    spec = registry.find(record.category, record.msg_id)
    if spec is None:
        return tr("logdecode.unknown_message", length=len(record.payload))

    try:
        if spec.symbol == well_known.ACK:
            return _summarise_ack(spec, record.payload)
        if spec.symbol == well_known.STATUS:
            return _summarise_status(spec, record.payload)
        if spec.symbol == well_known.TELEMETRY:
            return _summarise_telemetry(spec, record.payload)
        return _summarise_generic(spec, record.payload)
    except Exception:
        return tr("logdecode.undecodable", length=len(record.payload))


def build_log_detail(record: LogRecord) -> str:
    """Multi-line field-by-field decode for the detail pane."""
    if record.category == LOG_CATEGORY:
        return _detail_board_log(record)

    spec = registry.find(record.category, record.msg_id)
    if spec is None:
        return tr("logdecode.unknown_message", length=len(record.payload))

    values = unpack_message(spec, record.payload)
    lines = [f"{spec.symbol} — {tr(spec.name_key)}"]
    if spec.doc_ref:
        lines.append(spec.doc_ref)
    lines.append("")

    for field_spec in spec.fields:
        if not field_spec.editable or field_spec.key not in values:
            continue
        lines.append(
            f"{field_spec.label}: {format_field_value(field_spec, values[field_spec.key])}"
        )

    lines.extend(_extra_detail(spec, values))
    return "\n".join(lines)


# --------------------------------------------------------------------------------------
# The board's own output
# --------------------------------------------------------------------------------------

def _summarise_board_log(record: LogRecord) -> str:
    moved = _legacy_label(record.msg_id)
    if moved is not None:
        # Not board output at all: firmware a revision behind, answering under its old numbers.
        return tr("logdecode.legacy_v2", label=moved)

    if looks_like_text(record.payload):
        return log_text_line(record.payload)
    # Not text after all — say so rather than printing mojibake. The hex is in its own column.
    return tr("logdecode.board_log.binary", length=len(record.payload))


def _detail_board_log(record: LogRecord) -> str:
    moved = _legacy_label(record.msg_id)
    if moved is not None:
        return "\n".join([
            tr("logdecode.legacy_v2", label=moved),
            "",
            tr("logdecode.legacy_v2.hint", msg=f"0x{record.msg_id:04X}"),
            "",
            record.payload_hex,
        ])

    lines = [tr("logdecode.board_log.title", msg=f"0x{record.msg_id:04X}"), ""]

    if looks_like_text(record.payload):
        lines.append(decode_log_text(record.payload))
    else:
        lines.append(tr("logdecode.board_log.binary", length=len(record.payload)))
        lines.append(record.payload_hex)

    return "\n".join(lines)


def _legacy_label(msg_id: int) -> str | None:
    """`ТС 0x0D01 Квитанция` for a number this message carried in v2, else None."""
    from detector_scenario_tool.utils.labels import message_label

    moved = legacy_v2.recognise(msg_id)
    return None if moved is None else message_label(*moved)


# --------------------------------------------------------------------------------------
# Summaries
# --------------------------------------------------------------------------------------

def _summarise_generic(spec: MessageDef, data: bytes) -> str:
    values = unpack_message(spec, data)
    parts = []

    for field_spec in spec.fields:
        if not field_spec.editable or field_spec.key not in values:
            continue
        parts.append(
            f"{field_spec.label}="
            f"{format_field_value(field_spec, values[field_spec.key])}"
        )
        if len(parts) >= SUMMARY_FIELD_LIMIT:
            break

    if not parts:
        return tr("logdecode.no_fields", length=len(data))

    remaining = len([f for f in spec.editable_fields if f.key in values]) - len(parts)
    text = ", ".join(parts)
    if remaining > 0:
        text += tr("logdecode.more_fields", count=remaining)
    return text


def _summarise_ack(spec: MessageDef, data: bytes) -> str:
    values = unpack_message(spec, data)
    acknowledged = values.get("acknowledged_msg_id")
    rejected = bool(values.get("rejected", 0))
    code = values.get("error_code", 0)

    try:
        code_name = tr(AckErrorCode(code).label_key)
    except ValueError:
        code_name = str(code)

    text = tr(
        "logdecode.ack",
        msg=f"0x{acknowledged:04X}" if acknowledged is not None else "?",
        verdict=tr("logdecode.ack.rejected") if rejected else tr("logdecode.ack.accepted"),
        code=code_name,
    )

    packets = values.get("packet_count")
    if packets is not None and packets != 0xAAAAAA:
        # Bytes 5-7 only carry a packet count for the CMD_DUMP acknowledgement (§4.2 note 1).
        text += tr("logdecode.ack.packets", count=packets)
    return text


def _summarise_status(spec: MessageDef, data: bytes) -> str:
    values = unpack_message(spec, data)
    previous, current = decode_mode_byte(
        (values.get("previous_mode", 0)) | (values.get("current_mode", 0) << 3)
    )
    alarms = decode_bit_names(values.get("masked_alarm_status", 0), ALARM_BITS)

    text = tr(
        "logdecode.status",
        current=tr(current.label_key) if current else "?",
        previous=tr(previous.label_key) if previous else "?",
    )

    overflow = []
    if values.get("nand1_overflow"):
        overflow.append("NAND1")
    if values.get("nand2_overflow"):
        overflow.append("NAND2")
    if overflow:
        text += tr("logdecode.status.overflow", banks=", ".join(overflow))

    if alarms:
        text += tr("logdecode.status.alarms", alarms=", ".join(alarms))
    return text


def _summarise_telemetry(spec: MessageDef, data: bytes) -> str:
    values = unpack_message(spec, data)
    _, current = decode_mode_byte(
        (values.get("previous_mode", 0)) | (values.get("current_mode", 0) << 3)
    )
    alarms = decode_bit_names(values.get("masked_alarm_status", 0), ALARM_BITS)

    text = tr(
        "logdecode.telemetry",
        mode=tr(current.label_key) if current else "?",
        rtc=values.get("rtc", 0),
        mc_temp=values.get("mc_temp", 0),
        ped_temp=values.get("ped_temp", 0),
    )
    if alarms:
        text += tr("logdecode.status.alarms", alarms=", ".join(alarms))
    return text


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------

def _extra_detail(spec: MessageDef, values: dict) -> list[str]:
    lines: list[str] = []

    if spec.category != "TS":
        return lines

    if "masked_alarm_status" in values:
        names = decode_bit_names(values["masked_alarm_status"], ALARM_BITS)
        lines.append("")
        lines.append(
            tr("logdecode.detail.masked_alarms", alarms=", ".join(names) or tr("value.none"))
        )

    if "alarm_status" in values:
        names = decode_bit_names(values["alarm_status"], ALARM_BITS)
        lines.append(
            tr("logdecode.detail.alarms", alarms=", ".join(names) or tr("value.none"))
        )

    if "na_status" in values:
        names = decode_bit_names(values["na_status"], STATUS_BITS)
        lines.append(
            tr("logdecode.detail.signals", signals=", ".join(names) or tr("value.none"))
        )

    if "current_mode" in values:
        previous, current = decode_mode_byte(
            values.get("previous_mode", 0) | (values.get("current_mode", 0) << 3)
        )
        lines.append(
            tr(
                "logdecode.detail.mode",
                current=tr(current.label_key) if current else "?",
                previous=tr(previous.label_key) if previous else "?",
            )
        )

    if "rejected" in values:
        rejected, code = decode_ack_status(
            values.get("rejected", 0) | (values.get("error_code", 0) << 1)
        )
        lines.append(
            tr(
                "logdecode.detail.ack",
                verdict=tr("logdecode.ack.rejected") if rejected else tr("logdecode.ack.accepted"),
                code=tr(code.label_key) if code else "?",
            )
        )

    return lines
