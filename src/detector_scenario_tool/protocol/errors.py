"""Error codes carried by ТС «Квитанция» and by UniCAN bus error frames."""

from __future__ import annotations

from enum import IntEnum


class AckErrorCode(IntEnum):
    """Bits 1-7 of byte 4 of ТС «Квитанция» (Протокол_CAN_ГС_v2 §4.2)."""

    OK = 0
    ERR_MSG_ID = 1
    ERR_CONTENT = 2
    ERR_MODE = 3
    ERR_OTHER = 4

    @property
    def label_key(self) -> str:
        return f"ack.error.{self.name.lower()}"


def decode_ack_status(value: int) -> tuple[bool, AckErrorCode | None]:
    """Split byte 4 into (rejected, error code).

    Bit 0 is the execution flag: 0 — the command will be executed, 1 — rejected.
    """
    rejected = bool(value & 0x01)
    raw_code = (value >> 1) & 0x7F
    try:
        code = AckErrorCode(raw_code)
    except ValueError:
        code = None
    return rejected, code


def encode_ack_status(rejected: bool, code: AckErrorCode = AckErrorCode.OK) -> int:
    return (1 if rejected else 0) | (int(code) << 1)


class UniCanBusError(IntEnum):
    """Table 12 of SXC РЭ §1.4.4.3 — payload bytes 4-5 of an FFFFh error frame."""

    RECEIVER_NOT_INITIALISED = 0x0001
    START_BEFORE_PREVIOUS_FINISHED = 0x0002
    CRC_ERROR = 0x0003
    NO_FREE_BUFFER = 0x0004
    DATA_WITHOUT_START = 0x0005
    MORE_DATA_THAN_DECLARED = 0x0006
    COMMAND_TOO_SHORT = 0x000B
    TOO_MUCH_DATA_IN_FRAME = 0x000C
    IDENTIFIER_TOO_LONG = 0x000D
    EXTENDED_IDENTIFIER_TOO_LONG = 0x000E
    START_COMMAND_TOO_SHORT = 0x000F
    CANNOT_STORE_MESSAGE = 0x0010
    UNKNOWN_DRIVER_ERROR = 0x0011

    @property
    def label_key(self) -> str:
        return f"unican.error.{self.name.lower()}"


#: Alarm bits of the "Аварийный статус НА" word (Протокол_CAN_ГС_v2 §4.1).
ALARM_BITS: tuple[str, ...] = (
    "ALARM_MC_Temp",
    "ALARM_PU_Temp",
    "ALARM_PED_Temp",
    "ALARM_BD_Temp",
    "ALARM_PU_Volt",
    "ALARM_PU_Curr",
    "ALARM_PED_Volt",
    "ALARM_PED_Curr",
    "ALARM_PED_PS",
    "ALARM_PED_DIR",
    "ALARM_PED_ST",
    "ALARM_NAND_PS",
    "ALARM_NAND_PR",
    "ALARM_USB_VBUS",
    "ALARM_USB_PR",
    "ALARM_MRAM",
)

#: Основное описание алгоритма §12.4 — these are always masked in, whatever CMD_SET_CFG says.
NON_MASKABLE_ALARMS: frozenset[str] = frozenset(
    {"ALARM_NAND_PS", "ALARM_NAND_PR", "ALARM_USB_PR"}
)

#: Bits of the "Статус НА" word (Протокол_CAN_ГС_v2 §4.1).
STATUS_BITS: tuple[str, ...] = (
    "PU_CAN1_SHDN",
    "PU_CAN1_S",
    "PU_CAN2_SHDN",
    "PU_CAN2_S",
    "PU_NAND1_PS",
    "PU_NAND1_PSON",
    "PU_NAND2_PS",
    "PU_NAND2_PSON",
    "PU_PED_PS",
    "PU_USB_VBUS",
    "PU_FTDI_PS",
    "PU_FTDI_PSON",
    "PU_FTDI_RES",
    "PED_INHIBIT",
    "PED_SLEEP",
    "PED_PSON",
)


def decode_bit_names(value: int, names: tuple[str, ...]) -> list[str]:
    return [name for i, name in enumerate(names) if value & (1 << i)]
