# State audit — DP-01 verdict, fix scope, coverage gaps (2026-08-13, v1.2.5 @ 54af3a5)

Companions: [state-inventory.md](state-inventory.md) · [divergence-paths.md](divergence-paths.md).
No code was changed this session; this is the map, not the fix.

---

## 1. DP-01 root cause — verdict

**(c), with (a) true at the storage layer as the reason no later moment ever heals it.**

Precisely:

- **(c) confirmed — primary mechanism.** The Train tab's Project field is an independent
  input whose only default is the hardcoded markup literal `value="exdark-competition"`
  (ui.html:859), and **no code path ever consults imported state for it**. The project-follow
  machinery introduced in v1.2.1 syncs exactly three fields — `tr-train-url`, `tr-val-url`,
  `ps-test-url` (the `split` map at ui.html:1817) — and `tr-project` is not one of them.
  `kgCurrentProject()` (ui.html:1790) is read by pickers, gates, and default-derivations,
  never by anything that writes `tr-project`. At Start Training the field's value goes into
  the job body verbatim (ui.html:4088) and becomes the Run's project via
  `trainer.validate_settings` (trainer.py:272).
- **(a) confirmed as the persistence structure, not the trigger.** The same logical fact is
  stored under two keys that never meet: Import's settle-save writes
  `import.project_name` (ui.html:2213-2235); the Train form persists and restores
  `train.project_name` ([T-save] / applyConfig). So a reload restores the divergence
  rather than healing it. Aggravator: the v1.2.5 coherence fix re-persists the whole Train
  form when it re-points the URL fields (ui.html:1826), stamping the stale `tr-project`
  value into `train.project_name` at the exact moment it heals the URLs.
- **(b) ruled out.** Train's tab-entry hook *does* run on every entry (all entry paths,
  including the Continue chips, converge on `showTab` → `trOnTabEnter` — verified,
  ui.html:1281, 2430) and the config had been written; the hook simply doesn't cover this
  field. Rendering order is irrelevant: no rehydration at any time would read
  `import.project_name` into `tr-project`.
- **(d) ruled out.** The settle-save debounce is 600 ms + blur (ui.html:2226-2235), and the
  import itself force-saves at start (ui.html:2608). The tester's tables landed in
  `exdark-competitionv2`, proving the Import-side value was written and used. Flush timing
  is not in the causal chain.
- **(e) n/a.**

Matches the available evidence: the tester's Train field showed exactly the default
(fresh `train.project_name`), and the run's project was brand new with zero tables
(created on demand by the Run, not reused).

### The 30-second discriminating test ((c)/(a) vs runner-up (b))

> On Import, change Project to `probe-x`, click elsewhere (blur), **press F5**, open Train:
> if the Project field still shows `exdark-competition`, it's (c)/(a) — the field never
> consults imported state even from a cold start; if it shows `probe-x`, it was (b) — a
> stale render that rehydration fixes.

Expected result: still `exdark-competition`. (A reload replays `applyConfig`, which reads
`train.project_name`, not `import.project_name` — under (b) the reload would have healed it.)

---

## 2. Fix scope proposal (not a fix)

### Shape

One canonical **session object**, persisted as a new `session` key in `ui_config.json`;
tabs render projections of it and no tab owns a default.

```
session: {
  project_name:   str,          // owned here; Import's field is its editor, not its owner
  table_name:     str,          // ditto
  dataset_yaml:   str,          // ditto
  device:         str,          // one machine fact (today: train.device + submit.device)
  slug_override:  str | null    // null = "track the shipped COMPETITION_SLUG"; a string
                                // only when the user deliberately diverged from the default
}
```

Principles applied:

- **Tabs render projections; no tab owns a default.** The Train "Project" input is deleted;
  the run's project is the session project by construction (rendered as a read-only
  `.kg-locked-row`-style fact in the 3LC-settings section, same calm-lock idiom). The three
  table-URL fields become **derived by default**: value = `derive(session.project_name,
  session.table_name, split)` recomputed at render/gate time; a hand-pasted URL is stored
  as an explicit per-field override that a project/table change clears (with the gate's
  existing amber to say so). Device becomes one session field rendered in both tabs.
- **Derive, don't store anything computable.** Persisted `train_table_url` /
  `val_table_url` / `test_table_url` disappear except as explicit overrides; the slug is
  never stored unless overridden (killing DP-04: shipping a new `COMPETITION_SLUG` takes
  effect on every install whose override is null); `import_state` keeps only what is not
  derivable (tables/rows/reused/checks/job_id) and drops its private copies of
  project/table_name/dataset_yaml (killing DP-09's third copy; `kgRevisitSrc` reads the
  session).
