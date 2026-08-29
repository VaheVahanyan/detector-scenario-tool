"""Who produced a log record.

The names are written into saved logs (`src=`), so they are serialisation values as much as
display ones. `l476` / `l496` are the two microcontrollers as their own firmware names them.
"""

from __future__ import annotations

#: This application, when the frame went out over CAN from here.
HOST_SOURCE = "host"
#: The controller board — its serial log, and its own debug output on the CAN bus.
BOARD_SOURCE = "board"
#: The payload (НА), i.e. anything the protocol catalogue recognises as telemetry.
DETECTOR_SOURCE = "detector"


def normalize_log_source(source: str | None) -> str:
    s = (source or "").strip().lower()

    if s in {"l476", "board", "controller"}:
        return "board"

    if s in {"l496", "detector"}:
        return "detector"

    return s
