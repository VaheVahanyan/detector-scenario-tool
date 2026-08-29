"""User settings that outlive a session.

Only things the user would be annoyed to retype: which adapter, which channel, which language.
Scenario content never lives here — that belongs in the scenario file.
"""

from __future__ import annotations

import json
from pathlib import Path

from detector_scenario_tool.transport.backend import ConnectionSettings
from detector_scenario_tool.transport_defaults import (
    DEFAULT_BITRATE,
    DEFAULT_BOARD_LOG_ID,
    DEFAULT_BVS_ADDRESS,
    DEFAULT_NA_ADDRESS,
)

APP_DIR_NAME = "detector-scenario-tool"


def settings_path() -> Path:
    """Follows the XDG base directory spec, with the documented fallback."""
    import os

    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / APP_DIR_NAME / "settings.json"


def load() -> dict:
    path = settings_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # A corrupt settings file must never stop the application from starting.
        return {}


def save(data: dict) -> None:
    path = settings_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def load_connection_settings() -> ConnectionSettings:
    raw = load().get("connection", {})
    return ConnectionSettings(
        backend=raw.get("backend", "virtual"),
        channel=raw.get("channel", ""),
        bitrate=int(raw.get("bitrate", DEFAULT_BITRATE)),
        extended_ids=bool(raw.get("extended_ids", False)),
        na_address=int(raw.get("na_address", DEFAULT_NA_ADDRESS)),
        bvs_address=int(raw.get("bvs_address", DEFAULT_BVS_ADDRESS)),
        board_log_id=int(raw.get("board_log_id", DEFAULT_BOARD_LOG_ID)),
    )


def save_connection_settings(settings: ConnectionSettings) -> None:
    data = load()
    data["connection"] = {
        "backend": settings.backend,
        "channel": settings.channel,
        "bitrate": settings.bitrate,
        "extended_ids": settings.extended_ids,
        "na_address": settings.na_address,
        "bvs_address": settings.bvs_address,
        "board_log_id": settings.board_log_id,
    }
    save(data)


def load_language(default: str = "ru") -> str:
    return load().get("language", default)


def save_language(language: str) -> None:
    data = load()
    data["language"] = language
    save(data)
