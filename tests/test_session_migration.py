"""session_v1 against the two REAL configs (sanitized), both URL-resolution
branches each, plus the migration ordering and B1 override preservation.

The corrected precedence under test: import_state's copy wins ONLY when its
recorded table URLs resolve on disk (the only copy backed by verifiable
artifacts); otherwise the import form's last settled values; otherwise the
shipped defaults. The newstack fixture is the config that falsified the
import-form-first rule: its form says exdark-competition while the tables
live in v124check2.
"""

from __future__ import annotations

from conftest import fixture_config, materialize_tables, write_config

from tlc_plugin_kaggle import constants

RETIRED = {
    "train": ("train_table_url", "val_table_url", "project_name", "device"),
    "submit": ("test_table_url", "device", "competition_slug"),
    "import_state": ("project", "table_name", "dataset_yaml"),
    "submit_state": ("slug",),
}


def assert_retired_gone(data):
    assert "import" not in data
    for tab, keys in RETIRED.items():
        if tab in data:
            for key in keys:
                assert key not in data[tab], f"{tab}.{key} survived the migration"


def migrate(store, tmp_path, name, resolve_tables):
    cfg = fixture_config(name, tmp_path)
    if resolve_tables:
        materialize_tables(cfg)
    write_config(store, cfg)
    return store.load()


# ── oldstack: July 0.1.x config — no _migrations key at all ─────────────


def test_oldstack_snapshot_branch(store, tmp_path):
    data = migrate(store, tmp_path, "oldstack", resolve_tables=True)
    assert data["_migrations"]["session_v1"] == "import_state"
    sess = data["session"]
    assert sess["project_name"] == "exdark-competition-test-init3"
    assert sess["table_name"] == "initial"
    assert sess["dataset_yaml"].endswith("dataset.yaml")
    assert sess["slug_override"] is None  # fixture slug == shipped constant
    # The live DP-01 mixture: train/submit URLs point at exdark-competition,
    # not the session project — dropped by design, never carried as overrides.
    assert sess["overrides"] == {}
    assert_retired_gone(data)


def test_oldstack_form_branch_when_tables_missing(store, tmp_path, caplog):
    import logging

    with caplog.at_level(logging.WARNING, logger="tlc_plugin_kaggle.config_store"):
        data = migrate(store, tmp_path, "oldstack", resolve_tables=False)
    # Same project value either way in this config (form matched snapshot);
    # the marker records which rule actually decided — and WHY the snapshot
    # lost (tables existed in the config but not on disk at that moment).
    assert data["_migrations"]["session_v1"] == "import_form_urls_unresolved"
    assert data["session"]["project_name"] == "exdark-competition-test-init3"
    # D3: the permanent branch choice logs its evidence.
    assert "session_v1" in caplog.text
    assert "exdark-competition-test-init3/datasets/exdark_train/tables/initial" in caplog.text
    assert_retired_gone(data)


def test_session_v1_runs_after_device_blank_default(store, tmp_path):
    # The ordering assertion: oldstack carries device "0" in BOTH tabs and
    # has seen NEITHER migration. device_blank_default must rewrite '0'->''
    # before session_v1 folds the copies, or the session would resurrect
    # the saved-device-'0' bug the earlier migration killed.
    data = migrate(store, tmp_path, "oldstack", resolve_tables=True)
    assert data["_migrations"]["device_blank_default"] is True
    assert data["session"]["device"] == ""


# ── newstack: current v1.2.5 config — three-way project divergence ──────


def test_newstack_snapshot_wins_over_edited_form(store, tmp_path):
    data = migrate(store, tmp_path, "newstack", resolve_tables=True)
    assert data["_migrations"]["session_v1"] == "import_state"
    sess = data["session"]
    # Tables live in v124check2; the form was edited to exdark-competition
    # afterwards. The doc's import-form-first rule would have migrated to a
    # project containing no tables — reproducing DP-01 in the migration.
    assert sess["project_name"] == "v124check2"
    assert sess["device"] == ""
    assert sess["slug_override"] is None
    assert sess["overrides"] == {}  # persisted URLs point at exdark-competition
    assert data["_migrations"]["device_blank_default"] is True  # untouched marker
    assert_retired_gone(data)


