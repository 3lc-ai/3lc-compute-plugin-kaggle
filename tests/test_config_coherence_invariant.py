"""The invariant that codifies exit_gate_125 C1 permanently: after
migration, the config names exactly one project (and one table name, one
device, one slug decision) across all INTENT keys — session plus its
overrides. import_state.tables is excluded by scope: it is a snapshot
artifact of what the last import DID, validated against disk on every read
(verified_import_state), not a statement of current intent.

Under the session design this is nearly vacuous — which is the desired end
state: the invariant holds by construction, and this test keeps it that way.
"""

from __future__ import annotations

import pytest

from conftest import fixture_config, materialize_tables, write_config

from tlc_plugin_kaggle.config_store import _url_project


def walk_keys(node, path=""):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from walk_keys(v, f"{path}.{k}" if path else k)
    else:
        yield path, node


@pytest.mark.parametrize("name", ["oldstack", "newstack"])
def test_config_coherence_invariant(store, tmp_path, name):
    cfg = fixture_config(name, tmp_path)
    materialize_tables(cfg)
    write_config(store, cfg)
    data = store.load()
    sess = data["session"]

    # One project across all intent keys.
    projects = {sess["project_name"]}
    projects |= {_url_project(u) for u in sess["overrides"].values()}
    assert len(projects) == 1

    # The shared facts exist under exactly one key each: no field named
    # device/slug/competition_slug/project_name/*_table_url anywhere
    # outside the session object (import_state.tables excluded by scope).
    for path, _value in walk_keys(data):
        if path.startswith(("session.", "import_state.tables.")):
            continue
        leaf = path.rsplit(".", 1)[-1]
        assert leaf not in {
            "device", "slug", "competition_slug", "project_name", "project",
            "table_name", "train_table_url", "val_table_url", "test_table_url",
            "dataset_yaml",
        }, f"duplicate copy of a session fact at {path}"

    # And the session itself is complete.
    assert set(sess) == {
        "project_name", "table_name", "dataset_yaml", "device",
        "slug_override", "overrides",
    }
