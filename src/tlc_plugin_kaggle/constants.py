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

# ── SWAPPED AT PUBLIC LAUNCH, 2026-09-14 ─────────────────────────────────
# Single source for the Submit tab's slug default and the join link. This is
# the PUBLIC competition. The private test competition it replaced — whose
# "comepetition" typo was real and in the Kaggle URL — is retired in
# RETIRED_SLUGS below and must stay there.
COMPETITION_SLUG = "the-3lc-low-light-detection-challenge"

# ── Starter-kit CDN ──────────────────────────────────────────────────────
# The bucket prefix is deliberately DECOUPLED from the Kaggle slug: the slug
# changes at launch (see COMPETITION_SLUG), the data location never does.
# COMPETITION_ID is a stable bucket identifier — NOT a LAUNCH-VERIFY item.
# A version prefix is immutable once staged: a kit update ships as a new
# STARTER_KIT_VERSION value, never as overwritten objects (the 24h edge
# cache would otherwise serve a mixed manifest/shard set).
CDN_BASE_URL = "https://competitions.3lc.ai"
COMPETITION_ID = "exdark-low-light"
STARTER_KIT_VERSION = "v3"


def starter_kit_prefix() -> str:
    """The immutable CDN prefix the downloader reads (no trailing slash)."""
    return f"{CDN_BASE_URL}/kaggle/{COMPETITION_ID}/starter-kit/{STARTER_KIT_VERSION}"


# Slugs that must never win over the shipped constant when found persisted
# as session.slug_override: the placeholder that shipped in early builds,
# plus every slug this plugin has since retired. A v1.2.5-era persisted slug
# (or an install that skipped v1.2.6) must collapse to tracking the shipped
# constant instead of submitting to a retired competition
# (config_store.py:284, tests/test_slug_swap.py).
#
# This set is now LOAD-BEARING. It was pre-staged in v1.2.10 (E8,
# 2026-09-02) and FIRED on 2026-09-14, when COMPETITION_SLUG moved to the
# public competition: from that commit on, every install still carrying the
# typo'd test slug — persisted or typed by hand — is redirected to the live
# competition instead of submitting to a dead one. Pre-staging is why the
# launch commit had no second edit to forget. Keep the literal in sync if
# the typo'd slug is ever re-spelled: this set is matched by value, not by
# reference to the constant, precisely so a retired value survives a swap.
RETIRED_SLUGS = frozenset({
    "[SLUG]",
    "the-3-lc-low-light-object-detection-comepetition-test",
})


def resolve_slug(raw: str) -> str:
    """The slug a request must actually submit to — THE single runtime
    decision, so no caller re-implements the policy.

    `RETIRED_SLUGS` is the one definition of "must never win"; before this
    existed, `predictor` checked only the `"[SLUG]"` placeholder by hand at
    two sites and `kaggle_connection` checked nothing, so the typo'd test
    slug would have survived the launch swap and submitted to a retired
    competition. Note the store's collapse (config_store.py:284) governs
    PERSISTENCE only: the submit job reads its slug from the request body
    (`params["competition_slug"]`), so a slug typed by hand reaches here
    whether or not the store kept it. This is the layer that decides.

    Idempotent, and live since the 2026-09-14 launch swap: a request naming
    the retired test competition now resolves to the public one rather than
    submitting to a dead slug.
    """
    candidate = str(raw or "").strip()
    if not candidate or candidate in RETIRED_SLUGS:
        return COMPETITION_SLUG
    return candidate
