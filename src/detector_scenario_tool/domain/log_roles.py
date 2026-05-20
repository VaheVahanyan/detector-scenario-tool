from __future__ import annotations


def normalize_log_source(source: str | None) -> str:
    s = (source or "").strip().lower()

    if s in {"l476", "board", "controller"}:
        return "board"

    if s in {"l496", "detector"}:
        return "detector"

    return s
