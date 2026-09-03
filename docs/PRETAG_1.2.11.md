# v1.2.11 pre-tag checklist

Scope: the **starter-kit v2 cutover**. `STARTER_KIT_VERSION` `v1` → `v2`, so
the kit the plugin downloads carries `starter_kit/LICENSE-ExDark.txt` and the
corrected README. No behavior change beyond the prefix the downloader reads.
Rules: RELEASING.md order (tag → repo `catalog.json` → gist mirror), never
retag, `pytest` last thing before tagging.

**Epistemic status:** the kit build is verified by measurement, not inference —
every hash below was produced by hashing the actual artifact, and the 9-shard
byte-identity claim was checked at two independent layers (manifest agreement,
and a `sha256sum` diff of the on-disk zips that trusts neither manifest). The
**CDN prefix was staged and confirmed live before this tag**, which is the one
ordering in this release that cannot be inverted. Not verified here: a
click-through of the download flow against the live v2 prefix — that is listed
under "Open pre-tag items".

## Why this is a code release at all

BSD-3 clause 2 needs the ExDark copyright notice inside the distributed kit.
Adding it changes the kit, and a CDN version prefix is **immutable once
staged** (RELEASING.md), so the notice cannot be added to `v1` in place. It
ships as a new prefix, and the constant that resolves the prefix is plugin
code. Kit content is `../competition_exdark@78b3bf7`; the plugin side is
`16795c5`.

## The ordering that cannot be inverted

`starter_kit_prefix()` resolves at download time with **no fallback**, and
`fetch_manifest` fails the job on a 404. Tagging ahead of the dev → prod sync
would hard-fail every tester on the Import tab — the exact surface this
release exists to improve. So: stage → sync → verify live → **then** tag.

- [x] **`v2` prefix is LIVE on prod and verified** (2026-09-03, confirmed by
      Rishikesh): `manifest.json` 2,848,920 bytes, sha256
      `77F3A87E274C783EE2D21053F88E6FE220735B3E6329759F481FF7840D5EE9C6`
      — matches the committed anchor `kit/exdark-low-light/v2/manifest.json`
      exactly; `Accept-Ranges: bytes` present; a ranged GET returns **206**
      (resume depends on both).

## Verified at review (2026-09-03, dev machine)

- [x] **The kit tree matches the v2 manifest**: `check_kit_parity.py --dir`
      → `PARITY, matched 14005`, zero mismatches, zero missing, zero extra.
- [x] **10 shards, all ten names identical to v1**, and the **9 image shards
      are byte-identical**. Checked twice: `archives[]` name → (bytes, sha256,
      file_count) agreement between the v1 and v2 manifests, and a
      `sha256sum` diff of `v1/part-0[0-8]*.zip` against `v2/part-0[0-8]*.zip`
      (empty). Only `part-09-root-labels.zip` changed:
      1,496,845 → 1,498,578 bytes, 6,646 → 6,647 files.
- [x] **Why that is structural, not luck.** `_plan_shards` iterates
      `sorted(groups)` — an order independent of any group's contents — and
      re-initializes `size = 0` *inside* that loop, so no size carries across
      groups and a root-labels change cannot perturb an image group's chunk
      boundaries. `root-labels` holds 862,451 B against a 73,400,320 B budget
      (1.2 %), so it stays one shard, `group_totals["root-labels"] == 1`, and
      `_shard_name`'s suffix stays `""` → `part-09` at index 9. Holds for any
      root-file addition under ~72 MB.
- [x] **The v1 manifest shows exactly the intended delta** and nothing else:
      `size_mismatch: 2` (`README.md` 5006 → 6547, `dataset.yaml` 508 → 666),
      **`sha_mismatch: 0`**, **`missing: 0`**, **`extra: 1`**
      (`starter_kit/LICENSE-ExDark.txt`, 1502 B). Zero sha mismatches matters:
      `check()`'s `elif` chain reports a size difference *instead of* a sha
      one, so a sha line would mean a file changed content at identical
      length. Nothing did.
- [x] **The license reaches the participant.** Extracted from
      `v2/part-09-root-labels.zip`: 1,502 bytes, sha256 `51340966…` —
      byte-identical to `../competition_exdark/LICENSE-ExDark.txt`. It sits at
      entry 6644, after `labels/val/*` and before `README.md`, which is the
      Windows normcase sort position.
