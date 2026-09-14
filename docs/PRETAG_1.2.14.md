# v1.2.14 pre-tag checklist

Scope: **the launch release.** Two things, both launch-blocking, both
invisible to a catalog install until tagged: the public competition slug, and
a trainer that stops drifting per participant. Rules: RELEASING.md order,
never retag, `pytest` last thing before tagging.

**Epistemic status:** the slug policy and the dependency resolution are
verified by execution on this machine. What is NOT verified here is anything
requiring an installed build - no catalog install, no Hub click-through, no
footer read. Those are post-tag by construction and listed as such at the
bottom; nothing above this line depends on them.

## The ordering gate, and that it was honoured

> **This tag must exist BEFORE any catalog push, and before the competition
> opens.** v1.2.13's `COMPETITION_SLUG` *is* the retired test slug, so
> `resolve_slug` returns it unchanged: a participant installing 1.2.13 submits
> to a dead competition, with the Submit tab's join link pointed there too.
> Nothing ages a tag install out, so anyone installing in that window stays
> broken until they reinstall.

Gudbrand was cleared to push v1.2.13 to the catalog. Rishikesh told him to
hold until this tag exists (confirmed 2026-09-14, before this commit).

## The slug swap

`COMPETITION_SLUG` -> `the-3lc-low-light-detection-challenge`. One value line;
`RETIRED_SLUGS` needed no edit, because v1.2.10 (E8, 2026-09-02) pre-staged
the typo'd test slug into it. That pre-staging is why this release had no
second edit to forget, and it worked exactly as designed.

Verified by execution against the shipped constants:

| Input | Resolves to |
|---|---|
| `the-3-lc-...-comepetition-test` (retired) | the public slug |
| empty string | the public slug |
| `[SLUG]` (early-build placeholder) | the public slug |
| `some-other-competition` | itself - a deliberate override survives |

**The policy is load-bearing for the first time.** Before this commit
`COMPETITION_SLUG` was itself a member of `RETIRED_SLUGS`, so every input
already resolved to the value it resolved to anyway - `resolve_slug` had never
once changed an outcome on a shipped build.
`test_resolve_slug_is_inert_before_launch` asserted exactly that inertness,
and the swap broke it by construction. It is replaced, not deleted, by two
tests that read the **shipped** constants rather than the `launch` fixture:

- `test_retired_test_slug_resolves_to_the_live_competition`
- `test_submission_aimed_at_retired_slug_lands_on_live_competition`,
  parametrized over all three runtime surfaces (`submit_to_kaggle`,
  `kaggle_live_status`, `kaggle_connection`)

The `launch`-fixture tests are kept: they cover the generic swap mechanic
against synthetic values and must keep working for the next swap.

## The trainer pins

`3lc-ultralytics==0.4.0` **and** `ultralytics==8.4.66`. Both, not either.

Measured 2026-09-14 - the wrapper does not pin what it wraps:

| | Declares | Note |
|---|---|---|
| ours, before | `3lc-ultralytics>=0.3.3` | floating |
| `3lc-ultralytics` 0.4.0 | `ultralytics>=8.4.0,<8.4.67` | 67-version window |
| `3lc-ultralytics` 0.3.4 | `ultralytics>=8.4.0,<8.4.67` | **identical** |

The wrapper version is not the lever. The `optimizer=auto` change ran
ultralytics 8.4.6 -> 8.4.66 and cost 0.035 val mAP50 silently between July and
September 2026; **both endpoints sit inside that window**, so pinning only the
wrapper leaves the exact regression reachable. A range cannot fix it either -
any range admitting a new ultralytics admits the same class of change. With
the checkpoint and imgsz already locked, the trainer was the last
per-participant input still drifting, in a competition with prizes.

Both values are what all three provisioned venvs (1.2.11 / 1.2.12 / 1.2.13)
actually carry, so this pins to a measured-present combination rather than a
remembered one. `ultralytics` was already installed transitively - this is a
pin, not a new dependency.

Cost accepted deliberately: updates are manual for the duration of the
competition. Registered in `docs/v1.2-ideas.md` to revisit when it closes.

