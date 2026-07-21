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

_lock = threading.Lock()

# Keys the UI/backend may persist; anything else is dropped. The three tab
# keys hold whole-form snapshots; "import_state" is the backend-written
# last-successful-import snapshot that backs the Import tab's revisit view
# (State 6) and the stepper checkmark.
_ALLOWED_TABS = ("import", "train", "submit", "import_state")


def load() -> dict[str, Any]:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save(update: dict[str, Any]) -> dict[str, Any]:
    """Merge per-tab snapshots into the stored config; return the result."""
    with _lock:
        data = load()
        for tab, values in update.items():
            if tab in _ALLOWED_TABS and isinstance(values, dict):
                data[tab] = values
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = CONFIG_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
        os.replace(tmp, CONFIG_PATH)
        return data
