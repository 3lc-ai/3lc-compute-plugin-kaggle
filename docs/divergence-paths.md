# Divergence paths — kaggle-exdark plugin (audit session 2026-08-13, v1.2.5 @ 54af3a5)

A divergence path (DP) is a concrete, ordered sequence of user actions after which two
readers of the same logical fact see different values. Derived from
[state-inventory.md](state-inventory.md); root-cause verdict and fix scope in
[state-audit-verdict.md](state-audit-verdict.md).

All paths below were verified by code reading against the working copy (v1.2.5,
`docs/state-audit` branch). DP-06 and DP-07 are race/partial-failure paths: mechanism
verified in code, not reproduced at runtime this session — marked ⚠ code-verified-only.

> **Status (2026-08-13, v1.2.6 on `fix/session-state`, untagged):**
> DP-01/02/05/09/10 dissolved with the session object (no store left to
> disagree); DP-04 and DP-08 resolved by validate-on-read; DP-06 resolved by
> load sequencing. Evidence: the pytest layer in `tests/` plus the Phase 2
> browser verification (DP-01 killed end-to-end). **Out of scope, still
> open:** DP-03 (stepper's project-blind derivation) and DP-07 (three-store
> submission outcome). Descriptions below are kept as written — they document
> v1.2.5, the version the migration heals.

## Divergence classes

- **D1 — duplicated storage**: one logical fact stored under ≥2 independent keys.
- **D2 — hardcoded default shadowing canonical state**: a field/derivation defaults to a
  literal instead of reading the canonical value.
- **D3 — persisted value read without validation** against the current environment
  (shipped constants, job store, disk).
- **D4 — rehydration bypass/race**: a code path reads or writes state before/around the
  async config restore, or skips the tab-entry refresh.
- **D5 — multi-copy write with partial failure**: one writer fans one fact out to several
  stores; a partial failure leaves them disagreeing.

The theory this list tests: the workflow is a locked linear sequence, but its state is
per-tab independent values. **Every DP below is an instance of exactly that** — the list
supports the one-architectural-gap reading. The three prior "separate" bugs map cleanly:
run-start-only config save = D4, saved-device-'0' = D1+D3, and this round's orphaned run =
D1+D2.

---

## DP-01 — Project name: Import vs Train run project (the tester's bug)

- **Class:** D2 (primary) + D1
- **Steps:**
  1. Load the plugin page fresh (no saved `train.project_name`, or one equal to the default).
  2. On Import, set "Project name" to `exdark-competitionv2`; let it settle (600 ms / blur).
  3. Run Import & Validate → three tables created in project `exdark-competitionv2`.
  4. Click "Continue to Train" (or the Train tab — same path, see "Disproven" below).
  5. Tab entry re-points `tr-train-url` / `tr-val-url` at `exdark-competitionv2` defaults
     (`kgSyncFieldToProject` ui.html:3956, 1806-1831) → gate goes green.
  6. Observe the 3LC-settings "Project" field (`tr-project`): it still reads
     `exdark-competition`.
  7. Start Training.
