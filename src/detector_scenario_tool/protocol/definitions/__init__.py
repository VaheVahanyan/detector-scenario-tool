from detector_scenario_tool.protocol.definitions.control_commands import CONTROL_COMMANDS
from detector_scenario_tool.protocol.definitions.telemetry_commands import TELEMETRY_COMMANDS
from detector_scenario_tool.protocol.definitions.telemetry_messages import TELEMETRY_MESSAGES

#: Every message the tool knows about, in document order.
ALL_MESSAGE_DEFS = CONTROL_COMMANDS + TELEMETRY_COMMANDS + TELEMETRY_MESSAGES

__all__ = [
    "ALL_MESSAGE_DEFS",
    "CONTROL_COMMANDS",
    "TELEMETRY_COMMANDS",
    "TELEMETRY_MESSAGES",
]
