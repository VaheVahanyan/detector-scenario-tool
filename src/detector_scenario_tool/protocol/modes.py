"""Operating modes of the NA and the two different numberings the specification uses.

Таблица_состояний_и_переходов §3.1 warns about this explicitly: `Протокол_CAN_ГС_v2` §4.1 numbers
the modes for the telemetry "Режим работы НА" byte (TEST=2, ERASE=3), while §5.2 numbers them
differently for the command-validity tables (ERASE=2, TEST=3). Everything internal uses the symbolic
enum; the two integer mappings live here and nowhere else.
"""

from __future__ import annotations

from enum import Enum


class Mode(str, Enum):
    INIT = "init"
    DUTY = "duty"
    ERASE = "erase"
    TEST = "test"
    OBSERVE = "observe"
    DUMP = "dump"
    ALARM = "alarm"
    SHUTDOWN = "shutdown"

    @property
    def label_key(self) -> str:
        return f"mode.{self.value}"


#: Operational modes, i.e. everything the state machine can sit in while commands arrive.
OPERATIONAL_MODES: tuple[Mode, ...] = (
    Mode.DUTY,
    Mode.ERASE,
    Mode.TEST,
    Mode.OBSERVE,
    Mode.DUMP,
    Mode.ALARM,
    Mode.SHUTDOWN,
)

#: §4.1 — encoding of the "Режим работы НА" byte in ТС «Статус» and byte 24 of ТС «Телеметрия».
TELEMETRY_MODE_CODES: dict[Mode, int] = {
    Mode.INIT: 0,
    Mode.DUTY: 1,
    Mode.TEST: 2,
    Mode.ERASE: 3,
    Mode.OBSERVE: 4,
    Mode.DUMP: 5,
    Mode.ALARM: 6,
    Mode.SHUTDOWN: 7,
}

MODE_BY_TELEMETRY_CODE: dict[int, Mode] = {
    code: mode for mode, code in TELEMETRY_MODE_CODES.items()
}

#: §5.2 — the numbering used only when reading the command-validity tables. Kept for traceability
#: back to the document; never used for encoding.
COMMAND_TABLE_MODE_CODES: dict[Mode, int] = {
    Mode.DUTY: 1,
    Mode.ERASE: 2,
    Mode.TEST: 3,
    Mode.OBSERVE: 4,
    Mode.DUMP: 5,
    Mode.ALARM: 6,
    Mode.SHUTDOWN: 7,
}


def decode_mode_byte(value: int) -> tuple[Mode | None, Mode | None]:
    """Split the "Режим работы НА" byte into (previous, current). Bits 0-2 / 3-5, 6-7 reserved."""
    previous = MODE_BY_TELEMETRY_CODE.get(value & 0b111)
    current = MODE_BY_TELEMETRY_CODE.get((value >> 3) & 0b111)
    return previous, current


def encode_mode_byte(previous: Mode, current: Mode) -> int:
    return (TELEMETRY_MODE_CODES[previous] & 0b111) | (
        (TELEMETRY_MODE_CODES[current] & 0b111) << 3
    )
