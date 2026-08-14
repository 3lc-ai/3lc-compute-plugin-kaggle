"""Competition constants — the single definition site (leaf module).

Stdlib-free and imported by config_store, importer, predictor, and routes;
nothing here may import back into the package. This is where the v1.2.6
literal census points: every backend reference to the default project /
table name / dataset prefix / competition slug resolves to this file, and
the UI carries no copy at all (GET /config always serves a populated
session, plus _meta.default_slug).
"""

from __future__ import annotations

# Default 3LC project and table revision for a fresh session. The UI never
# hardcodes these — they reach the fragment only through GET /config.
DEFAULT_PROJECT = "exdark-competition"
DEFAULT_TABLE = "initial"

# Table layout: datasets are named f"{DATASET_PREFIX}_{split}".
DATASET_PREFIX = "exdark"


def split_dataset(split: str) -> str:
    """The dataset name a split's tables live under (exdark_train / _val /
    _test). The single definition of the split<->dataset mapping: the
    pickers, gates, server asserts, and migration all resolve it here
    (DP-11: a train slot holding an exdark_val URL passed every check that
    only tested one property)."""
    return f"{DATASET_PREFIX}_{split}"

# ── SWAP AT PUBLIC LAUNCH ────────────────────────────────────────────────
# Single source for the Submit tab's slug default and the join link. This is
# the private test competition — the "comepetition" typo is real, it's in the
# Kaggle URL. Replace the value with the public competition slug at launch.
COMPETITION_SLUG = "the-3-lc-low-light-object-detection-comepetition-test"

# Slugs that must never win over the shipped constant when found persisted
# as session.slug_override: the placeholder that shipped in early builds,
# plus every slug this plugin has since retired. LAUNCH-VERIFY: add the
# typo'd test slug above to this set IN THE SAME COMMIT that swaps
# COMPETITION_SLUG, so a v1.2.5-era persisted slug (or an install that
# skipped v1.2.6) collapses to tracking the new constant instead of
# submitting to the retired test competition (tests/test_slug_swap.py).
RETIRED_SLUGS = frozenset({"[SLUG]"})
