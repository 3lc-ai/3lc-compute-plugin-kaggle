# v1.2.15 pre-tag checklist

Scope: **the plugin description, and nothing else.** No behaviour change, no
fragment change, no dependency change. Gudbrand reported that the Hub card is
wordier than its neighbours in the plugin list; the other cards are one
sentence. Rules: RELEASING.md order, never retag, `pytest` last thing before
tagging.

**Epistemic status:** every claim below is verified by execution or by reading
the file on disk. What is NOT verified here is anything requiring an installed
build - no catalog install, no Hub click-through, no footer read, and in
particular **nobody has yet seen the new card rendered in a Hub plugin list.**
That is post-tag by construction and listed at the bottom.

## The description

Old (299 chars), new (217), and the comparator - the `yolo` plugin's own
catalog entry (205), read from
`3lc-hub-ga/.venv/.../tlc_compute/data/default-catalog.json`:

> **old** - End-to-end Kaggle competition workflow: import the dataset, train
> the fixed baseline (YOLOv11n, pinned COCO-pretrained init @ 640), predict and
> submit. The whole competition loop without leaving the Hub. Uses Ultralytics
> YOLO (AGPL-3.0); commercial use may require an Ultralytics Enterprise
> License.

> **new** - Run the 3LC low-light detection competition end to end: import the
> dataset, train the fixed baseline, predict and submit. Uses Ultralytics YOLO
> (AGPL-3.0); commercial use may require an Ultralytics Enterprise License.

> **yolo** - Fine-tune Ultralytics YOLO models on your data with live metrics,
> SocketIO progress, and experiment tracking. Uses Ultralytics YOLO (AGPL-3.0);
> commercial use may require an Ultralytics Enterprise License.

Copy specified by Paul. The Ultralytics clause is kept deliberately: `yolo` is
the other catalog entry that links AGPL code, its clause is the string ours
already mirrored verbatim, and the new text lands within 12 characters of it.
What was dropped is the model/init/resolution parenthetical and the "whole
competition loop" sentence - both still on the page itself, the first as the
Competition-constraints chips and the second as the hero subtitle.

## Where it renders - the audit that ran before any edit

| Site | Surface | Action |
|---|---|---|
| `src/tlc_plugin_kaggle/plugin.toml` | the **installed** card | changed |
| `pyproject.toml` `[tool.tlc-compute]` | legacy-host mirror, documentation of record | changed |
| `catalog.json` newest entry manifest | the **Available** card | changed (new 1.2.15 entry) |
| `pyproject.toml` `[project] description` | wheel PyPI `Summary` | **unchanged, deliberately** |
| `src/tlc_plugin_kaggle/ui.html` hero subtitle | the plugin **page header** | **unchanged, deliberately** |

Two surfaces, not one, is the finding worth recording: a catalog-source Hub
renders the **Available** card from `catalog.json` and the **installed** card
from the `plugin.toml` inside the wheel. Fixing only the manifest would have
left Gudbrand's card exactly as he found it until he reinstalled.

**Ruled out by grep, not by memory:** `competition_exdark/content_v2` (two hits,
both unrelated prose - `03_First_Submission.md:86` and `CAPTURE_LIST.md:26`,
"the loop closes without leaving the Hub"), `competition_exdark/content`,
`demo/`, `notes/`, and `README.md`, which carries its own longer intro rather
than this string. The copies under both Hub homes are installed artifacts and
refresh on reinstall.

### The two deliberate exclusions

`[project] description` is the wheel's PyPI `Summary`. It is already its own
shorter string, is never rendered on a Hub surface, and serves a different
audience; collapsing the two would force one sentence to do both jobs.

The `ui.html` hero keeps "Import the dataset, train the fixed baseline, predict
and submit. The whole competition loop without leaving the Hub." A card is
scanned in a list of twelve, where brevity is the point; a page header is read
once on arrival and has the room. Keeping `ui.html` out is also what makes this
a pure metadata release - no worker reload, no fixture work, nothing for a
tester to re-verify beyond the card.

## The parity test