- **Validate on read.** One `loadSession()` on the client validates and clamps everything
  `applyConfig` currently pastes raw (bounds via the existing `TR_BOUNDS` mirror — DP-10);
  `predict_submit_state` additionally requires the predict job record to exist, not just
  the CSV (DP-08); `slug_override` equal to the current or any retired shipped slug
  collapses to null (DP-04 belt-and-braces).
- **Sequence the load.** Tab-entry hooks and the initial dispatch await `configLoaded`
  before any state read/write (one promise-gate on `trOnTabEnter`/`psOnTabEnter` and the
  dispatch, killing DP-06). With derivation replacing the persisted URLs, there is nothing
  left for a race to clobber.

### Files touched

| File | Change |
|---|---|
| `src/tlc_plugin_kaggle/ui.html` | The bulk. Add `kgSession` (load/validate/save, ~90 LOC). Convert URL fields + device + slug to projections (~40 LOC rewiring). Delete `tr-project` form group (markup ~856-860 + CFG_FIELDS entries). **Delete `kgSyncFieldToProject`, `kgFollowedProject`, and the three follow call-sites** (ui.html:1806-1831, 2211-2225 sync branch, 3956, 4389 — the coherent-follow machinery; a design where stores can't disagree needs no self-healer). Collapse the two blank-prefill blocks (3434-3451, 4511-4519) into the derivation. Gate the dispatch/tab-enter hooks on `configLoaded`. |
| `src/tlc_plugin_kaggle/config_store.py` | Add `"session"` to `_ALLOWED_TABS`; add `session_v1` migration (below), ~30 LOC. |
| `src/tlc_plugin_kaggle/importer.py` | `verified_import_state` synthesized branch reads `cfg.session` instead of `cfg.import` (~5 LOC). |
| `src/tlc_plugin_kaggle/routes.py` | No route changes required. UI starts passing `&table=` to the existing `/tables/defaults` param (rt:164) — fixes DP-02 for free. |

**Untouched: trainer.py, predictor.py (job logic), jobs.py.** The job param schema is
unchanged — the UI still sends `project_name`, `test_table_url`, `device`, etc. in the job
body; only where those values come from changes. Locked contract, provenance recording,
host gating, plugin-run-only enforcement: zero delta.

### LOC estimate

~250 lines touched in ui.html + ~35 backend. Additions ≈ +135 (session module,
projection wiring, migration); deletions ≈ −100 (sync machinery ~55, prefill blocks ~25,
tr-project group + CFG entries ~12, revisit-copy plumbing ~8). **Net ≈ +35 — and the
deleted 100 includes the entire self-healing layer**, which is the point: the remaining
code cannot express the disagreement the healer existed to repair.

### What gets deleted (explicit list)

- `kgSyncFieldToProject` + `kgFollowedProject` + the settle/tab-enter follow calls
  (the coherent-follow machinery, all of it).
- The `tr-project` input and both persisted keys `train.project_name` /
  `train.{train,val}_table_url` / `submit.test_table_url` / `submit.competition_slug` /
  `submit.device` (as always-persisted values; URL/slug survive only as explicit overrides).
- `import_state.{project,table_name,dataset_yaml}` duplicate copies; `kgRevisitSrc`'s
  private copy; `submit_state.slug` (dead store).
- The `'[SLUG]'` band-aids (predictor.py:550, 614) once the migration lands — flagged for
  a later cleanup commit, not this one (A3: separate rider).

Kept: `_mark_if_orphaned` / `_normalize_record` / the epoch display-clamp — those validate
against the environment (process death, historical writer bug), which no store design
removes.

### Migration (`session_v1`, one-shot marker in `_migrations`)

For existing mixed configs (the v122check/v124check2 case):

- `session.project_name := import.project_name` — **Import's copy is authoritative** because
  it is the one that created the tables on disk; `train.project_name` is exactly the value
  this bug class corrupts. `session.table_name := import.table_name`,
  `session.dataset_yaml := import.dataset_yaml`.
- `session.device := train.device or submit.device` (post-`device_blank_default`, first
  non-empty; both copies dropped).
- `session.slug_override := submit.competition_slug` **iff** it differs from the shipped
  `COMPETITION_SLUG` and isn't a known retired slug/placeholder, else null.
- Drop the persisted URL keys (re-derived on first load; a URL whose project differs from
  `session.project_name` would have been the mixture — it is discarded by design, and the
  gate re-verifies immediately). Existing `import_state` snapshots stay valid (tables
  verification unchanged).
- Runs/jobs/provenance need **no migration** — job records and Run parameters are untouched.

### Blast radius on Train / Predict / provenance — zero, by construction

- Train job body: same keys, same server validation (`build_train_kwargs` /
  `validate_settings` unchanged). A run started after the fix records identical provenance.
- Predict/Submit: same params; `plugin-run-only`, host gate, CSV validation untouched.
- Provenance: the 4 assertions read the Run record (trainer.py:344-374) — no code in the
  proposal touches that path.
- Fixtures: `?kgdev` states set fields directly and never persist; the deleted `tr-project`
  field is not referenced by any fixture (verified: `trDevForce` ui.html:2916-3082 touches
  URLs/epochs only). Fixture updates limited to removing nothing-that-exists — checked.
- One **deliberate behavior change to sign off**: training a Run into a *different* project
  than the tables' (possible today via `tr-project`) goes away. For this competition that
  freedom is exactly the bug; if someone needs it (e.g. `control-sanity` runs), the
  session project is still editable on Import, or the control script bypasses the UI as it
  already does today.
- Fragment rule (CLAUDE.md §B): ui.html + config_store changes ⇒ worker **reload** after
  landing; no venv re-provision; catalog installs see it at the next tag.

---

## 3. Coverage gaps (Deliverable 5)

**The repo has zero automated tests.** No `tests/` directory, no CI. The two existing
verification instruments are structurally unable to catch this class:

- `SMOKE_TEST.md` — a manual checklist that **hardcodes the default project**
  ("the run appears in the 3LC Dashboard project (`exdark-competition`)", SMOKE_TEST.md:54).
  Every renamed-project path is outside its reachable space; DP-01 passes the smoke test
  *by definition* because the orphan run lands in the project the checklist looks in.
- `?kgdev` fixtures — static, fixed to `exdark-competition`, never persist
  (by design, ui-notes §Fixtures). They verify rendering, not state flow.
- `exit_gate_125 C1` (CONTEXT.md:37) — a manual, session-scoped coherence assertion over
  `ui_config.json`; not repeatable, and it asserts coherence of the *URL* fields, which is
  the part v1.2.5 fixed — it would not flag `train.project_name`.

Per path:

| DP | Caught by anything existing? | Test that should exist |
|---|---|---|
| DP-01 | **No** (smoke test hardcodes the project) | `test_dp01_run_project_follows_import_project` — import into project X, start train, assert the `/run` body's `project_name == X` |
| DP-02 | No | `test_dp02_table_name_flows_to_defaults` — import with `table_name='round2'`, assert Train/Predict default URLs end in `/tables/round2` and the gate is green |
| DP-03 | No | `test_dp03_stepper_and_gate_agree` — change project without re-import; assert stepper Import-step and Train gate report the same done/not-done |
| DP-04 | No | `test_dp04_shipped_slug_wins_unless_overridden` — config with old slug + new `COMPETITION_SLUG`; assert effective submit slug is the new constant (and an explicit override survives) |
| DP-05 | No | `test_dp05_device_single_fact` — set device in one tab; assert the other tab's job body carries it; assert config holds exactly one device key |
| DP-06 | No | `test_dp06_no_writes_before_rehydration` — delay `GET /config`; assert no `POST /config` and no field mutation happens until it resolves (both orderings) |
| DP-07 | No | `test_dp07_submission_outcome_agrees` — make `update_job_facts` fail; assert Status history and revisit render the same outcome |
| DP-08 | No | `test_dp08_basis_requires_job_record` — delete the predict job file, keep the CSV; assert `predict_submit_state` returns empty (or a degraded, non-submittable state), never an unlocked step 2 |
| DP-09 | No | `test_dp09_revisit_rerun_uses_displayed_values` — snapshot A + form B; assert the re-import request body equals what the revisit view displays |
| DP-10 | No | `test_dp10_persisted_values_are_valid` — force a whole-form save with `epochs=999`; assert the store rejects/clamps, or the restore path flags it |

Plus the invariant that codifies exit_gate_125 C1 permanently:
`test_config_coherence_invariant` — after any sequence of the write paths in the
inventory, `ui_config.json` names exactly one project (and one table name, one device,
one slug decision) across all keys. Under the session-object design this test is nearly
vacuous — which is the desired end state: the invariant holds by construction, and the
test exists to keep it that way.

Harness note (follow-on work, not this session): DP-04/05/07/08/10 and the migration are
plain pytest against `config_store` / `importer` / `predictor` pure functions (no torch);
DP-01/02/03/06/09 need the fragment running — Playwright against a stubbed compute API is
the realistic layer, and the stub is small (the fragment talks to ~12 routes, all
enumerated in the inventory).

---

## 4. Theory verdict

**Confirmed.** All ten paths, and all three historical bugs (run-start-only save,
saved-device-'0', the orphaned run), reduce to the same gap: a locked linear workflow whose
state is stored as independent per-tab values with per-tab hardcoded defaults, patched
after the fact by follow/migrate machinery that itself writes more per-tab state. They are
one architectural bug with ten faces, and the fix that removes the class also deletes the
machinery that managed it.
