# Copyright 2026 3LC Inc.
# SPDX-License-Identifier: AGPL-3.0-only
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

# ── Starter-kit CDN ──────────────────────────────────────────────────────
# The bucket prefix is deliberately DECOUPLED from the Kaggle slug: the slug
# changes at launch (see COMPETITION_SLUG), the data location never does.
# COMPETITION_ID is a stable bucket identifier — NOT a LAUNCH-VERIFY item.
# A version prefix is immutable once staged: a kit update ships as a new
# STARTER_KIT_VERSION value, never as overwritten objects (the 24h edge
# cache would otherwise serve a mixed manifest/shard set).
CDN_BASE_URL = "https://competitions.3lc.ai"
COMPETITION_ID = "exdark-low-light"
STARTER_KIT_VERSION = "v1"


def starter_kit_prefix() -> str:
    """The immutable CDN prefix the downloader reads (no trailing slash)."""
    return f"{CDN_BASE_URL}/kaggle/{COMPETITION_ID}/starter-kit/{STARTER_KIT_VERSION}"


# Slugs that must never win over the shipped constant when found persisted
# as session.slug_override: the placeholder that shipped in early builds,
# plus every slug this plugin has since retired. A v1.2.5-era persisted slug
# (or an install that skipped v1.2.6) must collapse to tracking the shipped
# constant instead of submitting to a retired competition
# (config_store.py:255, tests/test_slug_swap.py).
#
# LAUNCH-VERIFY — the pairing is now PRE-SATISFIED, not pending. The typo'd
# test slug is listed below already, so the launch commit only has to swap
# COMPETITION_SLUG above; there is no second edit to forget here. Listing it
# early is provably inert while COMPETITION_SLUG still holds it: the guard at
# config_store.py:255 rejects an override on `raw_slug != COMPETITION_SLUG`
# first, so the membership test is unreachable for that value today
# (tests/test_slug_swap.py::test_slug_equal_to_current_shipped_collapses
# covers exactly this pre-launch case). It becomes load-bearing the instant
# COMPETITION_SLUG changes. Keep the literal in sync if the typo'd slug is
# ever re-spelled: this set is matched by value, not by reference to the
# constant, precisely so the retired value survives the swap.
RETIRED_SLUGS = frozenset({
    "[SLUG]",
    "the-3-lc-low-light-object-detection-comepetition-test",
})
