"""Disk-backed store for last-used UI values (one JSON file, per-tab keys).

The installed host (tlc_compute 0.1.1.47) ships no shared config-store
helper — its built-ins each carry their own config_store.py (sam3,
image_metrics) — so this plugin does the same. Values are whole-form
snapshots keyed by tab ("import" / "train" / "submit"); a POST merges at the
tab level (last write per tab wins), so saving the Train form never touches
the Submit values. Never store secrets here — Kaggle credentials stay in the
kaggle client's own files.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

CONFIG_PATH = Path.home() / ".3lc-kaggle-plugin" / "ui_config.json"

# Reentrant: save() holds it while load() may persist a migration.
_lock = threading.RLock()

# Keys the UI/backend may persist; anything else is dropped. The three tab
# keys hold whole-form snapshots; the *_state keys are backend-written
# snapshots that back each tab's revisit view: "import_state" (Import,
# State 6 + stepper checkmark), "predict_state" / "submit_state"
# (Predict + Submit tab, re-verified against the CSV on disk).
_ALLOWED_TABS = ("import", "train", "submit", "import_state", "predict_state", "submit_state")

# One-time migrations over the persisted snapshot, keyed by a marker in
# "_migrations" so each runs exactly once per machine. device_blank_default:
# v1.2.2 changed the Device default from '0' to blank(auto), but a saved '0'
# (the old default, written on every run) overrode it forever — exactly the
# population the auto fix targeted kept the old behavior. Rewrite the exact
# string '0' once; a '0' the user types after the marker is a choice and
# persists.
_MIGRATIONS_KEY = "_migrations"


def _migrate(data: dict[str, Any]) -> bool:
    done = data.get(_MIGRATIONS_KEY)
    done = done if isinstance(done, dict) else {}
    if done.get("device_blank_default"):
        return False
    for tab in ("train", "submit"):
        values = data.get(tab)
        if isinstance(values, dict) and values.get("device") == "0":
            values["device"] = ""
    data[_MIGRATIONS_KEY] = {**done, "device_blank_default": True}
    return True


def load() -> dict[str, Any]:
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    if _migrate(data):
        with _lock:
            _write(data)
    return data


def _write(data: dict[str, Any]) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
    os.replace(tmp, CONFIG_PATH)


def save(update: dict[str, Any]) -> dict[str, Any]:
    """Merge per-tab snapshots into the stored config; return the result."""
    with _lock:
        data = load()
        _migrate(data)  # fresh store: stamp the marker before first write
        for tab, values in update.items():
            if tab in _ALLOWED_TABS and isinstance(values, dict):
                data[tab] = values
        _write(data)
        return data
