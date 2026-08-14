# CLAUDE.md — kaggle-exdark plugin (stability phase: round-2 testing)

Vocabulary lives in [CONTEXT.md](CONTEXT.md). This file is the operating
protocol; depth lives in the docs linked in §E — link, don't duplicate.
Rules marked **[codified]** existed only as working practice until written here.

## A. Hard rules

1. **No silent assumptions.** If the task is ambiguous or conflicts with any
   doc in §E, state the conflict and wait. Never pick an interpretation
   silently. [codified]
2. **No over-engineering.** Smallest change that resolves the finding. If a
   fix wants to exceed ~2x its apparent size, pause and report before
   continuing (the circuit-breaker rule). [codified]
3. **No orthogonal changes.** Touch only what the finding requires. A Predict
   bug never "improves" the Train tab in passing. Refactors are their own
   proposed task, never a rider. [codified]
4. **Plan first on non-trivial work.** Anything beyond a one-file fix: plan +
   conflicts + fragment impact, then wait for go-ahead. [codified]

## B. Repo operating rules

- **Branches.** Work on `port/0.2.x` (the v1.2.x line). `develop` is frozen
  v1.1.x. The 0.1.x service loads the plugin LIVE from this working copy
  (`plugin_dirs` → `src/`), so the checkout must sit on `develop` whenever
  the old service runs; the 0.2.x service installs from git tags and never
  reads the checkout. If both are needed, use a git worktree for port work.
  (PORT_PLAN addendum; TESTER_SETUP_0.2 appendix; README Appendix A.)
- **The frozen v1.1.x world is never touched**: the old Hub venv, the real
  `~/.3lc-compute/settings.json` (the 0.1.x writer silently drops 0.2.x keys),
  its key store and registered plugins. All 0.2.x state lives in
  `3lc-hub-next/` under a redirected home. (PORT_PLAN §2.)
- **Fragment rule.** Any change to `ui.html` or `plugin.toml` means the
  running install is stale. End the task by stating which applies under
  0.2.x: worker **reload** (code/fragment edits; kills the worker, next
  request respawns — never mid-train), venv **re-provision** (`[kaggle]`
  extra / dependency changes), or **fresh install from a new tag** (catalog
  installs never see working-copy changes). (ui-notes "0.2.x worker model".)
- **UI changes obey the playbook** (docs/ui-notes.md — decisions there are
  settled, not re-litigated): six-state machines, motion tokens + the four
  motion rules, the monochrome SVG icon set (no emoji, ever), copy tone
  (inform, don't instruct), NO em dashes in rendered copy, reduced-motion
  parity, `?kgdev` fixtures updated alongside state changes, fixtures always
  render the participant view.
- **The locked contract is untouchable**: pinned yolo11n.pt init
  (sha256-verified) + imgsz 640 enforcement, provenance recording (4
  assertions), host gating, plugin-run-only predictions for participants.
  Changes here are competition-design decisions, not code tasks. (ui-notes
  §13; training-sanity addendum.)
- **Releasing** (RELEASING.md, in order): push tag `vX.Y.Z` → update repo
  `catalog.json` (the source of truth; manifest must match `plugin.toml`,
  catalog id must equal plugin id) → tell Rishikesh to mirror the gist.
  Never edit the gist yourself; never retag an existing tag. [codified]
  Version string is identical in pyproject, plugin.toml, and the catalog.
  - Fixes are **invisible to catalog installs until tagged** — if a fix
    matters to an active tester, tag immediately; the commit-to-tag gap is
    where Copeland's round-2 device failure came from. [codified 2026-08-10]
  - The gist raw URL **lags edits by a few minutes** (CDN cache): verify via
    an incognito fetch after the lag, and paste the repo file **verbatim** —
    a hand-paste once introduced a duplicate-key error. Repo `catalog.json`
    is source of truth; the gist only ever mirrors it. [codified 2026-08-10]
- **Tests.** `tests/` is a pytest layer over config_store / migrations /
  predictor state (dev dependency group only — never ships, never enters the
  provisioned venv; the ui-notes no-new-dependencies rule governs runtime
  deps). Run before any tag; the migration tests pin the two real-world
  configs in `tests/fixtures/`. [codified 2026-08-13]
- **Identity.** Commit as Rishikesh-Jadhav only; no co-author trailers.
  Settings already enforce this — verify `git config user.name` if in doubt.
  [codified]
- **Windows-first.** Docs speak PowerShell 5.1; write files BOM-less
  [codified]. Service env vars: `TLC_COMPUTE_PLUGIN_VENV_KAGGLE_EXDARK`
  (W1 workaround, Windows-only) and `UV_TORCH_BACKEND=auto` (GPU torch in
  shop installs; no-op on non-NVIDIA hosts). Mac and remote-host deltas live
  in the TESTER_SETUP_0.2 macOS appendix and TESTER_SETUP_REMOTE.

## C. Tester-finding triage (round 2)

Findings arrive as `3lc-kaggle-diagnostics` blocks and Teams messages.

1. **Reproduce first** — from the diagnostics block (version header, inputs,
   checks, log tail) or the matching `?kgdev` fixture — before theorizing.
2. **Classify**:
   plugin bug → fix per A1–A4 ·
   platform/shop bug → the ledger + Gudbrand, not our code ·
   doc gap → fix the doc ·
   by-design → draft the tester-facing explanation (training-sanity.md is the
   model answer sheet; slow-hardware ≠ finding, only failure is).
3. **Fix**: update every fixture and doc the fix touches; log honest
   deviations (forced-changes-0.2.md pattern). State fragment impact (§B).
4. **Batch fixes toward the next tag**; tag per-fix only when a finding
   blocks all testers. [codified]

Where things live: platform-bug ledger = `../3lc-hub-next/PORT_PLAN.md` (§6
"Ledger items" + addendum; W-series defined in CONTEXT.md) · parked ideas =
docs/v1.2-ideas.md · LAUNCH-VERIFY sweep list = docs/v1.1-ideas.md · forced
changes = docs/forced-changes-0.2.md.

## D. Self-maintenance of these files

At the end of any session that ships a tag, changes a contract/process rule,
adds vocabulary, or resolves a tester-finding batch: check whether CLAUDE.md /
CONTEXT.md need a corresponding line, and update them in the same commit
series. These files are only useful while true. Keep them terse — one line
per fact, link out for depth. [codified 2026-08-10]

## E. Pointers

| Doc | Answers |
|---|---|
| docs/ui-notes.md | The UI playbook: state machines, motion, icons, copy, fixtures, v1 definition of done, 0.2.x worker/reload model |
| ../3lc-hub-next/PORT_PLAN.md (workspace) | 0.2.x compatibility matrix, coexistence/isolated home, W-series ledger, port history |
| RELEASING.md | Tag → catalog → gist release flow and why the gist exists |
| docs/TESTER_SETUP_0.2.md | Fresh-machine tester setup (Windows path + macOS appendix + 1.1.x-coexistence appendix) |
| docs/TESTER_SETUP_REMOTE.md | Remote Linux GPU host + browse-from-laptop setup |
| SMOKE_TEST.md | The 15-minute pass/fail checklist testers report against |
| docs/training-sanity.md | Why from-scratch ≈ 0.004 was normal; pretrained reference trajectory (~0.71 @ 10 ep val, 0.571 test); the answer sheet for "is training broken?" |
| docs/REMOTE_COMPUTE.md | Browser≠host surface audit, platform matrix, round-1 stumbles, round-2 submit policy |
| ../competition_exdark/reference/CONCLUSION_MATERIALS.md (workspace) | What gets published when the competition ends |
