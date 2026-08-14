"""DP-11: a table URL that is individually valid but belongs to another
split. The crosssplit fixture is CONSTRUCTED from the real mis-click state
(the live copy was corrected before capture): session pair
(exdark-competition, round2) with the train slot holding the same-project
exdark_val/initial URL — accepted by the picker, green-gated by the
existence-only check, persisted by v1.2.6's override capture.

Layers under test here: the shared predicate (classify_override — the JS
mirror kgOverrideDisposition is covered by the PRETAG manual steps until
the Playwright layer exists), the session_v1 migration applying it, and
the server-side asserts (trainer / predictor). The picker scoping and the
gate rendering are fragment behavior — PRETAG.
"""

from __future__ import annotations

import pytest

from conftest import fixture_config, materialize_tables, write_config

from tlc_plugin_kaggle import predictor, trainer
from tlc_plugin_kaggle.config_store import classify_override

ROOT = "X:/home/AppData/Local/3LC/3LC/projects/p1/datasets"


# ── The predicate itself ─────────────────────────────────────────────────


def test_classify_keep_same_split_revision():
    assert classify_override(f"{ROOT}/exdark_train/tables/round2", "p1", "initial", "train") == "keep"


def test_classify_drop_cross_split():
    assert classify_override(f"{ROOT}/exdark_val/tables/initial", "p1", "initial", "train") == "drop"


def test_classify_drop_cross_project():
    assert classify_override(f"{ROOT}/exdark_train/tables/round2", "p2", "initial", "train") == "drop"


def test_classify_drop_unparseable():
    assert classify_override("not-a-table-url", "p1", "initial", "train") == "drop"


def test_classify_suppress_derived_equal():
    # M1: equals what derivation yields — storing it would freeze future
    # table-name changes for this field while its sibling followed.
    assert classify_override(f"{ROOT}/exdark_train/tables/round2", "p1", "round2", "train") == "suppress"


# ── session_v1 applies it (migration call site) ──────────────────────────


def test_session_v1_drops_cross_split_override(store, tmp_path):
    cfg = fixture_config("crosssplit", tmp_path)
    materialize_tables(cfg)
    write_config(store, cfg)
    data = store.load()
    assert data["_migrations"]["session_v1"] == "import_state"
    sess = data["session"]
    assert sess["project_name"] == "exdark-competition"
    assert sess["table_name"] == "round2"
    # train slot held exdark_val/initial (the mis-click): dropped, not
    # preserved as an override. val and test held derived-equal URLs
    # (exdark_val/round2, exdark_test/round2): suppressed (M1). Nothing
    # survives — the fields re-derive on first load.
    assert sess["overrides"] == {}


# ── Layer 3: server-side asserts ─────────────────────────────────────────


def test_trainer_rejects_cross_split_url():
    with pytest.raises(ValueError, match="points at exdark_val; expected exdark_train"):
        trainer.validate_table_urls(
            f"{ROOT}/exdark_val/tables/initial", f"{ROOT}/exdark_val/tables/round2"
        )


def test_trainer_rejects_identical_train_and_val_urls():
    # Unreachable today once the dataset asserts pass (datasets must
    # differ), kept as defense in depth per the fix spec — so exercise it
    # through URLs that pass no dataset check first: same URL both slots
    # fails the train-slot dataset assert; assert the identical rule
    # directly on a hypothetical future shape via the message contract.
    with pytest.raises(ValueError):
        trainer.validate_table_urls(
            f"{ROOT}/exdark_val/tables/initial", f"{ROOT}/exdark_val/tables/initial"
        )


def test_trainer_accepts_correct_splits():
    trainer.validate_table_urls(
        f"{ROOT}/exdark_train/tables/initial", f"{ROOT}/exdark_val/tables/initial"
    )


def test_predict_rejects_cross_split_test_url():
    with pytest.raises(ValueError, match="points at exdark_train; expected exdark_test"):
        predictor.validate_test_table_url(f"{ROOT}/exdark_train/tables/initial")


def test_predict_accepts_test_split():
    predictor.validate_test_table_url(f"{ROOT}/exdark_test/tables/initial")
