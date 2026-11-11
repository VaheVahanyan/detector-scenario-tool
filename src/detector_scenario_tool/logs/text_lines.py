"""Cutting a serial byte stream into the board's text lines.

The board's log backends (`BSP/UART/src/log_backend_{lpuart1,usart2,ftdi}.c`) all go through
`debug_log.c`, which writes `\\r\\n` for every newline — so a line ends where the firmware says it
does. Two things still need handling:

* `debug_log_write_u32_inline` prints a number with no newline at all, so an unterminated tail has
  to come out once the board has been quiet for `LINE_TIMEOUT_MS`;
* a stream that is not text (the FTDI port carries science data in DUMP) has no newlines to speak
  of, so a line is cut at `MAX_LINE_BYTES` rather than accumulating for ever.

No Qt and no I/O: `services/serial_log_controller.py` and the packet monitor feed it bytes.
"""

from __future__ import annotations

import time
from typing import Callable


class TextLineSplitter:
    LINE_TIMEOUT_MS = 250
    MAX_LINE_BYTES = 4096

    def __init__(self, clock: Callable[[], float] | None = None) -> None:
        self._clock = clock or (lambda: time.monotonic() * 1000.0)
        self._buffer = bytearray()
        self._last_ms = 0.0

    def now_ms(self) -> int:
        return int(self._clock())

    @property
    def pending(self) -> int:
        return len(self._buffer)

    def reset(self) -> None:
        self._buffer.clear()

    def feed(self, data: bytes) -> list[bytes]:
        """Complete lines, without their terminator."""
        if not data:
            return []
        self._last_ms = self._clock()
        self._buffer.extend(data)

        lines: list[bytes] = []
        while True:
            end = self._buffer.find(b"\n")
            if end < 0:
                break
            lines.append(bytes(self._buffer[:end]).rstrip(b"\r"))
            del self._buffer[:end + 1]

        while len(self._buffer) >= self.MAX_LINE_BYTES:
            lines.append(bytes(self._buffer[:self.MAX_LINE_BYTES]))
            del self._buffer[:self.MAX_LINE_BYTES]

        return lines

    def flush(self, force: bool = False) -> list[bytes]:
        """The unterminated tail, once nothing has arrived for a while (or now, if forced)."""
        if not self._buffer:
            return []
        if not force and (self._clock() - self._last_ms) < self.LINE_TIMEOUT_MS:
            return []
        line = bytes(self._buffer).rstrip(b"\r")
        self._buffer.clear()
        return [line]
