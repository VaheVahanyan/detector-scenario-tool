"""Телеметрические сообщения (ТС / TM) — Протокол_CAN_ГС_v2 §4.

These travel from the НА to the БВС, so the tool never packs them; the definitions exist so the log
panel can decode a captured message field by field.
"""

from __future__ import annotations

from detector_scenario_tool.protocol.definitions.builders import (
    bits,
    filler,
    i16,
    raw,
    reserved,
    u8,
    u16,
    u24,
    u32,
)
from detector_scenario_tool.protocol.fields import AckBehaviour, MessageDef

TELEMETRY_MESSAGES: tuple[MessageDef, ...] = (
    MessageDef(
        category="TS",
        msg_id=0x0200,
        symbol="TM_STATUS",
        name_key="msg.TS.0200",
        length=6,
        fields=(
            bits("previous_mode", 0, 0, 3),
            bits("current_mode", 0, 3, 3),
            reserved(0, 6, 2),
            bits("nand1_overflow", 1, 0, 1),
            bits("nand2_overflow", 1, 1, 1),
            reserved(1, 2, 6),
            u16("masked_alarm_status", 2),
            u16("na_status", 4),
        ),
        ack=AckBehaviour.NONE,
        doc_ref="Протокол_CAN_ГС_v2 §4.1",
    ),
    MessageDef(
        category="TS",
        msg_id=0x0201,
        symbol="TM_ACK",
        name_key="msg.TS.0201",
        length=6,
        fields=(
            u16("acknowledged_msg_id", 0),
            bits("rejected", 2, 0, 1),
            bits("error_code", 2, 1, 7),
            # Only filled for the acknowledgement of CMD_DUMP; AAh otherwise (§4.2 note 1).
            u24("packet_count", 3),
        ),
        ack=AckBehaviour.NONE,
        doc_ref="Протокол_CAN_ГС_v2 §4.2",
    ),
    MessageDef(
        category="TS",
        msg_id=0x0202,
        symbol="TM_TELEMETRY",
        name_key="msg.TS.0202",
        length=100,
        fields=(
            u32("rtc", 0),
            i16("mc_temp", 4),
            i16("pu_temp", 6),
            i16("ped_temp", 8),
            i16("bd_temp", 10),
            u16("pu_voltage", 12),
            u16("pu_current", 14),
            u16("ped_voltage", 16),
            u16("ped_current", 18),
            u16("alarm_status", 20),
            u16("masked_alarm_status", 22),
            bits("previous_mode", 24, 0, 3),
            bits("current_mode", 24, 3, 3),
            reserved(24, 6, 2),
            bits("nand1_overflow", 25, 0, 1),
            bits("nand2_overflow", 25, 1, 1),
            reserved(25, 2, 6),
            u16("na_status", 26),
            # Zero outside OBSERVE (§4.3 note 1).
            u16("ped_status", 28),
            u16("trigger_config", 30),
            u16("observation_params", 32),
            # Bytes 34-97: the MRAM configuration echoed back, same order as CMD_SET_CFG.
            i16("min_mc_temp", 34),
            i16("max_mc_temp", 36),
            i16("min_pu_temp", 38),
            i16("max_pu_temp", 40),
            i16("min_ped_temp", 42),
            i16("max_ped_temp", 44),
            i16("min_bd_temp", 46),
            i16("max_bd_temp", 48),
            u16("min_pu_voltage", 50),
            u16("max_pu_voltage", 52),
            u16("min_pu_current", 54),
            u16("max_pu_current", 56),
            u16("min_ped_voltage", 58),
            u16("max_ped_voltage", 60),
            u16("min_ped_current", 62),
            u16("max_ped_current", 64),
            u16("outer_radiation_lmin", 66),
            u16("outer_radiation_lmax", 68),
            u16("inner_radiation_bmin", 70),
            u16("ac1_max_count", 72),
            u32("initial_rtc", 74),
            u16("session_id", 78),
            u24("nand1_packet_count", 80),
            u24("nand2_packet_count", 83),
            u16("nand1_erase_count", 86),
            u16("nand2_erase_count", 88),
            u16("nand1_test_count", 90),
            u16("nand2_test_count", 92),
            u16("alarm_mask", 94),
            u16("can_control_parameter", 96),
            u8("destination_id", 98),
            u8("device_id", 99),
        ),
        ack=AckBehaviour.NONE,
        doc_ref="Протокол_CAN_ГС_v2 §4.3",
    ),
    MessageDef(
        category="TS",
        msg_id=0x0203,
        symbol="TM_TEST_RESULT",
        name_key="msg.TS.0203",
        length=6146,
        fields=(
            # 2048 blocks × 3 bytes of error counts, then a CRC copied verbatim out of MRAM.
            raw("block_error_counts", 0, 6144),
            u16("crc", 6144),
        ),
        ack=AckBehaviour.NONE,
        doc_ref="Протокол_CAN_ГС_v2 §4.4",
    ),
)

#: §4.4 — the error array is 2048 entries of 3 bytes.
TEST_RESULT_BLOCK_COUNT = 2048
TEST_RESULT_BLOCK_WIDTH = 3
