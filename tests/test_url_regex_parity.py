"""The URL-parse predicate exists twice; this keeps the copies identical.

``config_store.URL_SEG_PATTERNS`` and ``kgUrlSeg`` in ui.html must agree:
the server classifies a table-URL override on save, the fragment does it at
write time, and the fragment cannot ask the service for the project root on
every keystroke. v1.2.10 changed both (the project segment is now found by
position in the layout tail, not by a literal "/projects/" directory), and
a one-sided edit would reintroduce exactly the class of bug being fixed —
silently, since a mis-parse reads as "this URL is for another project".

tests/test_dp11_cross_split.py notes that the JS mirror is covered only by
the PRETAG manual steps "until the Playwright layer exists". That stays true
for rendering and gate behavior; the PARSE layer no longer needs a human.

The two spellings differ in exactly one mechanical way: a JS regex literal
must escape the forward slash (``\\/``) where a Python pattern writes it
plain. Undo that and the strings must be byte-identical.
"""

from __future__ import annotations

import re
from pathlib import Path

from tlc_plugin_kaggle import config_store

UI_HTML = Path(config_store.__file__).parent / "ui.html"

# kgUrlSeg's map: `project: /.../,` one kind per line.
_JS_LITERAL = re.compile(r"(project|dataset|table):\s*/(.*?)/\s*(?=[,}])")


def js_patterns() -> dict[str, str]:
    body = UI_HTML.read_text(encoding="utf-8")
    start = body.index("function kgUrlSeg(")
    end = body.index("}", body.index("[kind];", start))
    found = _JS_LITERAL.findall(body[start:end])
    assert len(found) == 3, f"expected 3 regex literals in kgUrlSeg, found {len(found)}: {found}"
    # A JS regex literal escapes "/" as "\/"; Python writes it plain.
    return {kind: literal.replace("\\/", "/") for kind, literal in found}


def test_regexes_are_identical_on_both_sides():
    assert js_patterns() == config_store.URL_SEG_PATTERNS


def test_both_sides_trim_before_matching():
    """The patterns are end-anchored, so a pasted value with trailing
    whitespace must be trimmed identically or the two sides disagree on
    real input rather than on their source text."""
    source = UI_HTML.read_text(encoding="utf-8")
    assert "String(url).trim().match(re)" in source
    assert config_store.url_table("  X:/p/datasets/d/tables/t  ") == "t"
