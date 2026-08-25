"""Телеметрические сообщения (ТС / TM) — Протокол_CAN_ГС_v2_1_Спутникс §4.

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
        msg_id=0x0D00,
        symbol="TM_STATUS",
        name_key="msg.tm_status",
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
        doc_ref="Протокол_CAN_ГС_v2_1_Спутникс §4.1",
    ),
    MessageDef(
        category="TS",
        msg_id=0x0D01,
        symbol="TM_ACK",
        name_key="msg.tm_ack",
        length=6,
        fields=(
            u16("acknowledged_msg_id", 0),
            bits("rejected", 2, 0, 1),
            bits("error_code", 2, 1, 7),
            # Only filled for the acknowledgement of CMD_DUMP; AAh otherwise (§4.2 note 1).
            u24("packet_count", 3),
        ),
        ack=AckBehaviour.NONE,
        doc_ref="Протокол_CAN_ГС_v2_1_Спутникс §4.2",
    ),
    MessageDef(
        category="TS",
        msg_id=0x0D02,
        symbol="TM_TELEMETRY",
        name_key="msg.tm_telemetry",
        length=109,
        fields=(
            # §4.3: the RTC is a milliseconds word plus a seconds long word. v2 had a bare u32
            # here — that split, the same one in the MRAM copy below, the widened addresses and
            # the software version are what took this message from 100 bytes to 109.
            u16("rtc_ms", 0),
            u32("rtc_s", 2),
            i16("mc_temp", 6),
            i16("pu_temp", 8),
            i16("ped_temp", 10),
            i16("bd_temp", 12),
            u16("pu_voltage", 14),
            u16("pu_current", 16),
            u16("ped_voltage", 18),
            u16("ped_current", 20),
            u16("alarm_status", 22),
            u16("masked_alarm_status", 24),
            bits("previous_mode", 26, 0, 3),
            bits("current_mode", 26, 3, 3),
            reserved(26, 6, 2),
            bits("nand1_overflow", 27, 0, 1),
            bits("nand2_overflow", 27, 1, 1),
            reserved(27, 2, 6),
            u16("na_status", 28),
            # Zero outside OBSERVE (§4.3 note 1).
            u16("ped_status", 30),
            u16("trigger_config", 32),
            u16("observation_params", 34),
            # Bytes 36-105: the MRAM configuration echoed back, same order as CMD_SET_CFG.
            i16("min_mc_temp", 36),
            i16("max_mc_temp", 38),
            i16("min_pu_temp", 40),
            i16("max_pu_temp", 42),
            i16("min_ped_temp", 44),
            i16("max_ped_temp", 46),
            i16("min_bd_temp", 48),
            i16("max_bd_temp", 50),
            u16("min_pu_voltage", 52),
            u16("max_pu_voltage", 54),
            u16("min_pu_current", 56),
            u16("max_pu_current", 58),
            u16("min_ped_voltage", 60),
            u16("max_ped_voltage", 62),
            u16("min_ped_current", 64),
            u16("max_ped_current", 66),
            u16("outer_radiation_lmin", 68),
            u16("outer_radiation_lmax", 70),
            u16("inner_radiation_bmin", 72),
            u16("ac1_max_count", 74),
            u16("initial_rtc_ms", 76),
            u32("initial_rtc_s", 78),
            u16("session_id", 82),
            u24("nand1_packet_count", 84),
            u24("nand2_packet_count", 87),
            u16("nand1_erase_count", 90),
            u16("nand2_erase_count", 92),
            u16("nand1_test_count", 94),
            u16("nand2_test_count", 96),
            u16("alarm_mask", 98),
            u16("can_control_parameter", 100),
            u16("destination_id", 102),
            u16("device_id", 104),
            # «Содержимое программного ПЗУ МК» — new in v2.1, same three bytes as ТС «Версия ПО».
            u8("sw_major", 106),
            u8("sw_minor", 107),
            u8("sw_extra", 108),
        ),
        ack=AckBehaviour.NONE,
        doc_ref="Протокол_CAN_ГС_v2_1_Спутникс §4.3",
    ),
    MessageDef(
        category="TS",
        msg_id=0x0D03,
        symbol="TM_TEST_RESULT",
        name_key="msg.tm_test_result",
        length=6146,
        fields=(
            # 2048 blocks × 3 bytes of error counts, then a CRC copied verbatim out of MRAM.
            raw("block_error_counts", 0, 6144),
            u16("crc", 6144),
        ),
        ack=AckBehaviour.NONE,
        doc_ref="Протокол_CAN_ГС_v2_1_Спутникс §4.4",
    ),
    MessageDef(
        category="TS",
        # See CMD_GET_VERSION on the FF00…FFFF band.
        msg_id=0xFFE1,
        symbol="TM_VERSION",
        name_key="msg.tm_version",
        length=3,
        fields=(
            u8("sw_major", 0),
            u8("sw_minor", 1),
            u8("sw_extra", 2),
        ),
        ack=AckBehaviour.NONE,
        doc_ref="Протокол_CAN_ГС_v2_1_Спутникс §4.5",
    ),
)

#: §4.4 — the error array is 2048 entries of 3 bytes.
TEST_RESULT_BLOCK_COUNT = 2048
TEST_RESULT_BLOCK_WIDTH = 3
