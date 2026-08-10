"""Команды управления (КУ / CC) — Протокол_CAN_ГС_v2 §2, Обработка_команд_CAN_NATALIA §9.

Byte offsets are content-relative. These are short messages, so content byte 0 here is byte 2 in
the protocol document (the CAN frame data byte after the 2-byte MSG_ID).
"""

from __future__ import annotations

from detector_scenario_tool.protocol.definitions.builders import (
    bits,
    f32,
    filler,
    flag,
    i16,
    mram_bank,
    nand_bank,
    reserved,
    u8,
    u16,
    u24,
    u32,
    unused,
)
from detector_scenario_tool.protocol.fields import (
    AckBehaviour,
    CrossCheck,
    ExpectedResponse,
    MessageDef,
)
from detector_scenario_tool.protocol.modes import Mode

ALL_MODES = frozenset(
    {Mode.DUTY, Mode.ERASE, Mode.TEST, Mode.OBSERVE, Mode.DUMP, Mode.ALARM, Mode.SHUTDOWN}
)

ACK = ExpectedResponse(
    "TS", 0x0201, timeout_ms=1000, is_ack=True, bind_to_previous_ku=True, require_ack_ok=True
)
STATUS = ExpectedResponse("TS", 0x0200, timeout_ms=1000)
TELEMETRY = ExpectedResponse("TS", 0x0202, timeout_ms=1000)
TEST_RESULT = ExpectedResponse("TS", 0x0203, timeout_ms=5000)

#: §2.4 — «Параметры режима наблюдений», shared by CMD_OBSERVE_START and CMD_OBSERVE_CTRL.
#: §9.5 keeps the same layout for CMD_OBSERVE_CTRL, including the registration threshold, which
#: it writes to the ПЭД `Threshold` register.
OBSERVATION_PARAMS_CHOICES = {
    0: "choice.event_format.none",
    1: "choice.event_format.always",
    2: "choice.event_format.outside_inner_belt_bcsat",
    3: "choice.event_format.outside_inner_belt_bmsat",
    4: "choice.event_format.outside_inner_belt_b",
    5: "choice.event_format.outside_belts_bl",
    6: "choice.event_format.below_ac1_rate",
}

EVENT_COUNT_CHOICES = {
    0: "choice.nmax.none",
    1: "choice.nmax.1",
    2: "choice.nmax.10",
    3: "choice.nmax.20",
    4: "choice.nmax.50",
    5: "choice.nmax.100",
}

SPECTRUM_CHOICES = {
    0: "choice.spectrum.none",
    1: "choice.spectrum.spectrum1",
    2: "choice.spectrum.spectrum2",
}

HISTOGRAM_CHOICES = {
    0: "choice.nhist.none",
    1: "choice.nhist.256",
    2: "choice.nhist.512",
    3: "choice.nhist.1024",
    4: "choice.nhist.2048",
}


def _observation_params(offset: int) -> tuple:
    """Bytes 3-4 of CMD_OBSERVE_START / CMD_OBSERVE_CTRL, as one 16-bit word."""
    return (
        bits(
            "event_format_mode", offset, 0, 3, byte_length=2,
            choices=OBSERVATION_PARAMS_CHOICES, max_value=6,
        ),
        bits(
            "event_count_mode", offset, 3, 3, byte_length=2,
            choices=EVENT_COUNT_CHOICES, max_value=5,
        ),
        bits(
            "spectrum_mode", offset, 6, 2, byte_length=2,
            choices=SPECTRUM_CHOICES, max_value=2,
        ),
        bits(
            "histogram_cells", offset, 8, 3, byte_length=2,
            choices=HISTOGRAM_CHOICES, max_value=4,
        ),
        reserved(offset, 11, 1, byte_length=2),
        bits("particle_threshold", offset, 12, 4, byte_length=2, max_value=15),
    )


def _events_and_nmax_agree(payload) -> bool:
    """§9.4: the «События» flag and Nmax are either both zero or both non-zero."""
    events = payload.get("event_format_mode", 0)
    nmax = payload.get("event_count_mode", 0)
    return (events == 0) == (nmax == 0)


def _spectrum_and_nhist_agree(payload) -> bool:
    """§9.4: Спектр-1 requires Nhist != 0; no spectrum or Спектр-2 requires Nhist == 0."""
    spectrum = payload.get("spectrum_mode", 0)
    nhist = payload.get("histogram_cells", 0)
    if spectrum == 1:
        return nhist != 0
    return nhist == 0