- **Divergence:** the tables (and the gate's green verdict) live in `exdark-competitionv2`;
  the job body carries `project_name: 'exdark-competition'` (ui.html:4088) →
  `trainer.validate_settings` (trainer.py:272) → the tlc Run is created in a brand-new
  `exdark-competition` project containing zero dataset tables.
- **Consequence:** training itself succeeds (tables are resolved by URL, project-independent),
  so the divergence is **silent** — provenance passes, predict and submit work — but the Run
  is orphaned from its data: the Dashboard project holding the Run has no tables, "fix labels
  → retrain" (the Loop, the product's whole demo) breaks, and no warning ever fires.
- **Severity:** high — silent, survives to submission, breaks the demo story.
- **Root cause (precise):**
  - `tr-project` renders a hardcoded markup default `value="exdark-competition"`
    (ui.html:859) and **no code path ever re-points it at the current project**:
    `kgSyncFieldToProject` (ui.html:1806-1831) syncs only the three table-URL fields
    (`ui:1817`); `kgCurrentProject()` (ui.html:1790-1793) reads only `kg-project`.
  - The same logical fact is persisted under two independent keys — `import.project_name`
    (written by the Import settle-save, ui.html:2213-2235) and `train.project_name`
    (written by [T-save]) — so even a page reload cannot heal the field.
  - Aggravator: the v1.2.5 coherence fix itself cements the divergence — when the sync
    re-points the URL fields it re-persists the **whole** Train form (ui.html:1826),
    including the stale `tr-project`, into `train.project_name`.
- **Correction to the briefing's description:** mechanism confirmed, two refinements.
  (1) The Train job does *not* train on zero data — it trains fine on the other project's
  tables; only the Run record lands in the wrong project. (2) "Shows hardcoded default Y"
  is the fresh-install case; an install that ever trained with a different project shows
  that stale saved value instead (same class, worse: it can be a third project).

## DP-02 — Table name: Import's "Table name" vs the hardcoded `initial` in every default derivation

- **Class:** D2 + D1
- **Steps:**
  1. Fresh install. On Import, set "Table name" to `round2` (project left default).
  2. Run Import & Validate → success; tables exist at `.../datasets/exdark_*/tables/round2`.
  3. Open Train (fields empty on a fresh install).
- **Divergence:** the blank-prefill and the sync both derive defaults via
  `GET /tables/defaults?project=...` **without a `table` param** (ui.html:3435, 4512, 1813),
  so routes.py:164 falls back to `table="initial"` → the fields point at
  `.../tables/initial`, which does not exist. Import says done (banner, stepper ✓);
  Train's gate says "These tables aren't on disk yet" and its help text blames the
  **project** ("Looking in project X…", ui.html:3852-3854), which is correct — the table
  name is what's wrong.
- **Consequence:** participant is walked back to Import by the remediation, which will
  reuse/re-verify and change nothing; loop until they hand-paste URLs. Not silent, but
  misdiagnosed by the UI's own remediation text.
- **Severity:** medium — visible dead-end with misleading remediation; recoverable via the
  revision picker.
- **Root cause:** `import.table_name` is canonical for where tables land (importer.py:380)
  but the default-derivation chain (routes.py:164 + all three UI callers) hardcodes
  `initial` and never consults it. Same shape as DP-01: the project half of the tuple was
  taught to follow (v1.2.1), the table-name half never was.

## DP-03 — "Import done": stepper checkmark vs Train gate after a project change

- **Class:** D1 (two readers derive "done" from different sources)
- **Steps:**
  1. Import successfully into project `A` (stepper Import ✓).
  2. On Import, change "Project name" to `B`; let it settle. Do not re-import.
  3. Look at the stepper, then open Train.
- **Divergence:** the stepper still shows Import ✓ — `/pipeline` (routes.py:414) delegates
  to `verified_import_state`, which verifies the **snapshot's** tables (project `A`,
  importer.py:535-543) and knows nothing about the form's new project. Train's gate,
  meanwhile, has been re-pointed at project `B` (sync) and is amber ("no import for that
  project yet").
- **Consequence:** the pipeline indicator and the tab it points to disagree about whether
  step 1 is complete; "the stepper checkmark and the tab's revisit view must share one
  backend source of truth" (ui-notes §1) holds for Import's own revisit view but not for
  the cross-tab reading of the same fact.
- **Severity:** low-medium — confusing, self-heals after the next import, no data loss.
- **Root cause:** "import done" is project-relative for the Train gate (kgCurrentProject)
  but snapshot-absolute for the stepper (import_state). Two derivations of one fact.

## DP-04 — Competition slug: persisted copy vs shipped constant (public-launch trap)

> **Resolved in code (v1.2.6):** the slug is never stored unless deliberately
> overridden — `session.slug_override = null` means "track the shipped
> constant", the migration collapses the current/retired slugs to null, and
> `tests/test_slug_swap.py` proves the launch-swap case: a persisted
> v1.2.5-era slug plus a bumped `COMPETITION_SLUG` resolves to the NEW slug
> while an explicit user override survives. Launch still requires the
> RETIRED_SLUGS same-commit step (LAUNCH-VERIFY).

- **Class:** D3 + D1
- **Steps:**
  1. On today's build, open Predict + Submit once with Kaggle connected. The connection
     probe fills the empty slug field with `default_slug` (ui.html:4817-4819); the next
     predict/submit/sync persists it into `submit.competition_slug` ([S-save]).
  2. Time passes. The plugin ships the public competition with a new
     `COMPETITION_SLUG` (predictor.py:33, "SWAP AT PUBLIC LAUNCH").
  3. Tester updates the plugin and submits.
- **Divergence:** `applyConfig` restores the old test-competition slug (non-empty, so the
  default-fill at ui.html:4817 never runs again); the shipped constant says the public slug.
  The submission goes to the retired test competition (`…comepetition-test`, whose typo'd
  slug CONTEXT.md says must not survive into the public comp).
- **Consequence:** silent, survives to submission — the submit even *succeeds* if the test
  comp still exists. Kaggle history/leaderboard views also follow the stale slug
  (ui.html:5347, 5326).
- **Severity:** high at launch, zero today. The `slug == "[SLUG]"` band-aids
  (predictor.py:550, 614) show this exact class has already bitten once with a placeholder.
- **Root cause:** a value that is 100% derivable (server constant, participant almost never
  overrides) is stored, and the stored copy is read without validation against the current
  constant.

## DP-05 — Device: Train's device vs Predict's device

- **Class:** D1
- **Steps:**
  1. On Train → Advanced, set Device to `cpu` (say, debugging a CUDA fault) and train.
  2. Open Predict + Submit and run inference.
- **Divergence:** predict uses `submit.device` (still blank → auto → CUDA), not the value
  the user just set; two fields (ui.html:830, 1048), two config keys (`train.device`,
  `submit.device`), one machine-level fact.
- **Consequence:** behavior differs between steps with no indication; the v1.2.2/1.2.3
  device-'0' migration had to patch **both** copies (config_store.py:47 iterates
  `("train","submit")`) — the migration's shape is itself evidence of the duplication.
- **Severity:** low — visible in the log line (`pr:704`), auto usually right.
- **Root cause:** per-tab snapshots store a per-machine fact twice.

## DP-06 — Initial-load entry races config rehydration (saved tab ≠ Import) ⚠ code-verified-only

- **Class:** D4
- **Steps:**
  1. Work in a custom project so `train.*` holds custom table URLs; end the session on the
     Train tab (`localStorage['kg.activeTab']='train'`, ui.html:1276).
  2. Reload the page on a cold/slow worker (the round-1 cold-worker latency case).
- **Divergence:** the end-of-script dispatch (ui.html:5445) calls `showTab('train')` →
  `trOnTabEnter` → `kgSyncFieldToProject` **synchronously at load**, while `configLoaded`
  (ui.html:1917) is still in flight. The sync computes its stale-field list from the
  **pre-restore DOM** (empty URLs, `kg-project` = markup default) and fetches defaults for
  `exdark-competition`. Both orderings of the two async returns corrupt state:
  - `/config` first: `applyConfig` fills the saved custom URLs → the sync's fetch lands and
    overwrites both fields with default-project/`initial` URLs (its stale list was computed
    when they were empty) → `saveTabConfig('train')` (ui.html:1826) **persists the clobber**.
  - defaults first: sync writes + persists default URLs, then `applyConfig` restores the old
    saved values into the DOM → DOM and `ui_config.json` now disagree until the next save.
- **Consequence:** a saved custom-project Train config can be silently reset to the default
  project; this is a plausible second engine for the very cross-project mixtures v1.2.5
  patched. Same race exists for `ps-test-url` via `psOnTabEnter` (ui.html:4389) when the
  saved tab is Submit.
- **Severity:** medium — window is one fetch round-trip (seconds on a cold worker),
  consequences are silent and persisted.
- **Root cause:** tab-entry hooks run at dispatch without awaiting `configLoaded`; nothing
  serializes "restore, then follow, then verify".

## DP-07 — Submission outcome: three stores, one best-effort writer ⚠ code-verified-only

- **Class:** D5
- **Steps:**
  1. Predict (job P), then Submit (job S) — accepted by Kaggle.
  2. Let the cross-write onto P fail: `update_job_facts` (jobs.py:277-299) is best-effort
     with silent `except` (jobs.py:299) — e.g. P's record pruned between predict and submit
     (50-record cap, jobs.py:36), or a transient disk error.
- **Divergence:** `run_kaggle_submit` wrote the outcome to three places — S's facts
  (pr:816), P's facts (pr:817, failed), `submit_state` (pr:821-838, succeeded). Status
  history renders P's record → "CSV generated (not submitted)" (ui.html:5148); the Predict
  tab's revisit renders `submit_state` → "Submitted · #ref" (ui.html:5041-5044).
- **Consequence:** two surfaces disagree about whether the daily attempt was spent.
- **Severity:** low probability, medium confusion when hit.
- **Root cause:** one fact fanned out to three stores so each reader can stay one-hop; no
  single store all readers share.

## DP-08 — Revisit basis vs pruned job store

- **Class:** D3
- **Steps:**
  1. Predict successfully (snapshot `predict_state` written, CSV on disk).
  2. Generate ≥50 newer jobs (rounds of import/train/predict over weeks — the cap is
     jobs.py:36, pruned newest-first at jobs.py:97-103) so the predict record is deleted.
  3. Reload, open Predict + Submit → revisit view renders, step 2 unlocked
     ("Submitting: <run> · from a previous session").
  4. Click Submit to Kaggle.
- **Divergence:** `predict_submit_state` validated only the **CSV on disk**
  (predictor.py:858-860), not the job record; `/validate/submit` requires the record
  (routes.py:310-317) → 400 "No validated prediction CSV found for that job. Run inference
  first." while the panel above it displays that exact validated CSV. "Download CSV" from
  the same panel 404s the same way (routes.py:362-366).
- **Consequence:** visible contradiction; the remediation ("run inference first") is
  correct but the UI just asserted the opposite.
- **Severity:** medium — no data loss, but a guaranteed eventual state for any long-lived
  install that revisits an old prediction.
- **Root cause:** persisted `predict_state.job_id` read without validation against the
  environment that can invalidate it (the pruning job store); two validators of
  "submittable prediction" (CSV-exists vs record-exists) disagree by design.

## DP-09 — Import revisit snapshot vs the edited (hidden) form

- **Class:** D1
- **Steps:**
  1. Import successfully into project `A`, table `initial` → revisit view (form hidden).
  2. The saved form still holds `A`/`initial`. Now suppose the user earlier typed project
     `B` in the form and let it settle *without* importing (settle-save persists `B`), then
     reloaded: the revisit view renders snapshot `A` (import_state), while the hidden form
     and `import.project_name` hold `B`.
  3. Click "Re-import fresh" on a split from the revisit view.
- **Divergence:** the re-import runs with the **snapshot's** values (`kgRevisitSrc`,
  ui.html:2594-2597 ← 2683-2687) — project `A` — while the persisted form config and
  `kgCurrentProject()` (which Train/Predict follow) say `B`. Two readers of "what would an
  import use right now": the revisit action uses A, every other tab is following B.
