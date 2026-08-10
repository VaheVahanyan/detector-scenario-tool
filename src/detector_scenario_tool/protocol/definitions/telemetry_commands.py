"""Команды телеметрии (КТ / TC) — Протокол_CAN_ГС_v2 §3.

All three are long UniCAN messages pushed by the БВС, valid only in OBSERVE, and never
acknowledged (§2.3: «на КТ ТС «Квитанция» не выдается»). Each produces one НИ format.

Byte offsets are absolute here: long messages are numbered from byte 0 in the document.
"""

from __future__ import annotations

from detector_scenario_tool.protocol.definitions.builders import f32, i16, u8, u32, u64
from detector_scenario_tool.protocol.fields import AckBehaviour, CyclicDefault, MessageDef
from detector_scenario_tool.protocol.modes import Mode

OBSERVE_ONLY = frozenset({Mode.OBSERVE})

#: Telemetry commands repeat for the whole observation session; 20 s matches both the parameter
#: monitoring cycle and the «Телеметрия» НИ format cadence in the algorithm description.
CYCLIC_20S = CyclicDefault(enabled=True, period_ms=20_000)


def _vector(prefix: str, offset: int, axes: str = "xyz") -> tuple:
    return tuple(f32(f"{prefix}_{axis}", offset + 4 * i) for i, axis in enumerate(axes))


def _quaternion(prefix: str, offset: int) -> tuple:
    return tuple(f32(f"{prefix}_{c}", offset + 4 * i) for i, c in enumerate("wxyz"))


TELEMETRY_COMMANDS: tuple[MessageDef, ...] = (
    MessageDef(
        category="KT",
        msg_id=0xF210,
        symbol="TLM_TIME_ORBIT_ATT",
        name_key="msg.KT.F210",
        length=125,
        fields=(
            u64("system_time", 0),
            u32("time_since_reboot_s", 8),
            *_quaternion("eci_quaternion", 12),
            *_vector("eci_angular_rate", 28),
            u8("eci_data_quality", 40),
            *_quaternion("orb_quaternion", 41),
            *_vector("orb_angular_rate", 57),
            u8("orb_data_quality", 69),
            *_quaternion("forced_eci_quaternion", 70),
            *_vector("forced_eci_angular_rate", 86),
            u8("forced_eci_data_quality", 98),
            f32("latitude_deg", 99),
            f32("longitude_deg", 103),
            f32("altitude_m", 107),
            u8("ballistic_parameters", 111),
            u8("adcs_task_type", 112),
            u8("adcs_scheduled_task_count", 113),
            i16("reaction_wheel_x_plus_rpm", 114),
            i16("reaction_wheel_x_minus_rpm", 116),
            i16("reaction_wheel_y_plus_rpm", 118),
            i16("reaction_wheel_y_minus_rpm", 120),
            u8("extra_parameters_0", 122),
            u8("extra_parameters_1", 123),
            u8("extra_parameters_2", 124),
        ),
        allowed_modes=OBSERVE_ONLY,
        ack=AckBehaviour.NONE,
        follow_up=(),
        cyclic_default=CYCLIC_20S,
        doc_ref="Протокол_CAN_ГС_v2 §3.1 (НИ формат 05h)",
    ),
    MessageDef(
        category="KT",
        msg_id=0xF221,
        symbol="TLM_MAGFIELD",
        name_key="msg.KT.F221",
        length=76,
        fields=(
            *_vector("measured_magnetic_field", 0),
            *_vector("computed_magnetic_field_eci", 12),
            *_vector("measured_angular_rate", 24),
            *_vector("sun_direction_sensors", 36),
            *_vector("sun_direction_eci", 48),
            *_quaternion("star_tracker_quaternion", 60),
        ),
        allowed_modes=OBSERVE_ONLY,
        ack=AckBehaviour.NONE,
        follow_up=(),
        cyclic_default=CYCLIC_20S,
        doc_ref="Протокол_CAN_ГС_v2 §3.2 (НИ формат 06h)",
    ),
    MessageDef(
        category="KT",
        msg_id=0x0100,
        symbol="TLM_MCILWAIN",
        name_key="msg.KT.0100",
        length=24,
        fields=(
            u64("system_time", 0),
            f32("latitude_deg", 8),
            f32("longitude_deg", 12),
            f32("altitude_m", 16),
            i16("l_parameter_x100", 20),
            i16("b_parameter_gauss_x1000", 22),
        ),
        allowed_modes=OBSERVE_ONLY,
        ack=AckBehaviour.NONE,
        follow_up=(),
        cyclic_default=CYCLIC_20S,
        doc_ref="Протокол_CAN_ГС_v2 §3.3 (НИ формат 07h)",
    ),
)
