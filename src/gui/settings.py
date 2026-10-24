"""GUI state persisted between sessions in settings.json (repo root, git-ignored)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

SETTINGS_FILE = Path(__file__).resolve().parents[2] / "settings.json"

DEFAULTS = {
    "port": "",
    "poll_interval_s": 0.5,
    "window_geometry": None,               # base64 of QMainWindow.saveGeometry()
    "plot": {
        "window": "5 min",
        "follow": True,
        "visible": {"1": True, "2": True, "3": False},
    },
    # not readable from the device -> remembered here and re-applied on connect
    "toggles": {"ovp": False, "ocp": False, "beep": True, "lock": False},
    "profile": [
        {"duration": "00:00:10", "transition": "jump", "v": 0.0, "i": 0.1, "output": "on"},
        {"duration": "01:00:00", "transition": "ramp", "v": 2.0, "i": None, "output": "keep"},
    ],
}


def _merge(defaults: dict, loaded: dict) -> dict:
    """Defaults overlaid with loaded values, so new keys survive old settings files."""
    out = {}
    for key, default in defaults.items():
        value = loaded.get(key, default)
        out[key] = _merge(default, value) if isinstance(default, dict) and isinstance(value, dict) else value
    return out


def load() -> dict:
    try:
        return _merge(DEFAULTS, json.loads(SETTINGS_FILE.read_text(encoding="utf-8")))
    except FileNotFoundError:
        return _merge(DEFAULTS, {})
    except (OSError, ValueError) as e:
        log.warning("Ignoring unreadable %s: %s", SETTINGS_FILE, e)
        return _merge(DEFAULTS, {})


def save(settings: dict):
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")
