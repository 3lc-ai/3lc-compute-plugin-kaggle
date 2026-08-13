"""Disk-backed store for last-used UI values (one JSON file).

The installed host (tlc_compute 0.1.1.47) ships no shared config-store
helper — its built-ins each carry their own config_store.py (sam3,
image_metrics) — so this plugin does the same. Never store secrets here —
Kaggle credentials stay in the kaggle client's own files.

Since v1.2.6 the store holds one canonical **session** object for the facts
every tab shares — project / table name / dataset yaml / device / the slug
decision, plus explicit per-field table-URL overrides — and the per-tab keys
("train" / "submit") keep only tab-local fields. Tabs render projections of
the session; no tab owns a default. The *_state keys are backend-written
snapshots that back each tab's revisit view: "import_state" (Import, State 6
+ stepper checkmark), "predict_state" / "submit_state" (Predict + Submit
tab, re-verified against the CSV on disk AND the job store on read).

Keys retired by the session_v1 migration are REJECTED on save (ValueError →
the /config route answers 400): the only writer that still sends them is a
stale browser-cached fragment, and silently dropping its writes would be a
new silent divergence — a failing save is visible (worker log, network tab,
values that stop persisting) and the remedy is a hard refresh.
"""

from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path
from typing import Any

CONFIG_PATH = Path.home() / ".3lc-kaggle-plugin" / "ui_config.json"

# Single definition site for the shipped defaults. Every other backend site
# references these; the UI carries NO copy — GET /config always serves a
# populated session, so a fragment never needs a fallback literal.
DEFAULT_PROJECT = "exdark-competition"
DEFAULT_TABLE = "initial"

# Reentrant: save() holds it while load() may persist a migration.
_lock = threading.RLock()

# Keys the UI/backend may persist; anything else is dropped. "import" is
# retired: the Import form is the session's editor, not a store of its own.
_ALLOWED_TABS = ("session", "train", "submit", "import_state", "predict_state", "submit_state")

# Retired by session_v1 — one logical fact must not reappear under a second
# key. Kept as data (not prose) so save() can enforce it.
_RETIRED_TABS = ("import",)
_RETIRED_TAB_KEYS: dict[str, tuple[str, ...]] = {
    "train": ("train_table_url", "val_table_url", "project_name", "device"),
    "submit": ("test_table_url", "device", "competition_slug"),
    "import_state": ("project", "table_name", "dataset_yaml"),
    "submit_state": ("slug",),
}

_MIGRATIONS_KEY = "_migrations"
_SPLITS = ("train", "val", "test")


def default_session() -> dict[str, Any]:
    """The session a fresh install starts from. slug_override=None means
    "track the shipped COMPETITION_SLUG"; overrides holds only explicit
    per-field table-URL choices (hand-paste / revision picker)."""
    return {
        "project_name": DEFAULT_PROJECT,
        "table_name": DEFAULT_TABLE,
        "dataset_yaml": "",
        "device": "",
        "slug_override": None,
        "overrides": {},
    }


# ── URL helpers (migration only) ─────────────────────────────────────────
# Table URLs follow the deterministic layout
# .../projects/<project>/datasets/<dataset>/tables/<table>; both slash
# styles occur in real configs (importer writes /, yaml paths use \).

def _url_project(url: str) -> str | None:
    m = re.search(r"[\\/]projects[\\/]([^\\/]+)[\\/]datasets[\\/]", str(url))
    return m.group(1) if m else None


def _url_dataset(url: str) -> str | None:
    m = re.search(r"[\\/]datasets[\\/]([^\\/]+)[\\/]tables[\\/]", str(url))
    return m.group(1) if m else None


def _url_table(url: str) -> str | None:
    m = re.search(r"[\\/]tables[\\/]([^\\/]+)[\\/]?$", str(url).strip())
    return m.group(1) if m else None