- [x] **No orphans in the version dir**: 11 entries on disk, exactly
      `{manifest.json} ∪ archives[].name`. The generator's guard is a *prefix*
      match on `part-*`, so a stale shard from an aborted run would pass it,
      never be deleted, and never be listed — the build went into an
      asserted-absent staging dir to remove that mode.
- [x] **The shipped bytes are the reviewed bytes.** Built to
      `cdn/_staging/v2`, verified, then landed by a same-volume `mv`. Never
      rebuilt in place: `created_utc` defaults to `now`, so a second run would
      change `manifest.json` while the shards stayed identical — the exact
      "mixed manifest/data set" the immutability rule exists to prevent.
      Post-rename `created_utc` is still `2026-09-03T17:10:36Z` and the
      hashes are unchanged.
- [x] **Manifest header**: 14,005 files / 623,652,065 bytes (`+3,201` vs v1 =
      license 1,502 + `dataset.yaml` 158 + README 1,541, which accounts for
      the delta exactly); archive sum 625,413,959; manifest sha256
      `77f3a87e…`, 2,848,920 bytes.
- [x] **`test_downloader.py` was a real failure, not a cosmetic one.** The
      destination is `dest / constants.STARTER_KIT_VERSION`
      (`downloader.py:101`) while ten assertions spelled `"v1"`; the bump
      broke **9 tests**. Fixed by deriving, not re-pinning: a `_version_dir()`
      helper plus a `cdn` fixture that generates and serves from the constant.
      Proven version-agnostic by running the file green against a temporary
      `"v3"` (15 passed) before restoring `"v2"`. A future bump needs no edit
      there. `test_kit_scripts.py` is deliberately untouched — its `"v1"` is
      its own synthetic fixture's version, with no coupling to the constant.
