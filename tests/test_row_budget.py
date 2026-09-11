"""The train-time row budget (v1.2.13).

An UPPER BOUND on train and val rows, checked against the tables a run will
actually train on. Before this, nothing anywhere compared a train-time row
count to anything: `importer.EXPECTED_ROWS` was asserted only during Import,
against the tables as imported, and `check_provenance` records model, imgsz,
pretrained and the checkpoint sha but NOT row counts, so a run trained on a
grown split was indistinguishable after the fact.

Two properties are load-bearing and both are tested here rather than trusted
to comments: the bound is an upper bound (pruning and zero-weighting stay
legal), and the check runs AFTER table resolution (`use_latest` follows
`.latest()`, so a legal base table can have an over-size revision above it).
"""

from __future__ import annotations

import inspect

import pytest

from pathlib import Path

from tlc_plugin_kaggle import trainer
from tlc_plugin_kaggle.importer import EXPECTED_ROWS

TRAIN, VAL = EXPECTED_ROWS["train"], EXPECTED_ROWS["val"]


class FakeTable:
    """Only the surface check_row_budget touches. Mirrors conftest's fake."""

    def __init__(self, row_count):
        self.row_count = row_count


def budget(train_rows, val_rows, use_latest=False):
    trainer.check_row_budget(
        {"train": FakeTable(train_rows), "val": FakeTable(val_rows)}, use_latest
    )


# ── Upper bound, not equality ────────────────────────────────────────────

@pytest.mark.parametrize("train_rows", [TRAIN, TRAIN - 1, 1])
def test_at_or_under_the_ceiling_is_allowed_for_train(train_rows):
    """Equality passes and so does anything under it. Pruning rows is
    legitimate competition work, so a smaller table is NOT a finding."""
    budget(train_rows, VAL)


@pytest.mark.parametrize("val_rows", [VAL, VAL - 1, 1])
def test_at_or_under_the_ceiling_is_allowed_for_val(val_rows):
    budget(TRAIN, val_rows)


def test_one_row_over_is_refused_on_train():
    with pytest.raises(ValueError, match=r"Train table has 5,911 rows"):
        budget(TRAIN + 1, VAL)


def test_one_row_over_is_refused_on_val():
    with pytest.raises(ValueError, match=r"Val table has 734 rows"):
        budget(TRAIN, VAL + 1)


def test_both_splits_over_are_both_named():
    with pytest.raises(ValueError) as exc:
        budget(TRAIN + 294, VAL + 8)
    message = str(exc.value)
    assert "Train table has 6,204 rows" in message
    assert "Val table has 741 rows" in message


# ── Weight and row count are orthogonal ──────────────────────────────────

def test_weights_cannot_change_the_verdict():
    """The bound reads raw `row_count`, so 3LC sampling weights and the two
    exclude-zero-weight settings cannot move it in either direction. A table
    whose rows are ALL weight 0 still passes at 5,910; a grown table is still
    refused however its rows are weighted. This is why the rule is stated as
    rows, not as 'effective training set size': the trainer passes those
    settings straight through to tlc_ultralytics and does no filtering of its
    own, so no row-count reading here could reflect them anyway.
    """
    budget(TRAIN, VAL)                       # every row weight 0 -> same count
    with pytest.raises(ValueError):
        budget(TRAIN + 1, VAL)               # weights are irrelevant to this


def test_an_unreadable_row_count_does_not_refuse():
    """A table whose row_count cannot be read must not fail the run. The Layer-1
    gate names unknown counts; Layer 3 refuses only what it can prove."""
    class Opaque:
        row_count = None

    trainer.check_row_budget({"train": Opaque(), "val": Opaque()})


# ── The message ──────────────────────────────────────────────────────────

def test_the_message_says_what_is_still_allowed():
    with pytest.raises(ValueError) as exc:
        budget(TRAIN + 1, VAL)
    message = str(exc.value)
    assert "Removing rows is fine" in message
    assert "weight to 0" in message
    assert "The competition train split has 5,910." in message


