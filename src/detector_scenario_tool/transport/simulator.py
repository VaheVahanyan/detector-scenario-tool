"""A stand-in for the detector, built from the protocol definitions.

This is what makes a dry run worth doing: it applies the same per-mode validity table the analyzer
uses, so running a scenario without hardware still exercises acknowledgement matching, error codes
and mode transitions rather than just checking that bytes were produced.

It is a model of the *protocol*, not of the firmware — it does not erase anything, time anything,
or produce science data.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from detector_scenario_tool.protocol import registry
from detector_scenario_tool.protocol.errors import AckErrorCode, encode_ack_status
from detector_scenario_tool.protocol.fields import AckBehaviour, pack_message, validate_payload
from detector_scenario_tool.protocol.fields import unpack_message
from detector_scenario_tool.protocol.modes import TELEMETRY_MODE_CODES, Mode

ACK_MSG_ID = 0x0201
STATUS_MSG_ID = 0x0200


@dataclass(frozen=True)
class SimulatedReply:
    msg_id: int
    payload: bytes


@dataclass
class DetectorSimulator:
    """Answers control commands the way `Обработка_команд_CAN_NATALIA` says the НА should."""

    mode: Mode = Mode.DUTY
    previous_mode: Mode = Mode.INIT
    #: Set to make the simulator reject everything with this code, to exercise failure handling.
    forced_error: AckErrorCode | None = None
    #: Commands whose acknowledgement should simply not be sent, to exercise timeouts.
    silent_for: set[int] = field(default_factory=set)
    received: list[tuple[int, bytes]] = field(default_factory=list)

    def reset(self) -> None:
        self.mode = Mode.DUTY
        self.previous_mode = Mode.INIT
        self.received.clear()

    def handle(self, msg_id: int, payload: bytes) -> list[SimulatedReply]:
        self.received.append((msg_id, bytes(payload)))

        spec = registry.find("KU", msg_id) or registry.find("KT", msg_id)
        if spec is None:
            return [self._ack(msg_id, AckErrorCode.ERR_MSG_ID)]

        if spec.custom:
            # The tool registers user-defined messages so it can pack and display them; the
            # firmware has only the catalogue, so it answers ERR_MSG_ID. Modelling that is the
            # whole point of being able to author one.
            if spec.category == "KT":
                return []
            return [self._ack(msg_id, AckErrorCode.ERR_MSG_ID)]

        if spec.category == "KT":
            # §2.3: telemetry commands are never acknowledged. Outside OBSERVE they are simply
            # dropped, which is exactly what "no reply" models.
            return []

        if msg_id in self.silent_for:
            return []

        if self.forced_error is not None:
            return [self._ack(msg_id, self.forced_error)]

        if self.mode not in spec.allowed_modes:
            return [self._ack(msg_id, AckErrorCode.ERR_MODE)]

        if self._payload_is_invalid(spec, payload):
            return [self._ack(msg_id, AckErrorCode.ERR_CONTENT)]

        replies = [self._ack(msg_id, AckErrorCode.OK, payload=payload, spec=spec)]

        if spec.changes_mode_to is not None and spec.changes_mode_to is not self.mode:
            self.previous_mode, self.mode = self.mode, spec.changes_mode_to

        replies.extend(self._follow_ups(spec))
        return replies

    # -- replies -----------------------------------------------------------------------

    def _ack(
            self,
            msg_id: int,
            code: AckErrorCode,
            payload: bytes = b"",
            spec=None,
    ) -> SimulatedReply:
        ack_spec = registry.find("TS", ACK_MSG_ID)
        values = {
            "acknowledged_msg_id": msg_id,
            "rejected": 1 if code is not AckErrorCode.OK else 0,
            "error_code": int(code),
            # §4.2 note 1: the packet count is only meaningful for the CMD_DUMP acknowledgement.
            "packet_count": 0xAAAAAA,
        }

        if spec is not None and spec.symbol == "CMD_DUMP" and code is AckErrorCode.OK:
            requested = unpack_message(spec, payload).get("requested_packet_count", 0)
            values["packet_count"] = requested

        return SimulatedReply(ACK_MSG_ID, pack_message(ack_spec, values))

    def _follow_ups(self, spec) -> list[SimulatedReply]:
        replies = []
        for response in spec.follow_up:
            if response.is_ack or not response.guaranteed:
                continue
            replies.append(
                SimulatedReply(response.msg_id, self._telemetry_payload(response.msg_id))
            )
        return replies

    def _telemetry_payload(self, msg_id: int) -> bytes:
        spec = registry.find("TS", msg_id)
        values = dict(spec.default_payload())

        if msg_id == STATUS_MSG_ID or msg_id == 0x0202:
            values["previous_mode"] = TELEMETRY_MODE_CODES[self.previous_mode]
            values["current_mode"] = TELEMETRY_MODE_CODES[self.mode]

        return pack_message(spec, values)

    @staticmethod
    def _payload_is_invalid(spec, payload: bytes) -> bool:
        if len(payload) != spec.length:
            return True
        return bool(validate_payload(spec, unpack_message(spec, payload)))


def encoded_ack_status(rejected: bool, code: AckErrorCode) -> int:
    """Convenience for tests that build an acknowledgement byte by hand."""
    return encode_ack_status(rejected, code)