def test_newstack_form_branch_when_tables_missing(store, tmp_path):
    data = migrate(store, tmp_path, "newstack", resolve_tables=False)
    assert data["_migrations"]["session_v1"] == "import_form_urls_unresolved"
    # No verifiable artifacts: the form's last expressed intent wins; the
    # Train gate re-verifies immediately and walks the user to re-import.
    assert data["session"]["project_name"] == "exdark-competition"
    assert_retired_gone(data)


def test_snapshot_strings_disagreeing_with_urls_lose_to_the_artifact(store, tmp_path):
    # D1: the branch's justification is the verified artifact, so the
    # artifact must decide. A snapshot whose string fields disagree with
    # its own tables' URLs is the exact snapshot-vs-value class this
    # release retires — the URL segments win.
    cfg = fixture_config("newstack", tmp_path)
    materialize_tables(cfg)
    cfg["import_state"]["project"] = "wrong-string-project"
    cfg["import_state"]["table_name"] = "wrong-string-table"
    write_config(store, cfg)
    data = store.load()
    assert data["_migrations"]["session_v1"] == "import_state"
    assert data["session"]["project_name"] == "v124check2"
    assert data["session"]["table_name"] == "initial"


def test_empty_snapshot_project_string_still_uses_artifact(store, tmp_path):
    # D1's second half: an empty ist["project"] must not silently fall
    # through to the form value while recording branch="import_state".
    cfg = fixture_config("newstack", tmp_path)
    materialize_tables(cfg)
    cfg["import_state"]["project"] = ""
    write_config(store, cfg)
    data = store.load()
    assert data["_migrations"]["session_v1"] == "import_state"
    assert data["session"]["project_name"] == "v124check2"  # not the form's exdark-competition


def test_form_branch_without_any_snapshot(store, tmp_path):
    write_config(store, {"import": {"project_name": "probe-x", "table_name": "r2", "dataset_yaml": ""}})
    data = store.load()
    assert data["_migrations"]["session_v1"] == "import_form_no_snapshot"
    sess = data["session"]
    assert sess["project_name"] == "probe-x"
    assert sess["table_name"] == "r2"


# ── B1: same-project URL overrides survive; cross-project ones don't ────


def test_same_project_revision_override_preserved(store, tmp_path):
    cfg = fixture_config("newstack", tmp_path)
    materialize_tables(cfg)
    # A revision-picker choice in the CORRECT project (fixed-labels Loop
    # progress): same project, non-default table revision.
    round2 = cfg["import_state"]["tables"]["train"]["url"].replace("/tables/initial", "/tables/round2")
    cfg["train"]["train_table_url"] = round2
    write_config(store, cfg)
    sess = store.load()["session"]
    assert sess["overrides"] == {"train_table_url": round2}


def test_override_equal_to_derived_default_not_stored(store, tmp_path):
    cfg = fixture_config("newstack", tmp_path)
    materialize_tables(cfg)
    # Same project AND exactly what derivation would produce: no override.
    cfg["train"]["train_table_url"] = cfg["import_state"]["tables"]["train"]["url"]
    write_config(store, cfg)
    assert store.load()["session"]["overrides"] == {}


def test_unparseable_url_dropped(store, tmp_path):
    cfg = fixture_config("newstack", tmp_path)
    materialize_tables(cfg)
    cfg["train"]["train_table_url"] = "not-a-table-url"
    write_config(store, cfg)
    assert store.load()["session"]["overrides"] == {}


# ── general properties ───────────────────────────────────────────────────


def test_migration_is_idempotent(store, tmp_path):
    migrate(store, tmp_path, "oldstack", resolve_tables=True)
    first = store.CONFIG_PATH.read_text(encoding="utf-8")
    store.load()  # second load: markers present, nothing runs, no write
    assert store.CONFIG_PATH.read_text(encoding="utf-8") == first


def test_default_branch_without_import_facts(store, tmp_path):
    write_config(store, {"train": {"epochs": "5", "device": "0"}})
    data = store.load()
    assert data["_migrations"]["session_v1"] == "default"
    sess = data["session"]
    assert sess["project_name"] == constants.DEFAULT_PROJECT
    assert sess["table_name"] == constants.DEFAULT_TABLE
    assert sess["device"] == ""  # '0' rewritten before the fold
