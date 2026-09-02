"""The launch-swap case (DP-04): an install carrying an old persisted slug
plus a version bump that changes COMPETITION_SLUG must resolve to the NEW
slug — while a deliberate user override survives.

At the real launch the same mechanics apply, and the retirement half is
already done: the typo'd test slug was added to constants.RETIRED_SLUGS on
2026-09-02 (E8), so the launch commit only swaps COMPETITION_SLUG. The
`launch` fixture below still monkeypatches both, because it has to simulate
a build where the constant has ALREADY moved — that is the state these
tests exist to cover, and it is not the shipped state.
"""

from __future__ import annotations

import pytest

from conftest import FIXTURE_SLUG, write_config

from tlc_plugin_kaggle import constants

NEW_SLUG = "the-3lc-public-competition"


def _write_legacy(store, slug):
    write_config(store, {
        "submit": {"conf": "0.25", "device": "", "competition_slug": slug},
        "_migrations": {"device_blank_default": True},
    })


def _effective(sess):
    return sess["slug_override"] or constants.COMPETITION_SLUG


@pytest.fixture
def launch(monkeypatch):
    """Simulate the public-launch build: new shipped constant, old test
    slug retired in the same commit."""
    monkeypatch.setattr(constants, "COMPETITION_SLUG", NEW_SLUG)
    monkeypatch.setattr(constants, "RETIRED_SLUGS", frozenset({"[SLUG]", FIXTURE_SLUG}))


def test_persisted_old_slug_resolves_to_new_constant(store, launch, tmp_path):
    _write_legacy(store, FIXTURE_SLUG)
    sess = store.load()["session"]
    assert sess["slug_override"] is None
    assert _effective(sess) == NEW_SLUG


def test_explicit_user_override_survives_the_swap(store, launch, tmp_path):
    _write_legacy(store, "my-own-competition")
    sess = store.load()["session"]
    assert sess["slug_override"] == "my-own-competition"
    assert _effective(sess) == "my-own-competition"


def test_placeholder_slug_collapses_to_tracking(store, tmp_path):
    _write_legacy(store, "[SLUG]")
    assert store.load()["session"]["slug_override"] is None


def test_slug_equal_to_current_shipped_collapses(store, tmp_path):
    # The store fixture pins COMPETITION_SLUG to the fixtures' value, so
    # this is the pre-launch case: persisted == shipped -> track, not pin.
    _write_legacy(store, FIXTURE_SLUG)
    assert store.load()["session"]["slug_override"] is None
