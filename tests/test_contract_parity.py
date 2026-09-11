"""The locked contract is SERVED, not restated (v1.2.13).

A divergence guard in the mould of `test_url_regex_parity`: one value derived
correctly at one site while a second site reads a stale copy, with nothing
comparing them. That class has now shipped three times (v1.2.10's project root,
v1.2.12's kit version, and this), so the standing rule in CLAUDE.md §B is that
catching it is the suite's job.

What made this instance worth closing ahead of the others is WHICH card it is.
ui.html hardcoded `sha256 0ebbc80d4a76...` and `640` in four places against
`trainer.OFFICIAL_CHECKPOINT_SHA256` and `LOCKED_TRAIN_ARGS`. That card is the
competition's fairness claim to participants: a stale hash there asserts
something no run records, and `check_provenance` would go on passing while the
page said otherwise.

One test file covers both halves of the one `_meta` addition, the contract and
the row bounds, because they are one claim: these are the fixed rules of the
competition and the fragment does not get to have an opinion about them.
"""

from __future__ import annotations

import re
from pathlib import Path

from tlc_plugin_kaggle import trainer
from tlc_plugin_kaggle.importer import EXPECTED_ROWS
from tlc_plugin_kaggle.routes import KaggleController

UI = Path(__file__).resolve().parents[1] / "src" / "tlc_plugin_kaggle" / "ui.html"


def served():
    return KaggleController.get_config.fn(object())["_meta"]["contract"]


# ── The backend half: what is served IS the contract ─────────────────────

def test_served_contract_mirrors_the_trainer_constants():
    c = served()
    assert c["model"] == trainer.LOCKED_TRAIN_ARGS["model"]
    assert c["imgsz"] == trainer.LOCKED_TRAIN_ARGS["imgsz"]
    assert c["pretrained"] == trainer.LOCKED_TRAIN_ARGS["pretrained"]
    assert c["checkpoint_sha256"] == trainer.OFFICIAL_CHECKPOINT_SHA256


def test_served_contract_mirrors_the_row_bounds():
    assert served()["max_rows"] == EXPECTED_ROWS


def test_the_contract_block_is_exactly_the_contract():
    """Complete, and no more. A partial mirror invites "which fields are in
    it?" and lets the next locked key be added to trainer without reaching the
    card. `pretrained` is deliberately served without being rendered anywhere
    today: it is part of the contract, so it is part of the block.
    """
    assert set(served()) == {
        *trainer.LOCKED_TRAIN_ARGS,
        "checkpoint_sha256",
        "max_rows",
    }


def test_the_bounds_are_a_copy_not_the_live_dict():
    assert served()["max_rows"] is not EXPECTED_ROWS


# ── The fragment half: no hand-written twin survives ─────────────────────

def test_no_checkpoint_sha_literal_anywhere_in_the_fragment():
    """Three copies used to live here: the card's 12-char prefix and two
    independent full-length `devSha` literals in the ?kgdev fixtures."""
    text = UI.read_text(encoding="utf-8")
    assert trainer.OFFICIAL_CHECKPOINT_SHA256 not in text
    assert trainer.OFFICIAL_CHECKPOINT_SHA256[:12] not in text


def test_the_locked_contract_card_renders_served_values():
    """The card's two claim-bearing values come from `_meta.contract`."""
    text = UI.read_text(encoding="utf-8")
    assert '<span class="val" id="tr-lock-init"></span>' in text
    assert '<span class="val kg-contract-imgsz"></span>' in text
    # Every surface that states the locked resolution, not only the card row.
    assert text.count("kg-contract-imgsz") >= 5


def test_no_contract_literal_survives_outside_fixtures_and_prose():
    """The imgsz literal must not reappear in rendered contract copy.

    Two allowlisted homes remain, deliberately:

      * the Batch help sentence, which mentions 640px as PROSE about GPU memory
        ("16 fits an 8 GB card at 640px"). It makes no claim the provenance
        panel verifies, and serving it would put a slot inside a sentence for
        no participant benefit.
      * the ?kgdev fixtures, which reproduce BACKEND strings (the provenance
        check labels and the trainer's log line) rather than stating the
        contract. A fixture disagreeing with the constant is demo data being
        wrong, not the fairness claim being wrong. Registered, not fixed:
        the same argument applies to the Import fixtures' 5,910 / 733.
    """
    lines = UI.read_text(encoding="utf-8").splitlines()
    # Standalone number only: a bare substring search also matches the 640 in
    # "0.6402" and "86400", which are mAP scores and epoch offsets.
    imgsz = re.compile(r"(?<![\d.])" + str(trainer.LOCKED_TRAIN_ARGS["imgsz"]) + r"(?!\d)")
    offenders = []
    for i, line in enumerate(lines, 1):
        if not imgsz.search(line):
            continue
        stripped = line.strip()
        if stripped.startswith("//"):                       # comments
            continue
        if "8 GB card" in line:                             # batch-help prose
            continue
        if re.search(r"imgsz=|records imgsz|PASS run records", line):  # fixtures
            continue
        offenders.append(f"{i}: {stripped[:100]}")
    assert not offenders, "unserved contract literal(s) in ui.html:\n" + "\n".join(offenders)
