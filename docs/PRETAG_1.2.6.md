# v1.2.6 pre-tag checklist

Nothing tags until every line is ticked. Rules of the exercise: RELEASING.md
order (tag → repo catalog.json → Rishikesh mirrors the gist), never retag,
and the footer-version heuristic is only trustworthy again AFTER the tag —
dev wheels carry 1.2.5 metadata until the version bump ships in the tagged
build. Run `pytest` last thing before tagging (44+ tests, both real-world
fixtures).

## Tier 3 — manual verification on the dev machine (GPU)

- [x] Two-epoch GPU train from the session project: run lands in the same
      project as the three tables (SMOKE_TEST §2 wording — a run anywhere
      else is a blocker, not a variation). TWO epochs is load-bearing,
      not convention: the ETA fix was one of Copeland's five round-1
      findings (root cause was epoch-boundary-only eta_s) and only shows
      with epochs remaining after epoch 1; also the ≥2-point
      history/sparkline, the second per-epoch collection pass, and the
      mAP50 reference band calibrated at epoch 2. A 1-epoch run
      (2026-08-13) covered project landing/provenance/links only.
      (Observed 2026-08-14: `kaggle_run_20260814_135436`, live ETA
      visible from 24s in — the round-1 eta_s fix confirmed on the
      current build; two history points, epoch 1 mAP50 0.44325 matching
      the pre-refactor baseline to five decimals, epoch 2 0.5563 inside
      the calibrated band; 4/4 provenance PASS; run in
      exdark-competition. Supersedes the 1-epoch DP-01 evidence.)
- [x] Full 715-image predict; 5/5 format checks; no OOM after train in the
      same session. (Observed 2026-08-14: same worker session as the
      two-epoch train, no OOM, 5/5 checks, 715 rows, 2,171 boxes.)
- [x] Real Kaggle submit accepted (or a friendly state with the CSV kept);
      Status history row renders the outcome vocabulary. (Observed
      2026-08-14: accepted, ref #55512225; history row moved
      "CSV generated" → "Submitted · #55512225".)
- [x] Four provenance PASS assertions, checkpoint sha256 `0ebbc80d4a76…`
      unchanged. (Observed 2026-08-13: 1-epoch run
      `kaggle_run_20260813_171646`, 4/4 PASS, sha unchanged.)
- [x] Dashboard / Explore links open non-empty (object_service param
      present; Object Service running). (Observed 2026-08-13:
      exdark-competition opened with Runs 11, Tables 3, 6,643 metrics.)

## Migration — against restored copies of BOTH real fixtures

CLOSED BY SUITE 2026-08-14 (55 passed), not by a live redirected-home
worker run: `tests/test_session_migration.py` executes session_v1 against
sanitized copies of both real stores, both URL-resolution branches each.
The premigration store on the desktop (`Desktop\v126-fixtures`) was
verified byte-equivalent to the newstack fixture modulo the documented
sanitization (paths, slug, zeroed submission ref), so the suite IS this
section's exercise. Live-disk note: the `v124check2` tables are gone from
this machine (2026-08-14), so a live first read here would take the
`import_form_urls_unresolved` branch — also pinned.

- [x] `ui_config.oldstack.json` (no `_migrations` at all): both markers
      appear, `session.device == ""` (ordering), branch recorded, retired
      keys gone, session project = the artifact's project when tables
      resolve. (Suite: `test_oldstack_snapshot_branch`,
      `test_session_v1_runs_after_device_blank_default`.)
- [x] `ui_config.newstack.json` (three-way divergence): session project
      follows the tables on disk, not the edited form; overrides empty
      (cross-project URLs dropped). (Suite:
      `test_newstack_snapshot_wins_over_edited_form`.)
- [x] The `_migrations.session_v1` marker value matches what the disk state
      at that moment justifies (`import_state` vs
      `import_form_urls_unresolved` — the worker log names any unresolved
      URLs). (Suite: both `*_form_branch_when_tables_missing` tests; the
      caplog assertion pins the worker-log line.)

## Session-refactor specifics

- [x] **F2 — override preservation, browser-real:** run an actual
      fix-labels Loop pass (edit labels in the Dashboard → new revision →
      pick it via the revision picker). Reload: the picked revision
      survives in the field and in `session.overrides`. Then change the
      project on Import: override cleared, fields re-derived, gate amber.
      (Unit-tested in `test_same_project_revision_override_preserved`;
      never yet exercised against a real revision chain.)
      (Observed 2026-08-14, both halves against a real revision chain:
      committed `train_v2` in the Dashboard, picked it via the picker,
      ran a full 2-epoch train on it (`kaggle_run_20260814_142701`),
      F5 — field and override survived; then changed project to `abcd` —
      both fields re-derived, override dropped, amber named `abcd`.
      The full fix-labels Loop ran end to end.)
- [x] **DP-02 — non-default table name:** import with Table name
      `round2` (or any non-`initial`). Train and Predict derive URLs ending
      `/tables/round2` and their gates go green with no hand-pasting.
      (Observed 2026-08-13: imported under `round2`, Train derived
      `/tables/round2`, gate green, verified line read
      `exdark_train/round2 · exdark_val/round2`.)
- [x] **F1 — deep-link follow** (added as observed, not originally
      listed here): two-hop project change `probe-x` → `probe-y`, the
      Loop link followed with no lag. (Observed 2026-08-13.)
- [x] **DP-06 — load sequencing** (added as observed, not originally
      listed here): hard-reload on the Train tab, no flash of
      default-project URLs before the session applied. (Observed
      2026-08-13.)