- [x] **The `?kgdev=dl-*` fixture re-pinned to real v2 numbers** — manifest
      URL, the `\v2\` destination path, `part-09`'s byte count, the archive
      sum (in the log line and in `bytes_total`), and `14004` → `14005` in six
      places. The block's own comment promises "real shard names and byte
      counts from the published manifest"; that is its contract.
      `node --check` v24.16.0 over the extracted script block: **PASS**.
- [x] **`pytest -q`: 157 passed** (same count as v1.2.10 — this release adds
      no tests, it removes a version coupling from existing ones).
- [x] **Manifest/catalog integrity** (RELEASING.md step 2, machine-checked
      before writing): `catalog.json` round-trips byte-identically through
      `json.dumps(indent=2, ensure_ascii=False)`; the new 1.2.11 manifest was
      **generated from `plugin.toml`** rather than hand-pasted and compares
      equal by `tomllib` on every key, key order included; catalog `id` ==
      plugin `id`; the `source` tag matches the version; version string
      identical in `pyproject.toml` (both sites), `plugin.toml` and the
      catalog manifest. The diff against the previous catalog is 34 insertions
      (the entry) and one deletion (`generated_at`) — nothing else moved.
- [x] **Build check**: `uv build` produces
      `3lc_compute_plugin_kaggle-1.2.11-py3-none-any.whl`, whose `METADATA`
      reports `Version: 1.2.11`, `License-Expression: AGPL-3.0-only`,
      `Requires-Python: >=3.11`, `Requires-Dist: 3lc-compute-plugin-sdk
      <0.4.0,>=0.3.1`; the bundled `plugin.toml` reads 1.2.11 and `ui.html`
      ships. So the footer (which renders installed dist metadata, never a
      hand-synced constant) will read 1.2.11.
- [x] **Version-pin sweep** per RELEASING.md:
      `docs/TESTER_SETUP_0.2.md` (7 pins), `scripts/setup-0.2-tester.ps1`
      (3, incl. `$PLUGIN_VER`), `README.md` (4), `pyproject.toml` (2),
      `plugin.toml` (1), `CONTEXT.md` "Current release". A tree-wide grep for
      `1.2.10` leaves only history: CONTEXT.md's release narrative, CLAUDE.md's
      project-root note, `forced-changes-0.2.md`, `ui-notes.md`,
      `v1.2-ideas.md`, `PRETAG_1.2.10.md`, earlier catalog entries, and
      **`TESTER_SETUP_0.2.md:227`** — that row says "Fixed in **1.2.10**",
      which is a statement about when a bug was fixed, not a pin. Left as
      written.
- [x] **Two standing rules recorded in RELEASING.md**, both established by
      this build rather than assumed:
      - The kit tree tracks the newest staged version only, so
        `check_kit_parity.py --dir` against an *older* version's manifest is
        **expected** to exit 1. Older tree state is recovered from git plus
        that version's committed anchor. Worth noting this was already true in
        a narrower form: `package_build/starter_kit.zip` (the live Data-tab
        upload) has not been reproducible from the tree since 2026-08-26.
      - `part-09-root-labels.zip`'s archive sha256 is Windows-specific.
        `_plan_shards` sorts `Path` objects and `PurePath.__lt__` case-folds on
        Windows but compares bytewise on POSIX, so the two uppercase basenames
        order differently and the central directory changes. **Already true of
        v1** — its `files[]` records `README.md` after `labels/val/*`, which is
        normcase order — so a POSIX rebuild of v1 already produced a different
        `part-09` hash. Verify with `check_kit_parity.py`, which compares
        `files[]` per path and is order-independent.

## Kit content shipped (competition_exdark@78b3bf7)

`starter_kit/LICENSE-ExDark.txt` in both kit trees. README retitled to
"Low-light object detection - starter kit" (clause-3 audit F5 — the old title
led with the dataset's name to identify our own deliverable). Its
`## License / data use` rewritten: BSD-3 attribution with the copyright line,
the Loh & Chan *CVIU* 178 (2019) citation, the authors' commercial-contact
request framed as **their request, not a license term**, and CC BY 4.0 for the
organizers' contributions (rulebook, val/test revisions, re-split,
compilation) scoped so the grant does not reach ExDark's images or original
annotations. The wrong "non-commercial research use only" claim is gone. The
dead CUDA-first troubleshooting row now says what is true: the plugin builds
its own environment and picks GPU PyTorch, so a current NVIDIA driver is
enough and the CUDA toolkit is not needed (`nvidia-smi`, never `nvcc`).

The `package_build/starter_kit/` copies were **regenerated from
`starter_kit/`** rather than edited, which also closed two accumulated drifts:
that README was 6 weeks stale (naming the retired page "Dataset Download & 3LC
Hub Setup"), and its `dataset.yaml` still claimed test is **NOT** imported into
the Hub, contradicting the plugin's own importer — `bf3725f` had fixed only the
source-of-truth copy and missed the build root.

## Deliberate non-goals (A3)

- **The `Path`-sort case-folding is documented, not fixed.** Normalizing it
  (`key=lambda p: p.as_posix()`) would change `part-09`'s hash for *every*
  version including v1, invalidating both committed anchors. If it is ever
  worth doing it is its own proposed task on a v3, never a rider here.
- **No orphan-cleanup or `created_utc` CLI flag added to
  `make_kit_manifest.py`.** Both hazards were handled by procedure (build into
  an asserted-absent dir; land by rename), and the script is not the finding.
- **`v1` is not withdrawn.** It stays served for installs already pinned to
  it; it is superseded, not fixed. It must not be advertised.
- **`test_kit_scripts.py` untouched** — see above; changing its synthetic
  `"v1"` would be churn.

## Open pre-tag items

- [ ] **Download click-through against the live v2 prefix** (needs the service
      up). Every layer is verified offline — the fixture renders the real
      numbers, the tests cover resume/206/range-ignore/corruption against a
      generated CDN, and the prod prefix answered a ranged GET — so this
      confirms the real network path end to end, not resolution: run Download
      on the Import tab, watch 10 shards verify, and confirm
      `LICENSE-ExDark.txt` is present at the extracted kit root.
- [ ] **Tell round-2 testers to update.** The kit they already have on disk is
      v1 and stays where it is; the new version downloads into a sibling
      `v2\` directory rather than replacing it, so nothing is destroyed and
      re-downloading is safe. Update, then **hard-refresh the plugin page** —
      the standing post-update step.

## Post-tag verification (tick-only below this line; everything above is frozen at the tag)

- [ ] Tag `v1.2.11` pushed; `catalog.json` entry landed; gist mirrored by
      Rishikesh (verify via an incognito fetch after the CDN lag).
- [ ] Footer reads `1.2.11` after a catalog install (RELEASING.md step 4).
- [ ] A fresh catalog install downloads from `…/starter-kit/v2/` and lands
      `LICENSE-ExDark.txt` at the kit root.
- [ ] `kit-exdark-v2` data tag pushed (the `kit-*` namespace, never `v*`).
