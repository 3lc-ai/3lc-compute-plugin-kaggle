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


# ── The runtime half (v1.2.13) ───────────────────────────────────────────
#
# Everything above tests PERSISTENCE: what the store keeps as slug_override.
# That was the whole of the retired-slug policy until v1.2.13, and it does not
# reach the submit path — the job reads its slug from the REQUEST BODY
# (`params["competition_slug"]`, sent by the fragment as the raw ps-slug
# field), so a slug typed by hand arrives at submit_to_kaggle whether or not
# the store kept it. The three runtime surfaces used to disagree: two collapsed
# only the "[SLUG]" placeholder by hand and kaggle_connection collapsed nothing
# at all, so after the launch swap the typo'd test slug would have submitted to
# the retired competition. constants.resolve_slug is now the one decision.


def test_resolve_slug_is_inert_before_launch():
    """The pre-launch guarantee: COMPETITION_SLUG is itself a member of
    RETIRED_SLUGS today, so every input resolves to exactly what it resolves
    to now. The policy only becomes load-bearing when the constant changes."""
    assert constants.COMPETITION_SLUG in constants.RETIRED_SLUGS
    assert constants.resolve_slug(constants.COMPETITION_SLUG) == constants.COMPETITION_SLUG
    assert constants.resolve_slug("") == constants.COMPETITION_SLUG
    assert constants.resolve_slug("[SLUG]") == constants.COMPETITION_SLUG


def test_resolve_slug_collapses_every_retired_slug_after_the_swap(launch):
    for retired in ("[SLUG]", FIXTURE_SLUG):
        assert constants.resolve_slug(retired) == NEW_SLUG
    assert constants.resolve_slug("  " + FIXTURE_SLUG + " ") == NEW_SLUG


def test_resolve_slug_keeps_a_deliberate_choice(launch):
    assert constants.resolve_slug("some-other-competition") == "some-other-competition"


@pytest.mark.parametrize("surface", ["submit_to_kaggle", "kaggle_live_status", "kaggle_connection"])
def test_every_runtime_surface_routes_its_slug_through_the_policy(surface, launch, monkeypatch):
    """All three must ASK the shared policy, whatever they do afterwards.

    Spying on `resolve_slug` rather than on a downstream call is deliberate:
    two of these three bail out early when credentials are absent (submit
    returns "skipped", live-status returns not-connected and drops the slug
    from its payload), so any probe further down the path tests the bail-out
    instead of the policy. kaggle_connection is in this list because before
    v1.2.13 it had no slug guard at ALL — the other two at least collapsed the
    "[SLUG]" placeholder by hand.
    """
    from tlc_plugin_kaggle import predictor

    calls: list[tuple[str, str]] = []

    def spy(raw):
        out = constants.resolve_slug(raw)
        calls.append((raw, out))
        return out

    monkeypatch.setattr(predictor, "COMPETITION_SLUG", NEW_SLUG)
    monkeypatch.setattr(predictor, "resolve_slug", spy)
    monkeypatch.setattr(predictor, "kaggle_credentials_present", lambda: True)
    monkeypatch.setattr(
        predictor, "_authenticated_api", lambda: (None, "no credentials in this test")
    )

    fn = getattr(predictor, surface)
    if surface == "submit_to_kaggle":
        fn("some.csv", "msg", FIXTURE_SLUG, None)
    else:
        fn(FIXTURE_SLUG)

    assert calls, f"{surface} never consulted resolve_slug — it has its own policy"
    assert calls == [(FIXTURE_SLUG, NEW_SLUG)], (
        f"{surface} resolved {calls!r}; the retired slug must collapse to the shipped one"
    )


def test_predictor_carries_no_slug_literal_of_its_own():
    """The divergence guard: RETIRED_SLUGS is the single definition of "must
    never win". A hand-rolled membership test in predictor is the bug this
    closes, so assert the literals are gone rather than trusting review."""
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "src" / "tlc_plugin_kaggle" / "predictor.py"
    text = src.read_text(encoding="utf-8")
    assert '"[SLUG]"' not in text
    assert "comepetition" not in text
