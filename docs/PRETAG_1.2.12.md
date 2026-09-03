# v1.2.12 pre-tag checklist

Scope: the **divergent-source release**. One value read from two sources with
nothing comparing them — closing the instance v1.2.11's kit bump armed (F1),
the Verify ratio that could not go non-green (F10), and adding the tests that
catch the class rather than the instance. Rules: RELEASING.md order (tag →
repo `catalog.json` → gist mirror), never retag, `pytest` last thing before
tagging.

**Epistemic status:** the two behavior fixes are verified by execution, not by
reading. F1's tests were written first and **observed failing against the
pre-fix downloader** (4 of 5; the 5th is a regression guard for `verify_now`,
correctly green both sides). F10 was proven at DOM level by rendering the
fragment's live path against a `matched != file_count` payload. Every packaging
assertion was mutation-checked. **Not verified here:** anything needing a
running 0.2.x service — the live worker check and the reduced-motion pass, both
listed under "Open pre-tag items".

## Why this is a release rather than a batch

CLAUDE.md §B: fixes are invisible to catalog installs until tagged. F1 is live
for **every** holder of kit v1 the moment they update to v1.2.11 or later, and
its symptom is silence — the participant is told "downloaded 2 days ago"
forever and no surface names a newer kit. That is not a finding a tester will
report, so it cannot wait for a batch.

## What was actually wrong

Three sources could answer "which kit is this": `constants.STARTER_KIT_VERSION`
(the write path), the job record's `facts.kit_version` (the read path), and the
CDN manifest's own `kit_version` (surfaced in a check-detail line and compared
to nothing). `16795c5` moved the first and not the second.

## Verified at review (2026-09-03, dev machine)

- [x] **The new tests fail against the pre-fix code.** Confirmed by running
      them before the downloader change:
      `test_recorded_version_behind_the_constant_is_superseded`,
      `test_superseded_is_not_the_missing_kit_state`,
      `test_record_without_a_recorded_version_does_not_probe_the_current_one`,
      `test_manifest_version_disagreeing_with_the_constant_is_refused` — all
      four FAILED, then all four passed after. A test that passes before the
      fix is not testing the fix.
- [x] **The two-version block pins v1 and v2 deliberately.** The rest of
      `test_downloader.py` derives the version from the constant (correct for
      those tests, and exactly why `16795c5` removed the only place a skew
      could surface). The `home` fixture exists so the version can move
      mid-test, which the `cdn` fixture cannot do.
- [x] **F10 proven at DOM level, not by reading.** The fragment's live path,
      driven against `{ok: true, file_count: 14005, matched: 14002}`, renders
      **"Starter kit verified just now: 14,002 of 14,005 files match the
      manifest."** The same payload before the fix rendered "14,002 of 14,002":
      a perfect ratio on a kit missing three files.
- [x] **`superseded` renders as information, not a fault** — `kg-callout info`,
      `info` glyph, ordinary offer beneath, no new button or wiring. Checked
      both through the `?kgdev=dl-superseded` fixture and through the live
      `download_state` path.
- [x] **Every packaging assertion mutation-checked.** Drifting `plugin.toml`'s
      version failed `test_the_four_version_strings_agree`; a bad catalog
      `manifest.version` failed `test_catalog_entries_are_internally_consistent`;
      a duplicated entry failed that plus
      `test_catalog_versions_are_unique_and_newest_first`. Each fired alone.
- [x] **`node --check` clean** on the extracted `ui.html` script block.
- [x] **Suite: 167 passed** (was 157 at v1.2.10).
- [x] **Catalog entry derived from `plugin.toml`, not hand-pasted** — and
      written byte-stably: `ensure_ascii=False` (the manifest icon is an emoji;
      escaping it rewrites all 12 entries) and `write_bytes` (Python translates
      `\n` to `\r\n` on Windows and this file is LF in the index). Diff is 34
      insertions, 1 deletion: one entry plus `generated_at`.
- [x] **Version pins swept** per RELEASING.md §2: `docs/TESTER_SETUP_0.2.md`
      (7 sites), `README.md` (4), `scripts/setup-0.2-tester.ps1` (3),
      `CONTEXT.md` release line. Grep for `1.2.11` in `*.md` / `*.ps1` now
      returns only history (CONTEXT.md's "preceded by" chain), which
      RELEASING.md explicitly excludes from the sweep.

## The honest limit, recorded deliberately

**Downloading v2 does not correct a v1 holder.** `parse_dataset_yaml` resolves
`path: .` against the yaml's own directory, so the new kit lands in a new
directory while already-imported tables keep resolving into the old tree; and
because those tables still exist, `verified_import_state` keeps passing and the
Import tab stays in its revisit view, so the participant never re-imports. They
keep training against v1, wrong README and all. What v1.2.12 buys is that they
are **told**, accurately, instead of being told nothing.

The copy therefore does not claim the download resolves anything beyond having
the kit present, and does not invite deleting the old kit — that would break
exactly those tables. The in-place top-up is the fix that actually reaches an
existing holder; it leads the v1.2.13 register in `docs/v1.2-ideas.md`.

## Open pre-tag items

- [ ] **Live 0.2.x worker check.** With a completed download record on disk,
      edit `facts.kit_version` to `"v1"` in
      `~/.3lc-kaggle-plugin/jobs/<id>.json` and reload the Import tab. Expect
      the superseded line naming v1 and the real resolved path, the Download
      offer visible beneath, and Verify still green against the tree on disk.
      Every backend equivalent is covered by the suite; this is the UI hop.
- [ ] **Reduced-motion parity** on the superseded callout (ui-notes §2). It
      renders through `dlShowOffer(false, false)` with `animate` false, so
      there should be nothing to gate — confirm rather than assume.

## Post-tag verification

- [ ] Footer reads **1.2.12** after a catalog install (RELEASING.md §4).
- [ ] Gist raw URL serves the 1.2.12 entry after the CDN lag, checked by
      incognito fetch, and the pasted content is byte-identical to the repo
      file.
