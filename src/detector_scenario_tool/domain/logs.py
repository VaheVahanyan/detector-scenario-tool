from __future__ import annotations

from dataclasses import dataclass


@dataclass
class LogRecord:
    timestamp_ms: int
    direction: str          # "tx" | "rx"
    category: str           # "KU" | "KT" | "TS"
    msg_id: int
    payload: bytes
    source: str = ""        # "l476" | "l496" | "controller" | "detector" | etc
    note: str = ""

    @property
    def payload_hex(self) -> str:
        return " ".join(f"{b:02X}" for b in self.payload)