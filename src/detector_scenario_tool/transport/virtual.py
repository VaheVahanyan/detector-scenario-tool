"""A backend with no hardware behind it.

Two uses: the default *dry run*, where a `DetectorSimulator` answers as the НА would, and tests,
which can drive it deterministically.
"""

from __future__ import annotations

from collections import deque

from detector_scenario_tool.transport.backend import CanBackend, ConnectionSettings
from detector_scenario_tool.transport.simulator import DetectorSimulator
from detector_scenario_tool.transport.unican import (
    CanFrame,
    Reassembler,
    UniCanMessage,
    encode,
)
from detector_scenario_tool.transport_defaults import DEFAULT_BVS_ADDRESS, DEFAULT_NA_ADDRESS


class VirtualBackend(CanBackend):
    def __init__(
            self,
            settings: ConnectionSettings | None = None,
            simulator: DetectorSimulator | None = None,
            na_address: int | None = None,
            bvs_address: int | None = None,
    ) -> None:
        super().__init__(settings or ConnectionSettings(backend="virtual"))
        self.simulator = simulator if simulator is not None else DetectorSimulator()
        # The connection says who is on the bus; the arguments stay for tests that want to answer
        # from somewhere unexpected.
        self.na_address = self.settings.na_address if na_address is None else na_address
        self.bvs_address = self.settings.bvs_address if bvs_address is None else bvs_address

        self._incoming: deque[CanFrame] = deque()
        self._sent: list[CanFrame] = []
        self._reassembler = Reassembler(extended=self.settings.extended_ids)

    @property
    def is_simulated(self) -> bool:
        return True

    @property
    def sent_frames(self) -> list[CanFrame]:
        return list(self._sent)

    def open(self) -> None:
        self._open = True
        self._incoming.clear()
        self._sent.clear()
        self._reassembler.reset()

    def close(self) -> None:
        self._open = False

    def send(self, frame: CanFrame) -> None:
        if not self._open:
            raise RuntimeError("backend is not open")

        self._sent.append(frame)

        decoded = self._reassembler.feed(frame)
        if not isinstance(decoded, UniCanMessage):
            return

        for reply in self.simulator.handle(decoded.msg_id, decoded.payload):
            self._incoming.extend(
                encode(
                    reply.msg_id,
                    reply.payload,
                    destination=self.bvs_address,
                    source=self.na_address,
                    extended=self.settings.extended_ids,
                )
            )

    def receive(self, timeout: float = 0.0) -> CanFrame | None:
        # Replies are produced synchronously by send(), so a timeout would only ever be spent
        # waiting for nothing.
        return self._incoming.popleft() if self._incoming else None

    def inject(self, frames: list[CanFrame]) -> None:
        """Queue frames as if the bus had produced them; for tests and log replay."""
        self._incoming.extend(frames)