- **Consequence:** re-import refreshes project A's tables while Train's gate is waiting for
  project B; combined with DP-03 the stepper stays ✓ throughout.
- **Severity:** low — requires the edit-then-abandon sequence, but fully silent.
- **Root cause:** the same three facts exist as snapshot copy (`import_state.*`), form/cfg
  copy (`import.*`), and in-memory copy (`kgRevisitSrc`); actions pick different copies.

## DP-10 — The sync side-effect persists whole unvalidated forms

- **Class:** D4 + D3
- **Steps:**
  1. On Train, type `999` into Epochs (inline error appears on blur; Start disabled).
  2. Go to Import and change the project name; let it settle → `kgSyncFieldToProject`
     re-points Train URLs and calls `saveTabConfig('train')` (ui.html:1826).
  3. Reload the page.
- **Divergence:** `epochs: '999'` is now the *persisted last-used value* and `applyConfig`
  restores it without validation (ui.html:1885-1896) — the restored form silently carries
  an out-of-bounds value with no inline error until the field is blurred or Start is
  clicked. The run-start save path validates first (trValidateAll at ui.html:4063 precedes
  the save at 4074); the sync path is the only unvalidated writer.
- **Consequence:** low practical harm (server still rejects), but the config store's
  claimed semantics — "last-used values" (routes.py:378) — now include values never used
  and never valid.
