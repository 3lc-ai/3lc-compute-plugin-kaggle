"""config_store basics: merge semantics, allowlist, atomicity, markers,
and the retired-key rejection (the stale-fragment guard)."""

from __future__ import annotations

import pytest

from conftest import write_config


def test_load_missing_file_is_empty(store):
    assert store.load() == {}


def test_save_merges_per_tab(store):
    store.save({"train": {"epochs": "5"}})
    store.save({"submit": {"conf": "0.3"}})
    data = store.load()
    assert data["train"] == {"epochs": "5"}
    assert data["submit"] == {"conf": "0.3"}


def test_save_replaces_whole_tab(store):
    store.save({"train": {"epochs": "5", "batch": "16"}})
    store.save({"train": {"epochs": "7"}})
    assert store.load()["train"] == {"epochs": "7"}


def test_save_drops_unknown_tabs(store):
    store.save({"bogus": {"x": 1}, "train": {"epochs": "5"}})
    data = store.load()
    assert "bogus" not in data
    assert data["train"] == {"epochs": "5"}


def test_fresh_save_stamps_markers_in_order(store):
    store.save({"train": {"epochs": "5"}})
    mig = store.load()["_migrations"]
    assert mig["device_blank_default"] is True
    assert mig["session_v1"] == "fresh"


def test_no_tmp_file_left_behind(store):
    store.save({"train": {"epochs": "5"}})
    assert not store.CONFIG_PATH.with_suffix(".json.tmp").exists()


@pytest.mark.parametrize(
    ("tab", "key"),
    [
        ("train", "train_table_url"),
        ("train", "val_table_url"),
        ("train", "project_name"),
        ("train", "device"),
        ("submit", "test_table_url"),
        ("submit", "device"),
        ("submit", "competition_slug"),
        ("import_state", "project"),
        ("import_state", "table_name"),
        ("import_state", "dataset_yaml"),
        ("submit_state", "slug"),
    ],
)
def test_save_rejects_retired_fields(store, tab, key):
    with pytest.raises(ValueError, match=key):
        store.save({tab: {key: "x"}})


def test_save_rejects_retired_import_tab(store):
    with pytest.raises(ValueError, match="import"):
        store.save({"import": {"project_name": "x"}})


def test_rejected_save_writes_nothing(store):
    write_config(store, {"train": {"epochs": "3"}, "_migrations": {"device_blank_default": True, "session_v1": "fresh"}})
    before = store.CONFIG_PATH.read_text(encoding="utf-8")
    with pytest.raises(ValueError):
        store.save({"train": {"epochs": "9", "project_name": "x"}})
    assert store.CONFIG_PATH.read_text(encoding="utf-8") == before


def test_session_tab_is_persistable(store):
    sess = store.default_session()
    sess["project_name"] = "probe-x"
    store.save({"session": sess})
    assert store.load()["session"]["project_name"] == "probe-x"