OBSERVATION_CROSS_CHECKS = (
    CrossCheck(
        "observation.events_nmax_mismatch",
        _events_and_nmax_agree,
        ("event_format_mode", "event_count_mode"),
    ),
    CrossCheck(
        "observation.spectrum_nhist_mismatch",
        _spectrum_and_nhist_agree,
        ("spectrum_mode", "histogram_cells"),
    ),
)


def _dump_count_present(payload) -> bool:
    """§9.7: with output type 0 the requested packet count must not be zero."""
    if payload.get("output_type", 0) != 0:
        return True
    return payload.get("requested_packet_count", 0) != 0


CONTROL_COMMANDS: tuple[MessageDef, ...] = (
    MessageDef(
        category="KU",
        msg_id=0x0000,
        symbol="CMD_TELEM_REQ",
        name_key="msg.KU.0000",
        length=6,
        fields=(filler(0, 6),),
        allowed_modes=frozenset({Mode.DUTY, Mode.OBSERVE, Mode.ALARM}),
        follow_up=(ACK, TELEMETRY),
        doc_ref="Протокол_CAN_ГС_v2 §2.1",
    ),
    MessageDef(
        category="KU",
        msg_id=0x0001,
        symbol="CMD_STATUS_REQ",
        name_key="msg.KU.0001",
        length=6,
        fields=(filler(0, 6),),
        allowed_modes=ALL_MODES,
        follow_up=(ACK, STATUS),
        doc_ref="Протокол_CAN_ГС_v2 §2.2",
    ),
    MessageDef(
        category="KU",
        msg_id=0x0002,
        symbol="CMD_SET_TIME",
        name_key="msg.KU.0002",
        length=6,
        fields=(
            u16("board_time_ms", 0, max_value=999),
            u32("board_time_s", 2),
        ),
        allowed_modes=frozenset({Mode.DUTY}),
        follow_up=(ACK,),
        doc_ref="Протокол_CAN_ГС_v2 §2.3",
    ),
    MessageDef(
        category="KU",
        msg_id=0x0003,
        symbol="CMD_OBSERVE_START",
        name_key="msg.KU.0003",
        length=6,
        fields=(
            nand_bank(0, 0),
            flag("ped_power_enabled", 0, 2),
            flag("ped_low_power", 0, 3),
            flag("ped_event_registration", 0, 4),
            flag("keep_nand_power_after_overflow", 0, 5),
            flag("keep_ped_power_after_overflow", 0, 6),
            flag("keep_ped_low_power_after_overflow", 0, 7),
            *_observation_params(1),
            u16("trigger_config", 3),
            filler(5, 1),
        ),
        allowed_modes=frozenset({Mode.DUTY}),
        follow_up=(ACK, STATUS),
        cross_checks=OBSERVATION_CROSS_CHECKS,
        changes_mode_to=Mode.OBSERVE,
        doc_ref="Протокол_CAN_ГС_v2 §2.4",
    ),
    MessageDef(
        category="KU",
        msg_id=0x0004,
        symbol="CMD_OBSERVE_CTRL",
        name_key="msg.KU.0004",
        length=6,
        fields=(
            # §9.5: bits 0-1 are unused and must read 3.
            reserved(0, 0, 2, value=3),
            flag("ped_power_enabled", 0, 2),
            flag("ped_low_power", 0, 3),
            flag("ped_event_registration", 0, 4),
            reserved(0, 5, 3),
            *_observation_params(1),
            u16("trigger_config", 3),
            filler(5, 1),
        ),
        allowed_modes=frozenset({Mode.OBSERVE}),
        follow_up=(ACK,),
        cross_checks=OBSERVATION_CROSS_CHECKS,
        doc_ref="Протокол_CAN_ГС_v2 §2.5",
    ),
    MessageDef(
        category="KU",
        msg_id=0x0005,
        symbol="CMD_DUTY",
        name_key="msg.KU.0005",
        length=6,
        fields=(
            nand_bank(0, 0),
            flag("nand_power_enabled", 0, 2),
            flag("ped_power_enabled", 0, 3),
            flag("ped_low_power", 0, 4),
            reserved(0, 5, 3),
            filler(1, 5),
        ),
        allowed_modes=frozenset({Mode.DUTY, Mode.ERASE, Mode.TEST, Mode.OBSERVE, Mode.DUMP}),
        follow_up=(ACK, ExpectedResponse("TS", 0x0200, guaranteed=False)),
        changes_mode_to=Mode.DUTY,
        doc_ref="Протокол_CAN_ГС_v2 §2.6",
    ),
    MessageDef(
        category="KU",
        msg_id=0x0006,
        symbol="CMD_DUMP",
        name_key="msg.KU.0006",
        length=6,
        fields=(
            nand_bank(0, 0),
            flag("keep_nand_power_after_dump", 0, 2),
            # §9.7: DUMP is USB only; bit 3 set to 1 is rejected with ERR_CONTENT.
            reserved(0, 3, 1, suffix="_output_interface"),
            bits(
                "output_type", 0, 4, 1,
                choices={0: "choice.dump.requested_count", 1: "choice.dump.all_accumulated"},
            ),
            reserved(0, 5, 3),
            # §9.7 rejects a zero count when the output type is "requested count", which is the
            # default, so a freshly added step must not start out invalid.
            u24("requested_packet_count", 1, default=1),
            filler(4, 2),
        ),
        allowed_modes=frozenset({Mode.DUTY}),
        follow_up=(ACK, STATUS),
        cross_checks=(
            CrossCheck("dump.count_required", _dump_count_present, ("requested_packet_count",)),
        ),
        changes_mode_to=Mode.DUMP,
        doc_ref="Протокол_CAN_ГС_v2 §2.7",
    ),
    MessageDef(
        category="KU",
        msg_id=0x0007,
        symbol="CMD_SET_CFG",
        name_key="msg.KU.0007",
        length=66,
        fields=(
            # Bytes 0-1: слово управления записью настроек.
            flag("write_session_id", 0, 0, byte_length=2),
            flag("write_nand1_packet_count", 0, 1, byte_length=2),
            flag("write_nand2_packet_count", 0, 2, byte_length=2),
            flag("write_nand1_erase_count", 0, 3, byte_length=2),
            flag("write_nand2_erase_count", 0, 4, byte_length=2),
            flag("write_nand1_test_count", 0, 5, byte_length=2),
            flag("write_nand2_test_count", 0, 6, byte_length=2),
            reserved(0, 7, 9, byte_length=2),
            # Bytes 2-17: temperature thresholds.
            i16("min_mc_temp", 2),
            i16("max_mc_temp", 4),
            i16("min_pu_temp", 6),
            i16("max_pu_temp", 8),
            i16("min_ped_temp", 10),
            i16("max_ped_temp", 12),
            i16("min_bd_temp", 14),
            i16("max_bd_temp", 16),
            # Bytes 18-25: ПУ voltage and current.
            u16("min_pu_voltage", 18),
            u16("max_pu_voltage", 20),
            u16("min_pu_current", 22),
            u16("max_pu_current", 24),
            # Bytes 26-33: ПЭД voltage and current.
            u16("min_ped_voltage", 26),
            u16("max_ped_voltage", 28),
            u16("min_ped_current", 30),
            u16("max_ped_current", 32),
            # Bytes 34-41: radiation belt parameters and the AC1 rate limit.
            u16("outer_radiation_lmin", 34),
            u16("outer_radiation_lmax", 36),
            u16("inner_radiation_bmin", 38),
            u16("ac1_max_count", 40),
            # Bytes 42-61: service counters.
            u32("initial_rtc", 42),
            u16("session_id", 46),
            u24("nand1_packet_count", 48),
            u24("nand2_packet_count", 51),
            u16("nand1_erase_count", 54),
            u16("nand2_erase_count", 56),
            u16("nand1_test_count", 58),
            u16("nand2_test_count", 60),
            u16("alarm_mask", 62),
            # Bytes 64-65: параметр управления взаимодействием по интерфейсу CAN.
            bits(
                "can_reply_address_source", 64, 0, 1, byte_length=2,
                choices={0: "choice.can_reply.mram", 1: "choice.can_reply.sender"},
            ),
            bits(
                "sputniks_time_reaction", 64, 1, 1, byte_length=2,
                choices={0: "choice.sputniks_time.accept", 1: "choice.sputniks_time.ignore"},
            ),
            reserved(64, 2, 14, byte_length=2),
        ),
        allowed_modes=frozenset({Mode.DUTY, Mode.ALARM}),
        follow_up=(ACK,),
        doc_ref="Протокол_CAN_ГС_v2 §2.8",
    ),
    MessageDef(
        category="KU",
        msg_id=0x0008,
        symbol="CMD_ERASE",
        name_key="msg.KU.0008",
        length=6,
        fields=(
            nand_bank(0, 0),
            flag("keep_power_after_erase", 0, 2),
            reserved(0, 3, 5),
            filler(1, 5),
        ),
        allowed_modes=frozenset({Mode.DUTY}),
        follow_up=(ACK, STATUS),
        changes_mode_to=Mode.ERASE,
        doc_ref="Протокол_CAN_ГС_v2 §2.9",
    ),
    MessageDef(
        category="KU",
        msg_id=0x0009,
        symbol="CMD_TEST",
        name_key="msg.KU.0009",
        length=6,
        fields=(
            nand_bank(0, 0),
            flag("keep_power_after_test", 0, 2),
            reserved(0, 3, 5),
            filler(1, 5),
        ),
        allowed_modes=frozenset({Mode.DUTY}),
        follow_up=(ACK, STATUS),
        changes_mode_to=Mode.TEST,
        doc_ref="Протокол_CAN_ГС_v2 §2.10",
    ),
    MessageDef(
        category="KU",
        msg_id=0x000A,
        symbol="CMD_TEST_RESULT",
        name_key="msg.KU.000A",
        length=6,
        fields=(
            nand_bank(0, 0),
            mram_bank(0, 2),
            reserved(0, 4, 4),
            filler(1, 5),
        ),
        allowed_modes=frozenset({Mode.DUTY}),
        follow_up=(ACK, TEST_RESULT),
        doc_ref="Протокол_CAN_ГС_v2 §2.11",
    ),
    MessageDef(
        category="KU",
        msg_id=0x000B,
        symbol="CMD_SHUTDOWN",
        name_key="msg.KU.000B",
        length=6,
        fields=(filler(0, 6),),
        allowed_modes=frozenset(
            {Mode.DUTY, Mode.ERASE, Mode.TEST, Mode.OBSERVE, Mode.DUMP, Mode.ALARM}
        ),
        follow_up=(ACK, STATUS),
        changes_mode_to=Mode.SHUTDOWN,
        doc_ref="Протокол_CAN_ГС_v2 §2.12",
    ),
    MessageDef(
        category="KU",
        msg_id=0x000C,
        symbol="CMD_RESET_ALARM",
        name_key="msg.KU.000C",
        length=6,
        fields=(filler(0, 6),),
        allowed_modes=frozenset({Mode.ALARM}),
        follow_up=(ACK,),
        doc_ref="Протокол_CAN_ГС_v2 §2.13",
    ),
    MessageDef(
        category="KU",
        msg_id=0x0401,
        symbol="CMD_SET_TIME_SPUTNIKS",
        name_key="msg.KU.0401",
        length=6,
        fields=(
            u32("posix_time", 0),
            u8("time_source_accuracy", 4),
            unused(5, 1),
        ),
        allowed_modes=frozenset({Mode.DUTY}),
        # §9.14: with bit 1 of the CAN control word set, the command is ignored and no
        # acknowledgement is produced at all — the only such command in the protocol.
        ack=AckBehaviour.ACK_MAY_BE_SUPPRESSED,
        follow_up=(ExpectedResponse("TS", 0x0201, is_ack=True, bind_to_previous_ku=True,
                                    require_ack_ok=True, guaranteed=False),),
        doc_ref="Протокол_CAN_ГС_v2 §2.14",
    ),
    MessageDef(
        category="KU",
        msg_id=0x0A61,
        symbol="CMD_SET_DEST_ID",
        name_key="msg.KU.0A61",
        length=6,
        fields=(
            u8("destination_id", 0, default=0x1E),
            unused(1, 5),
        ),
        allowed_modes=ALL_MODES,
        follow_up=(ACK,),
        doc_ref="Протокол_CAN_ГС_v2 §2.15",
    ),
    MessageDef(
        category="KU",
        msg_id=0x0A62,
        symbol="CMD_SET_DEVICE_ID",
        name_key="msg.KU.0A62",
        length=6,
        fields=(
            u8("device_id", 0, default=0x1E),
            unused(1, 5),
        ),
        allowed_modes=ALL_MODES,
        follow_up=(ACK,),
        doc_ref="Протокол_CAN_ГС_v2 §2.16",
    ),
)