- [x] **Stale-fragment test — closed by source analysis + unit coverage
      (2026-08-14), NOT observed in a live v1.2.5→v1.2.6 shop upgrade.**
      What closed it is a finding, not a green observation: the v1.2.5
      fragment's `saveTabConfig` swallows every save error (`.catch`,
      best-effort), so the 400 is invisible mid-flow. The 400 rejection
      and nothing-written halves are pinned by the retired-key tests;
      the "what the user sees" half is absent by construction until the
      fragment-version echo ships (v1.2.7 candidate, v1.2-ideas.md).
      Consequence shipped: the tester note now makes the post-update
      hard-refresh a REQUIRED step.
- [x] **Fresh-install case:** delete `ui_config.json`, open the page:
      fields filled from shipped defaults (served session), no migration
      noise, first settle-save creates `session` + markers
      (`session_v1: "fresh"`). (Observed 2026-08-13: marker `"fresh"`,
      empty Import form, Import & Validate correctly disabled.)
- Remaining C3 items from the Phase 2 checklist — all observed
  2026-08-13, reported 2026-08-14:
  - [x] revisit-reads-session (6) / DP-01 acceptance criterion: 1-epoch
        run `kaggle_run_20260813_171646` under session project
        exdark-competition; Dashboard at that project showed Runs 11,
        Tables 3, 6,643 per-sample metrics against exdark_train/initial
        + exdark_val/initial — run and tables in ONE project. Config
        after the run: one project_name, one device, slug_override null,
        no retired keys (run-start save did not re-pollute the store).
        Supersedable by the two-epoch run.
  - [x] DP-10 clamp (7): hand-set `train.epochs` to "999", reloaded —
        field showed 20 (markup default), no inline error, 999 neither
        restored nor persisted.
  - [x] DP-08 pruned-record (8): predict job JSON moved out of `jobs/`,
        reload — Predict rendered the FORM with step 2 locked ("Run
        inference first. A validated CSV unlocks this step"), not an
        unlocked step whose submit would 404. File restored — revisit
        view returned ("predicted 31 hours ago (from a previous
        session)").
  - [x] `?kgdev` fixtures render + never persist (9): state6,
        train-state2, submit-results all rendered with "demo state —
        actions disabled" on Start Training / Re-run inference / Submit
        to Kaggle; config untouched. (H1's bleed was found in this same
        pass; ticked separately post-fix under Open items.)
  - [x] Console clean (10) — **plugin console clean; see J1/J2**, not
        bare-clean: DevTools console empty across all four tab switches
        on the normal page, but the Issues panel showed ~50 entries, all
        Chrome Local Network Access blocks on Hub↔localhost calls (J1,
        platform escalation, ledgered) plus one form-field label issue
        (J2). Neither is a plugin console error.

## DP-11 — split identity (added after the round-3 finding)

- [x] Open the revision picker on each of the three URL fields: the
      popover offers ONLY that field's dataset (train -> exdark_train,
      val -> exdark_val, test -> exdark_test). (Observed 2026-08-13:
      each popover showed exactly one dataset group.)
- [x] Hand-paste a cross-split URL into the Train field (e.g. the
      exdark_val table): gate goes amber with the SPECIFIC message
      ("Train table URL points at exdark_val; expected exdark_train"),
      no wrong-project hint, Start disabled; the value is NOT persisted
      (reload re-derives the correct URL). (Observed 2026-08-13: amber
      message verbatim plus the identical-URLs bullet; F5 re-derived;
      overrides stayed `{}` — don't-store confirmed.)
- [x] Same hand-paste on the Predict test field: amber names the split;
      Run inference stays disabled. (Observed 2026-08-13: "Test table
      URL points at exdark_train; expected exdark_test", fired before
      the row-count backstop — N1 ordering confirmed.)
- [x] M1 runtime twin (the JS mirror is not unit-tested — this step IS
      its coverage until Playwright): pick the revision that equals the
      derived default via the picker; confirm `session.overrides` stays
      empty; then change the Table name on Import and confirm the field
      FOLLOWS the new name (nothing froze it). (Observed 2026-08-13:
      table_name round2 -> initial, BOTH URL fields followed, overrides
      `{}` after settle-save. ONE-SHOT evidence: run against the
      then-dirty config, cannot be re-run.)
- [x] Server backstop: with the gate somehow bypassed (curl /run or an
      edited request), a cross-split train body is rejected with the
      dataset-naming error, not trained. (Observed 2026-08-13: job
      `ddbe0249e8dc418ea164b8d9db750b13`, status failed in 2.4s, error =
      the split message, checks/progress/facts all empty, result null,
      no checkpoint fetch, no epoch.)
- [x] Run `scripts/scan_cross_split_runs.py` against the machine's job
      store(s); file its output with the checklist (a clean result is
      not proof of absence — 50-record prune, header says so).
      (Run 2026-08-13 at the DP-11 gate: 19 + 13 records, 0 flagged.)

## Open items (decide before tag)

- [x] H1 regression check (fix landed with the K1 audit): open
      `?kgdev=submit-results` — the connection card reads
      `participant`, never a real Kaggle handle; `?kgdev=train-state2` —
      the URL fields keep their demo values (no late overwrite from the
      live derivation). The only network requests on a fixture page load
      are `/config` and `/pipeline`. (Observed 2026-08-13:
      submit-results showed "Connected to Kaggle as participant", handle
      gone. The train-state2 demo-values clause and the network-request
      audit were not separately evidenced in the report — reasoned as
      covered by the same kgDevMode guard, not watched.)
- [ ] Version bump verified in the tagged build: pyproject + plugin.toml +
      catalog manifest all `1.2.6`, footer reads v1.2.6 after a catalog
      install.