### The resolution gate was re-run, because the pin window moved

`docs/v1.1-ideas.md` makes this standing: whatever we publish must resolve
from public PyPI alone with no index configuration. Run on a genuinely clean
venv (py3.12, `--no-cache --index-url https://pypi.org/simple`):

**Resolved 113 packages, exit 0, no warnings** - `3lc==3.3.1`,
`3lc-compute-plugin-sdk==0.3.3`, `3lc-ultralytics==0.4.0`,
`ultralytics==8.4.66`, `kaggle==2.2.4`, `torch==2.14.0`.

113 matches the figure recorded for the v1.2.8 gate. Honest note: the first
attempt resolved against the project venv (132 resolved / 50 to install) and
was **not** the documented check - 82 packages came from the existing
environment. The number above is the clean re-run.

## Two findings the sweep surfaced

- **The version census is four sites, not three.** RELEASING.md read
  "hand-synced in exactly three places" and named one `pyproject.toml` site.
  There are two: `[project]` and `[tool.tlc-compute]`. A sweep that followed
  the doc faithfully left the second at 1.2.13; `test_packaging.py`, which is
  named `test_the_four_version_strings_agree`, caught it. Doc corrected and
  both sites added to the ride-along census in this commit.
- **Third `uv.lock` finding, and the first not about our own version.** The
  lock recorded `3lc-ultralytics` **0.3.4** while every provisioned venv ran
  **0.4.0**, so it did not describe what ships to participants. `uv lock`
  after the pins closed it (uv reported `Updated 3lc-ultralytics v0.3.4 ->
  v0.4.0`). Three misses on one file, each a different field, each after a
  careful manual sweep: the argument for the Phase C drift check, not a
  fourth sweep.

## Gates

- [x] `pytest` - **230 passed**, run last before tagging.
- [x] Four version strings agree at 1.2.14 (`test_packaging`).
- [x] `catalog.json`: new newest-first 1.2.14 entry, `source` at `@v1.2.14`,
      manifest version matching `plugin.toml`, catalog id == plugin id,
      `generated_at` bumped. Valid JSON; 14 versions, 1.2.14 first.
- [x] `uv.lock` regenerated, reads 1.2.14 and both pins exactly.
- [x] Version-pin sweep per RELEASING.md: `docs/TESTER_SETUP_0.2.md` (7),
      `scripts/setup-0.2-tester.ps1` (3, incl. `$PLUGIN_VER`), `README.md`
      (4), `SMOKE_TEST.md` (2), `CONTEXT.md` "Current release". History left
      as written in `ui-notes.md`, `v1.2-ideas.md`, `WEEK_2026-09-01.md`,
      `RELEASING.md`, and the PRETAG files.
- [x] Clean-venv PyPI-only resolution gate (above).
- [x] `comepetition` survives in `src/` only as the retired literal in
      `RETIRED_SLUGS` plus the comment explaining it -
      `test_predictor_carries_no_slug_literal_of_its_own` still passes.

## Install shape this was verified against

**Source checkout only** (`uv run pytest`, `uv build`, a scratch venv). No
catalog install was exercised pre-tag, which is inherent - the tag has to
exist first. Per RELEASING.md's "a dev Hub and a tester are not the same
machine", nothing here should be read as a statement about an installed build.

## Post-tag verification

Tick-only below this line; never edit above it.

- [ ] Gist mirrored from the repo `catalog.json`, verbatim, confirmed by an
      incognito fetch after the CDN lag. *(Rishikesh)*
- [ ] Catalog install on the dev Hub; footer reads **v1.2.14**, read from the
      running process's home rather than from memory.
- [ ] Provisioned venv carries `ultralytics 8.4.66` after a fresh install.
- [ ] Submit tab's default slug and join link both point at the public
      competition.
- [ ] Kaggle section anchors verified against the live competition - the
      `content_v2` cross-links assume Kaggle derives them from section titles
      (`README_REDESIGN.md:28-32`); that was always an assumption, never
      checked. Not gated on this tag.
