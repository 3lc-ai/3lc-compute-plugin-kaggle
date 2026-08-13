# v1.2.6 pre-tag checklist

Nothing tags until every line is ticked. Rules of the exercise: RELEASING.md
order (tag → repo catalog.json → Rishikesh mirrors the gist), never retag,
and the footer-version heuristic is only trustworthy again AFTER the tag —
dev wheels carry 1.2.5 metadata until the version bump ships in the tagged
build. Run `pytest` last thing before tagging (44+ tests, both real-world
fixtures).

## Tier 3 — manual verification on the dev machine (GPU)

- [ ] Two-epoch GPU train from the session project: run lands in the same
      project as the three tables (SMOKE_TEST §2 wording — a run anywhere
      else is a blocker, not a variation).
- [ ] Full 715-image predict; 5/5 format checks; no OOM after train in the
      same session.
- [ ] Real Kaggle submit accepted (or a friendly state with the CSV kept);
      Status history row renders the outcome vocabulary.
- [ ] Four provenance PASS assertions, checkpoint sha256 `0ebbc80d4a76…`
      unchanged.
- [ ] Dashboard / Explore links open non-empty (object_service param
      present; Object Service running).

## Migration — against restored copies of BOTH real fixtures

Restore each to the redirected home, let a v1.2.6 worker be its first
reader, then assert:

- [ ] `ui_config.oldstack.json` (no `_migrations` at all): both markers
      appear, `session.device == ""` (ordering), branch recorded, retired
      keys gone, session project = the artifact's project when tables
      resolve.
- [ ] `ui_config.newstack.json` (three-way divergence): session project
      follows the tables on disk, not the edited form; overrides empty
      (cross-project URLs dropped).
- [ ] The `_migrations.session_v1` marker value matches what the disk state
      at that moment justifies (`import_state` vs
      `import_form_urls_unresolved` — the worker log names any unresolved
      URLs).

## Session-refactor specifics

- [ ] **F2 — override preservation, browser-real:** run an actual
      fix-labels Loop pass (edit labels in the Dashboard → new revision →
      pick it via the revision picker). Reload: the picked revision
      survives in the field and in `session.overrides`. Then change the
      project on Import: override cleared, fields re-derived, gate amber.
      (Unit-tested in `test_same_project_revision_override_preserved`;
      never yet exercised against a real revision chain.)
- [ ] **DP-02 — non-default table name:** import with Table name
      `round2` (or any non-`initial`). Train and Predict derive URLs ending
      `/tables/round2` and their gates go green with no hand-pasting.
- [ ] **Stale-fragment test:** with an old (pre-v1.2.6) cached fragment
      against the new worker, config saves 400 (worker log shows the
      retired-keys message) and NOTHING is written to the store; a
      hard-refresh fixes it. This is the B3 behavior the tester note
      documents.
- [ ] **Fresh-install case:** delete `ui_config.json`, open the page:
      fields filled from shipped defaults (served session), no migration
      noise, first settle-save creates `session` + markers
      (`session_v1: "fresh"`).
- [ ] Remaining C3 items from the Phase 2 checklist not yet reported:
      revisit-reads-session (6), DP-10 clamp (7), DP-08 pruned-record (8),
      `?kgdev` fixtures render + never persist (9), console clean (10).

## DP-11 — split identity (added after the round-3 finding)

- [ ] Open the revision picker on each of the three URL fields: the
      popover offers ONLY that field's dataset (train -> exdark_train,
      val -> exdark_val, test -> exdark_test).
- [ ] Hand-paste a cross-split URL into the Train field (e.g. the
      exdark_val table): gate goes amber with the SPECIFIC message
      ("Train table URL points at exdark_val; expected exdark_train"),
      no wrong-project hint, Start disabled; the value is NOT persisted
      (reload re-derives the correct URL).
- [ ] Same hand-paste on the Predict test field: amber names the split;
      Run inference stays disabled.
- [ ] M1 runtime twin (the JS mirror is not unit-tested — this step IS
      its coverage until Playwright): pick the revision that equals the
      derived default via the picker; confirm `session.overrides` stays
      empty; then change the Table name on Import and confirm the field
      FOLLOWS the new name (nothing froze it).
- [ ] Server backstop: with the gate somehow bypassed (curl /run or an
      edited request), a cross-split train body is rejected with the
      dataset-naming error, not trained.
- [ ] Run `scripts/scan_cross_split_runs.py` against the machine's job
      store(s); file its output with the checklist (a clean result is
      not proof of absence — 50-record prune, header says so).

## Open items (decide before tag)

- [ ] H1 regression check (fix landed with the K1 audit): open
      `?kgdev=submit-results` — the connection card reads
      `participant`, never a real Kaggle handle; `?kgdev=train-state2` —
      the URL fields keep their demo values (no late overwrite from the
      live derivation). The only network requests on a fixture page load
      are `/config` and `/pipeline`.
- [ ] Version bump verified in the tagged build: pyproject + plugin.toml +
      catalog manifest all `1.2.6`, footer reads v1.2.6 after a catalog
      install.