`test_packaging.py::test_the_description_is_the_same_on_every_surface` compares
`plugin.toml`, the `[tool.tlc-compute]` mirror, and the newest catalog entry.
Three hand-synced copies of one sentence with nothing comparing them is the
divergence shape CLAUDE.md names, and unlike a version skew nothing else in the
release flow would surface it.

**Newest catalog entry only.** Older entries record what shipped at their
version; a parity check that demanded rewriting them would falsify the
catalog's history.

**Why the newest entry is assertable here when the version is not.**
`test_the_four_version_strings_agree` deliberately declines to assert the
catalog's newest *version*, because RELEASING.md orders tag -> catalog and the
suite runs pre-tag. The description escapes that objection because it does not
change per release: the newest entry carries the currently-advertised text
whether or not its version has caught up. The test therefore fails only during
a description-changing release before the catalog entry lands - the ordering
step it exists to enforce. (In practice the window closes inside one commit
series: `v1.2.12`, `v1.2.13` and `v1.2.14` each point at a commit that already
carries its own catalog entry.)

### Mutation check

Each of the three sites was tampered with in turn, the suite run, and the file
restored:

| Mutated | Tests that failed |
|---|---|
| `plugin.toml` | `test_the_description_is_the_same_on_every_surface` |
| `pyproject [tool.tlc-compute]` | `test_the_description_is_the_same_on_every_surface` |
| `catalog.json` newest manifest | `test_the_description_is_the_same_on_every_surface` |

Exactly one test, the intended one, in all three cases - no version test fired
and no test was silently insensitive. Restoration verified by grep for the
tamper token afterwards.

## Checks

- [x] `uv run pytest` - **231 passed** (230 before; this release adds one).
- [x] Four version strings agree at 1.2.15 (`test_packaging`).
- [x] Description agrees across all three manifest surfaces (new test).
- [x] `catalog.json`: new newest-first 1.2.15 entry, `source` at `@v1.2.15`,
      manifest version matching `plugin.toml`, catalog id == plugin id,
      `generated_at` bumped. Valid JSON; **15** versions, 1.2.15 first, and the
      1.2.14 entry's description left exactly as it shipped.
- [x] `uv.lock` regenerated, reads 1.2.15; diff is one line; both trainer pins
      (`3lc-ultralytics==0.4.0`, `ultralytics==8.4.66`) unchanged.
- [x] Version-pin sweep per RELEASING.md: `docs/TESTER_SETUP_0.2.md` (6),
      `scripts/setup-0.2-tester.ps1` (3, incl. `$PLUGIN_VER`), `README.md` (5),
      `SMOKE_TEST.md` (2), `CONTEXT.md` "Current release". Every changed line
      was read back and confirmed to be a pin, not history. No `1.2.14` remains
      in any swept file. History left as written in `ui-notes.md`,
      `v1.2-ideas.md`, `WEEK_2026-09-01.md`, `RELEASING.md`, and the PRETAG
      files.
- [x] `src/tlc_plugin_kaggle/ui.html` untouched - confirmed by `git status`.
      No fragment impact, no `?kgdev` fixture work.
- [x] Docs updated in the same series: `RELEASING.md` step 2 (the description
      is part of the manifest match, and which entries it covers), `CLAUDE.md`
      standing-guards line, `CONTEXT.md` release entry, `docs/v1.2-ideas.md`
      register.

## Install shape this was verified against

**Source checkout only** (`uv run pytest`, `uv lock`, the wheel built by
`test_packaging`). No catalog install was exercised pre-tag, which is inherent -
the tag has to exist first. Nothing here should be read as a statement about an
installed build, and in particular nothing here has seen the rendered card.

## Post-tag verification

Tick-only below this line; never edit above it.

- [ ] Gist mirrored from the repo `catalog.json`, verbatim, confirmed by an
      incognito fetch after the CDN lag. *(Rishikesh)*
- [ ] Catalog install on the dev Hub; footer reads **v1.2.15**.
- [ ] **The Available card shows the new one-sentence description**, and the
      installed card shows it too after the update - the two surfaces this
      release exists to change, and the only check that closes Gudbrand's
      report.
- [ ] Card read back in the plugin list beside `yolo`, to confirm the length
      actually sits with its neighbours rather than merely measuring shorter.
