from __future__ import annotations

from dataclasses import dataclass


@dataclass
class LogRecord:
    timestamp_ms: int
    direction: str          # "tx" | "rx"
    category: str           # "KU" | "KT" | "TS"
    msg_id: int
    payload: bytes
    source: str = ""        # "host" | "detector" | "board" | "l476" | "l496" | etc
    note: str = ""
    #: Wire detail, filled in by the live transport. A long message spans several frames, so this
    #: is the identifier of the first one.
    can_id: int | None = None
    frame_count: int = 1
    #: False when reassembly or decoding failed — raw view has to show those rows, not drop them.
    valid: bool = True

    @property
    def can_id_hex(self) -> str:
        return "-" if self.can_id is None else f"0x{self.can_id:03X}"

    @property
    def byte_count(self) -> int:
        return len(self.payload)

    @property
    def payload_hex(self) -> str:
        return " ".join(f"{b:02X}" for b in self.payload)