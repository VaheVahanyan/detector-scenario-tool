"""Bus addresses and identifiers, kept in one place for the CAN transport (upgrade plan phase 5).

Both addresses are changeable at runtime by `CMD_SET_DEST_ID` / `CMD_SET_DEVICE_ID`, so these are
starting values, not constants of the protocol.
"""

from __future__ import annotations

#: Протокол_CAN_ГС_v2_1_Спутникс §1.5 — address of the spacecraft's onboard computer on CAN1.
DEFAULT_BVS_ADDRESS = 0x05

#: §1.6 — address of the payload (НА) on CAN1, marked "предварительно" in the document.
DEFAULT_NA_ADDRESS = 0x1E

#: SXC РЭ §1.4.11: the bus runs CAN 2.0B at 1 Mbit/s.
DEFAULT_BITRATE = 1_000_000

#: The CAN identifier the controller's debug log goes out on, when the firmware is built with
#: `NATALIA_LOG_BACKEND == NATALIA_LOG_BACKEND_CAN` (`BSP/UART/src/log_backend_can.c`,
#: `LOG_BACKEND_CAN_DEBUG_ID`). These frames are **not** UniCAN: the identifier is a constant
#: rather than an address pair, and the data bytes are raw text with no MSG_ID in front of them.
#: A firmware constant rather than a protocol one, hence a connection setting.
DEFAULT_BOARD_LOG_ID = 0x7DB