- **Severity:** low.
- **Root cause:** a healer for one field-group snapshots the whole tab; persistence is not
  gated on validity.

## DP-11 — Split identity: a slot's URL vs the split the slot means (found in round-3 browser verification, 2026-08-13)

> **Resolved in code (v1.2.6, same day):** three layers — the revision
> picker is scoped to its field's split (prevention; there is no legitimate
> cross-split pick in this workflow), the Train/Predict gates assert the
> dataset segment and non-identical train/val with a message naming the
> mismatch (detection), and `trainer.validate_table_urls` /
> `predictor.validate_test_table_url` reject server-side from both
> /validate/* and the job targets (enforcement — the host /run path never
> traverses /validate). One predicate (`classify_override` + its JS mirror)
> governs migration, runtime override capture, and read-time pruning, so
> `session.overrides` is valid-by-construction. Note: the
> identical-train/val rule is unreachable once both dataset asserts hold
> (the datasets must differ, so the URLs must) — defense in depth against
> future naming changes; do not read its green test as live coverage.

- **Class:** D3 (a persisted/typed value read without validation against
  its context) + D2 flavor (the slot's meaning is the shadowed canonical
  fact).
- **Steps (reproduced live):**
  1. On Train, open the revision picker on "Train table URL". The popover
     listed ALL datasets (exdark_test / exdark_train / exdark_val).
  2. Pick a revision from EXDARK_VAL. Accepted into the train field.
  3. Gate: existence-only → **green**: "Tables verified: exdark_val/initial
     · exdark_val/round2 · trains on these exact revisions".
  4. v1.2.6's override capture persisted it: the mistake survived reload.
- **Divergence:** the URL says exdark_val; the slot means exdark_train. Two
  readers of the split identity disagree, and no check compares them: the
  gate tested existence, `validate_settings` never inspected URLs, and —
  the reason Layer 3 exists — `.latest()` resolves within one dataset's
  lineage, so `use_latest` faithfully preserves the wrong dataset. Without
  a server-side assert there is NO point in the pipeline that would notice.
- **Severity (calibrated):** not a cheating vector — training on val yields
  a worse model and the leaderboard scores the held-out test set. It is a
  **silent-wrong-results footgun**: green gate, completed run, four PASS
  provenance assertions, plausible mAP, nothing anywhere indicating the
  mistake. Provenance records model/imgsz/pretrained/sha — not split
  identity — so an affected run is indistinguishable after the fact
  (LAUNCH-VERIFY: candidate provenance addition; scripts/
  scan_cross_split_runs.py covers the surviving job records).
- **Predict variant:** same picker hole on the test field; the row-count
  backstop (715) fails the job before inference, but its old remediation
  ("re-run Import") was misleading for this cause — reworded, and the
  dataset assert now fires first with the specific message.
- **Root cause:** an individually-valid value passing a check that tests
  one property (existence) while its contextual property (which split) is
  asserted nowhere. Pre-existing, not a v1.2.6 regression — but v1.2.6's
  override persistence upgraded it from transient to durable, which is
  what surfaced it.

---

## Where coherent-follow fires — the divergences the code already expects

Per the audit brief: each call site of the self-healing machinery marks a divergence the
design anticipates instead of preventing.

| Site | Heals | Doesn't heal (the gap it proves) |
|---|---|---|
| `kgImportCfgSettled` → sync (ui.html:2216-2223) | table-URL fields after a settled project change | `tr-project` (DP-01), table name (DP-02) — and its save side-effect cements DP-01 and creates DP-10 |
| `trOnTabEnter` → sync (ui.html:3956) | Train URLs on tab entry | same; races rehydration at initial dispatch (DP-06) |
| `psOnTabEnter` → sync (ui.html:4389) | test URL on tab entry | same; DP-06 |
| `_migrate` device_blank_default (config_store.py:42-52) | the two saved device copies, once | the duplication itself (DP-05) — new divergences need new migrations |
| `_mark_if_orphaned` / `_normalize_record` (jobs.py:328-362) | job records vs process death | legitimate read-time validation (keep — process death is a real environment change, not a store disagreement) |
| Display-time epoch clamp (routes.py:237-243) | pre-guard records' epochs+1 | legitimate display migration (keep) |

The first four heal disagreements between **stores the plugin itself writes** — exactly the
class a single canonical store removes. The last two validate against the **environment**
(process identity, historical writer bug) and stay under any design.

## Disproven suspicion — the "Continue →" chips do NOT bypass tab-entry rehydration

Verified: every entry path into a tab converges on `showTab` → `kgApplyTab`, which fires
the tab-enter hooks — the tab-bar click (ui.html:1289), keyboard (1291-1295), the Loop
links (1310-1323), "Continue to Train" (2430-2434), "Continue to Submit" (3673),
"Continue to Status" (4877-4880), and Status's "Open tab" links (5209-5213). There is no
chip-specific bypass. The two real entry-path holes are: the **initial dispatch** racing
the config load (DP-06), and `?kgdev` fixtures skipping the hooks by design
(ui.html:3951, 4383, 5428 — intended, fixtures never persist).

## Severity ranking

1. **DP-01** high — silent, shipped, hit by a tester, breaks the Loop.
2. **DP-04** high at public launch — silent, survives to submission (pre-launch gate item).
3. **DP-06** medium — silent persisted corruption, race-gated; plausible co-author of the
   round-2 mixtures.
4. **DP-02** medium — visible dead-end, misleading remediation.
5. **DP-08** medium — guaranteed eventual contradiction on long-lived installs.
6. **DP-03** low-medium · **DP-05** low · **DP-07** low · **DP-09** low · **DP-10** low.
