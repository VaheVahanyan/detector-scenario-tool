from __future__ import annotations

from dataclasses import dataclass

#: Not a protocol category: text the board printed onto the bus.
#:
#: In some firmware configurations the МК sends its own debug output over CAN, with identifiers
#: that mean nothing to `Протокол_CAN_ГС_v2_1_Спутникс`. Such a frame is not an answer from the
#: НА — treating it as one would let a stray printf satisfy a wait step or break log correlation —
#: so it is captured under this category, rendered as text, and ignored by everything that reasons
#: about responses. `KU`/`KT`/`TS` stay the three protocol categories; this is a fourth code that
#: only ever appears on a `LogRecord`.
LOG_CATEGORY = "LOG"

#: Share of decodable, printable characters above which a payload is shown as text rather than hex.
#: Low enough for a line that starts mid-UTF-8 sequence (the МК splits long text across frames),
#: high enough that packed telemetry does not read as a sentence.
TEXT_RATIO = 0.75

#: Control characters that survive into the rendered text; everything else becomes this.
_KEPT_CONTROLS = "\r\n\t"
_UNPRINTABLE = "·"


@dataclass
class LogRecord:
    timestamp_ms: int
    direction: str          # "tx" | "rx"
    category: str           # "KU" | "KT" | "TS" | "LOG"
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

    @property
    def is_board_log(self) -> bool:
        """True for the board's own text output, which is never a protocol message."""
        return self.category == LOG_CATEGORY


def looks_like_text(payload: bytes) -> bool:
    """Whether a payload is worth showing as text at all.

    The judgement is made on **bytes, not on decoded characters**, and deliberately so: the МК
    splits a long line across 6-byte frames, so a cyrillic fragment routinely begins mid-sequence
    and half of it decodes to replacement characters. Counting those as "not text" would hide the
    very lines this exists to show. A byte counts as text if it is printable ASCII, a kept control
    character, or anything above 7 bit — which is what a UTF-8 lead or continuation byte looks
    like. Binary telemetry, which is mostly zeroes, control bytes and `AAh` padding, still fails.
    """
    data = payload.rstrip(b"\x00")
    if not data:
        return False

    kept = {ord(ch) for ch in _KEPT_CONTROLS}
    texty = sum(1 for b in data if 0x20 <= b <= 0x7E or b in kept or b >= 0x80)
    return texty / len(data) >= TEXT_RATIO


def decode_log_text(payload: bytes) -> str:
    """The board's text, with control characters made visible.

    Trailing NULs are padding rather than content — the МК pads a frame out to its DLC — so they
    are dropped. Line breaks are kept: the detail pane shows them, the table folds them.
    """
    text = payload.rstrip(b"\x00").decode("utf-8", errors="replace")
    return "".join(
        ch if (ch in _KEPT_CONTROLS or ch.isprintable()) else _UNPRINTABLE for ch in text
    ).strip()


def log_text_line(payload: bytes) -> str:
    """The same text folded onto one line, for a table cell."""
    return " ".join(decode_log_text(payload).split())
