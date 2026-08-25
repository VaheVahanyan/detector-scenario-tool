"""Catalogue identifiers for tests that need a real message but do not care which.

Most tests want "some control command" or "the acknowledgement"; they were written with literal
identifiers, and the specification has now renumbered the catalogue twice. Importing from here
means the next renumbering is one edit in `protocol/definitions/` plus nothing at all.

A test whose *subject* is the identifiers — `test_protocol_v2_1_deltas.py` — deliberately spells
them out instead, so this module cannot quietly agree with a mistake there.
"""

from __future__ import annotations

from detector_scenario_tool.protocol import registry


def _id(symbol: str) -> int:
    spec = registry.by_symbol(symbol)
    assert spec is not None, f"{symbol} is not in the catalogue"
    return spec.msg_id


# Команды управления (КУ)
TELEM_REQ = _id("CMD_TELEM_REQ")
STATUS_REQ = _id("CMD_STATUS_REQ")
SET_TIME = _id("CMD_SET_TIME")
OBSERVE_START = _id("CMD_OBSERVE_START")
OBSERVE_CTRL = _id("CMD_OBSERVE_CTRL")
DUTY = _id("CMD_DUTY")
DUMP = _id("CMD_DUMP")
SET_CFG = _id("CMD_SET_CFG")
ERASE = _id("CMD_ERASE")
TEST = _id("CMD_TEST")
TEST_RESULT_REQ = _id("CMD_TEST_RESULT")
SHUTDOWN = _id("CMD_SHUTDOWN")
RESET_ALARM = _id("CMD_RESET_ALARM")
SET_TIME_BVS = _id("CMD_SET_TIME_BVS")
SET_DEST_ID = _id("CMD_SET_DEST_ID")
SET_DEVICE_ID = _id("CMD_SET_DEVICE_ID")
GET_VERSION = _id("CMD_GET_VERSION")

# Команды телеметрии (КТ)
TLM_TIME_ORBIT_ATT = _id("TLM_TIME_ORBIT_ATT")
TLM_MAGFIELD = _id("TLM_MAGFIELD")
TLM_MCILWAIN = _id("TLM_MCILWAIN")

# Телеметрические сообщения (ТС)
TM_STATUS = _id("TM_STATUS")
TM_ACK = _id("TM_ACK")
TM_TELEMETRY = _id("TM_TELEMETRY")
TM_TEST_RESULT = _id("TM_TEST_RESULT")
TM_VERSION = _id("TM_VERSION")

#: An identifier the catalogue does not use, for tests that need a message to be unknown.
UNKNOWN = 0x0FFF
