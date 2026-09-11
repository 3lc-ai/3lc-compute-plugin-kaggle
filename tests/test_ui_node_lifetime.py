# Copyright 2026 3LC Inc.
# SPDX-License-Identifier: AGPL-3.0-only
"""Static guards on ui.html node lifetime.

The bug these exist for (v1.2.13): the top-up offer replaced the innerHTML of
the block that CONTAINS ``#kg-dl-dest``, deleting that node. Two unguarded
dereferences then threw - ``dlStart`` reads it on every click, and the
``/config`` load writes it - and because ``dlStart`` sets ``dlRunning = true``
and clears the banner BEFORE the throw, the symptom was a button that killed
its own callout and then did nothing for the rest of the session, with the
handler never actually lost.

These are deliberately narrow. A general "every el() dereference must be
guarded" sweep would false-positive on its first run and be deleted (the
lesson in docs/v1.2-ideas.md about scoped literal censuses); these pin the
specific structural promise instead.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

UI = Path(__file__).parent.parent / "src" / "tlc_plugin_kaggle" / "ui.html"
DEREF = re.compile(r"el\('kg-dl-dest'\)\s*\.")


@pytest.fixture(scope="module")
def ui() -> str:
    return UI.read_text(encoding="utf-8")


def _line_at(ui: str, pos: int) -> str:
    return ui[ui.rfind("\n", 0, pos) + 1 : ui.index("\n", pos)].strip()


def test_kg_dl_dest_exists_exactly_once(ui: str) -> None:
    """Two would make el() ambiguous; zero is the bug."""
    assert ui.count('id="kg-dl-dest"') == 1


def test_the_offer_blurbs_are_toggled_never_rewritten(ui: str) -> None:
    """#kg-dl-dest lives inside the download blurb, so that block's innerHTML
    must never be assigned - toggling ``hidden`` is what keeps the node alive.
    """
    rewritten = re.findall(r"el\('(kg-dl-blurb[^']*)'\)\s*\.innerHTML", ui)
    assert rewritten == [], f"blurb innerHTML assigned, which deletes #kg-dl-dest: {rewritten}"

    for node in ("kg-dl-blurb-dl", "kg-dl-blurb-topup"):
        assert f'id="{node}"' in ui, f"{node} missing"
        assert re.search(rf"el\('{node}'\)\s*\.hidden\s*=", ui), f"{node} is not toggled"

    # The relationship the test protects, stated: dest is inside the dl blurb.
    start = ui.index('id="kg-dl-blurb-dl"')
    end = ui.index('id="kg-dl-blurb-topup"')
    assert 'id="kg-dl-dest"' in ui[start:end]


def test_kg_dl_dest_is_never_dereferenced_bare(ui: str) -> None:
    """Every production read/write goes through a null check.

    A missing node must not be able to take an unrelated click handler down
    with it - especially not one that has already latched ``dlRunning``.
    """
    # Everything after `var devDest =` is the ?kgdev fixture block, which runs
    # only in dev mode and force-renders the section first. A boundary, not a
    # blanket exemption: each excluded site must actually be a fixture write.
    fixtures_begin = ui.index("var devDest =")

    bare: list[str] = []
    fixture_sites: list[str] = []
    for m in DEREF.finditer(ui):
        line = _line_at(ui, m.start())
        if m.start() > fixtures_begin:
            fixture_sites.append(line)
            continue
        context = ui[max(0, m.start() - 400) : m.start()]
        if "el('kg-dl-dest')" in context or "destEl" in context:
            continue
        bare.append(line)

    assert bare == [], f"unguarded el('kg-dl-dest') dereference(s): {bare}"
    assert fixture_sites, "expected the ?kgdev fixture writes; did the block move?"
    assert all("devDest" in line for line in fixture_sites), (
        f"a non-fixture dereference slipped past the boundary: {fixture_sites}"
    )


def test_dlstart_does_not_read_the_dest_node_for_a_top_up(ui: str) -> None:
    """A top-up moves nothing, so the U1 gate-idling is both unnecessary and
    wrong there - and skipping it is what keeps the click path off the node."""
    m = re.search(r"function dlStart\(\)\s*\{(.*?)\n      \}", ui, re.S)
    assert m, "dlStart not found"
    body = m.group(1)
    assert "dlMode === 'top_up' ? null : el('kg-dl-dest')" in body, (
        "dlStart should skip the dest read for a top-up"
    )
    # The latch that turned one throw into a dead button for the session.
    assert body.index("dlRunning = true") < body.index("kgStartJob"), "unexpected dlStart shape"