def test_the_message_names_the_revision_situation_only_when_it_applies():
    with pytest.raises(ValueError) as latest:
        budget(TRAIN + 1, VAL, use_latest=True)
    assert "latest revision" in str(latest.value)

    with pytest.raises(ValueError) as exact:
        budget(TRAIN + 1, VAL, use_latest=False)
    assert "latest revision" not in str(exact.value), (
        "naming Use latest revision when it is off is misdirection: going back "
        "a revision would not clear the refusal"
    )


def test_the_message_carries_no_em_or_en_dash(monkeypatch):
    """ui-notes §4: no em or en dashes in rendered copy, and a Layer-3 refusal
    renders verbatim in the Train tab's failure banner."""
    with pytest.raises(ValueError) as exc:
        budget(TRAIN + 1, VAL, use_latest=True)
    assert "\u2014" not in str(exc.value)
    assert "\u2013" not in str(exc.value)


# ── The ordering, which is the whole correctness argument ────────────────

def test_the_budget_is_checked_after_both_tables_are_resolved():
    """THE structural guard.

    `use_latest` makes `_resolve_table` follow `.latest()`, so a base table at
    or under the ceiling can have a newer revision above it. Checking the
    budget before resolution would read the base table and pass the very case
    the check exists for, and it would do so silently: the run would train on
    the grown revision and record provenance that proves nothing about rows.

    Asserted on the source because the failure is an ORDERING, not a value.
    `run_training` cannot be called in this suite (build_settings imports
    tlc_ultralytics, which the dev venv does not carry), so a behaviour test
    would need the full training stack to catch a two-line move.
    """
    src = inspect.getsource(trainer.run_training)

    train_resolve = src.index('_resolve_table(params["train_table_url"]')
    val_resolve = src.index('_resolve_table(params["val_table_url"]')
    budget_call = src.index("check_row_budget(")

    assert budget_call > train_resolve, "row budget must be checked after the train table resolves"
    assert budget_call > val_resolve, "row budget must be checked after the val table resolves"


def test_the_budget_is_checked_before_training_starts():
    """The other half of the ordering: refuse before the checkpoint fetch and
    before YOLO is constructed, so an over-size run costs nothing."""
    src = inspect.getsource(trainer.run_training)
    budget_call = src.index("check_row_budget(")
    assert budget_call < src.index("ensure_official_checkpoint(")
    assert budget_call < src.index("YOLO(")


def test_the_budget_reads_the_resolved_tables_not_the_urls():
    """A signature guard on the same argument: the check takes Table objects.
    Passing URLs would make the ordering above unenforceable, since a URL is
    available before resolution."""
    src = inspect.getsource(trainer.run_training)
    assert 'check_row_budget({"train": train_table, "val": val_table}' in src


# ── One definition of the bounds ─────────────────────────────────────────

def test_the_bounds_come_from_one_place():
    """The gate, the Import assert and this check must not be able to
    disagree. Serving is what makes that true for the fragment; this pins the
    backend half."""
    from tlc_plugin_kaggle.routes import KaggleController

    served = KaggleController.get_config.fn(object())["_meta"]["contract"]["max_rows"]
    assert served == EXPECTED_ROWS
    assert served is not EXPECTED_ROWS, "serve a copy, not the live dict"


# ── The gate reads the served ceilings, never its own ────────────────────

def test_the_fragment_carries_no_row_bound_literal_in_the_gate():
    """The Train gate's ceilings come from `_meta.contract.max_rows`. The
    Import fixtures' 5,910 / 733 are allowlisted in test_contract_parity;
    the gate is not - it is the surface that states the rule."""
    UI = Path(__file__).resolve().parents[1] / "src" / "tlc_plugin_kaggle" / "ui.html"
    text = UI.read_text(encoding="utf-8")
    gate = text[text.index("function trEvaluateGate("):text.index("function trRenderGate(")]
    for ceiling in EXPECTED_ROWS.values():
        assert str(ceiling) not in gate
    assert "max_rows" in gate