def _url_exists(url: str) -> bool:
    """Best-effort existence check for a table URL. tlc resolves the URL the
    same way the gates do; without tlc (pytest) plain Path covers the local
    layouts real configs contain. Import is lazy — this module must stay
    cheap to import (stdlib-only) for tests and worker startup."""
    try:
        import tlc

        return bool(tlc.Url(str(url)).exists())
    except Exception:
        try:
            return Path(str(url)).exists()
        except OSError:
            return False


# ── Migrations ───────────────────────────────────────────────────────────
# One-time migrations over the persisted snapshot, keyed by markers in
# "_migrations" so each runs exactly once per machine. ORDER MATTERS and is
# fixed by the sequence in _migrate(): session_v1 folds the per-tab device
# copies into the session, so device_blank_default's '0' → '' rewrite must
# already have happened — a config that has seen neither (pre-v1.2.2 store)
# runs both, in order, in one load.


def _migrate_device_blank_default(data: dict[str, Any]) -> None:
    # v1.2.2 changed the Device default from '0' to blank(auto), but a saved
    # '0' (the old default, written on every run) overrode it forever —
    # exactly the population the auto fix targeted kept the old behavior.
    # Rewrite the exact string '0' once; a '0' typed after the marker is a
    # choice and persists.
    for tab in ("train", "submit"):
        values = data.get(tab)
        if isinstance(values, dict) and values.get("device") == "0":
            values["device"] = ""


def _migrate_session_v1(data: dict[str, Any]) -> str:
    """Fold the legacy per-tab copies of the shared facts into one session
    object. Returns the branch that decided the project/table/yaml triple —
    recorded in _migrations so a support conversation can reconstruct the
    decision from the config file alone.

    Precedence for the triple:
      1. import_state.* — IF the snapshot's three table URLs resolve on
         disk. This is the only copy backed by verifiable artifacts.
      2. import.* — the form's last settled values (the user's last
         expressed intent; the next gate re-verifies immediately).
      3. The shipped defaults.

    Table-URL keys: a URL whose project segment matches the resolved session
    project is an intentional same-project choice (hand-paste or revision
    picker — e.g. a fixed-labels revision) and is carried into
    session.overrides unless it equals what derivation would produce anyway.
    A URL in any OTHER project is the cross-project mixture this migration
    exists to end — dropped, as is one whose project can't be parsed.
    """
    legacy = [k for k in ("import", "train", "submit", "import_state") if isinstance(data.get(k), dict)]
    if not legacy:
        return "fresh"

    imp = data.get("import") if isinstance(data.get("import"), dict) else {}
    ist = data.get("import_state") if isinstance(data.get("import_state"), dict) else {}
    tables = ist.get("tables") if isinstance(ist.get("tables"), dict) else {}
    urls = [str((tables.get(s) or {}).get("url") or "") for s in _SPLITS]

    if tables and all(urls) and all(_url_exists(u) for u in urls):
        branch = "import_state"
        project = str(ist.get("project") or imp.get("project_name") or DEFAULT_PROJECT).strip()
        table_name = str(ist.get("table_name") or imp.get("table_name") or DEFAULT_TABLE).strip()
        dataset_yaml = str(ist.get("dataset_yaml") or imp.get("dataset_yaml") or "").strip()
    elif any(imp.get(k) for k in ("project_name", "table_name", "dataset_yaml")):
        branch = "import_form"
        project = str(imp.get("project_name") or DEFAULT_PROJECT).strip()
        table_name = str(imp.get("table_name") or DEFAULT_TABLE).strip()
        dataset_yaml = str(imp.get("dataset_yaml") or "").strip()
    else:
        branch = "default"
        project, table_name, dataset_yaml = DEFAULT_PROJECT, DEFAULT_TABLE, ""

    # One machine fact: first non-empty of the two legacy device copies
    # (both already post-device_blank_default — see _migrate ordering).
    device = ""
    for tab in ("train", "submit"):
        v = str((data.get(tab) or {}).get("device") or "").strip()
        if v:
            device = v
            break

    # Slug decision: persist only a deliberate divergence from the shipped
    # constant. The current constant and every retired slug collapse to
    # None = "track whatever the installed version ships" (DP-04).
    from tlc_plugin_kaggle import predictor

    raw_slug = str((data.get("submit") or {}).get("competition_slug") or "").strip()
    if raw_slug and raw_slug != predictor.COMPETITION_SLUG and raw_slug not in predictor.RETIRED_SLUGS:
        slug_override = raw_slug
    else:
        slug_override = None

    from tlc_plugin_kaggle.importer import DATASET_PREFIX

    overrides: dict[str, str] = {}
    for tab, key, split in (
        ("train", "train_table_url", "train"),
        ("train", "val_table_url", "val"),
        ("submit", "test_table_url", "test"),
    ):
        url = str((data.get(tab) or {}).get(key) or "").strip()
        if not url or _url_project(url) != project:
            continue  # cross-project mixture or unparseable: dropped by design
        if _url_dataset(url) == f"{DATASET_PREFIX}_{split}" and _url_table(url) == table_name:
            continue  # exactly what derivation yields: no override needed
        overrides[key] = url

    for tab, keys in _RETIRED_TAB_KEYS.items():
        values = data.get(tab)
        if isinstance(values, dict):
            for k in keys:
                values.pop(k, None)
    data.pop("import", None)

    data["session"] = {
        "project_name": project,
        "table_name": table_name,
        "dataset_yaml": dataset_yaml,
        "device": device,
        "slug_override": slug_override,
        "overrides": overrides,
    }
    return branch


def _migrate(data: dict[str, Any]) -> bool:
    """Run pending migrations in their fixed order. Returns True if any ran
    (caller persists). device_blank_default keeps its boolean marker;
    session_v1's marker is the branch string that decided the triple
    ("import_state" / "import_form" / "default" / "fresh") — truthy, so it
    doubles as the done flag."""
    done = data.get(_MIGRATIONS_KEY)
    done = dict(done) if isinstance(done, dict) else {}
    changed = False
    if not done.get("device_blank_default"):
        _migrate_device_blank_default(data)
        done["device_blank_default"] = True
        changed = True
    if not done.get("session_v1"):
        done["session_v1"] = _migrate_session_v1(data)
        changed = True
    if changed:
        data[_MIGRATIONS_KEY] = done
    return changed


def load() -> dict[str, Any]:
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    if _migrate(data):
        # The one deliberate read-path write in the plugin: a one-shot,
        # marker-guarded migration flush under the store lock.
        with _lock:
            _write(data)
    return data


def _write(data: dict[str, Any]) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
    os.replace(tmp, CONFIG_PATH)


def _retired_keys_in(update: dict[str, Any]) -> list[str]:
    bad = [tab for tab in _RETIRED_TABS if tab in update]
    for tab, keys in _RETIRED_TAB_KEYS.items():
        values = update.get(tab)
        if isinstance(values, dict):
            bad.extend(f"{tab}.{k}" for k in keys if k in values)
    return bad


def save(update: dict[str, Any]) -> dict[str, Any]:
    """Merge per-tab snapshots into the stored config; return the result.

    Raises ValueError if the update carries keys the session_v1 migration
    retired — nothing current writes them, so their presence means a stale
    cached fragment; rejecting the whole POST keeps the store coherent and
    makes the skew visible instead of silently re-creating the duplication.
    """
    bad = _retired_keys_in(update)
    if bad:
        raise ValueError(
            "config update contains retired keys (" + ", ".join(sorted(bad)) + "); "
            "these moved into the 'session' object in v1.2.6. If this write came "
            "from the plugin page, the browser is holding a stale fragment — "
            "hard-refresh the page."
        )
    with _lock:
        data = load()
        _migrate(data)  # fresh store: stamp the markers before first write
        for tab, values in update.items():
            if tab in _ALLOWED_TABS and isinstance(values, dict):
                data[tab] = values
        _write(data)
        return data
