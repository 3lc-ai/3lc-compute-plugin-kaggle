# CONTEXT.md — shared language (kaggle-exdark plugin)

One line per term. Depth: docs/ui-notes.md (UI), ../3lc-hub-next/PORT_PLAN.md (platform).

## Competition & contract

- **The Loop** — the product story the plugin demos: import → train → inspect/fix labels in the Dashboard (new table revision) → retrain on latest → predict → submit; the revision picker and the Loop's "fix labels" deep-link make it tangible.
- **the contract (locked)** — YOLOv11n from the official COCO-pretrained checkpoint, sha256-pinned, imgsz 640, pretrained=True; identical init for every participant; locked keys are rejected server-side, merged last.
- **pinned init / checkpoint sha** — `yolo11n.pt`, sha256 `0ebbc80d4a76…`; plugin downloads, hash-verifies, caches; the resolved path becomes the model arg so the Run records it.
- **provenance panel / 4 PASS assertions** — model · imgsz · pretrained · checkpoint sha256, read back from the Run record; renders "Verified provenance recorded"; proof of "trained through the verified pipeline".
- **host gate / local scoring** — the organizer machine holds the private answer key; local mAP@0.5 renders only there (`_meta.host`); absence of a score on a participant machine is by design, the Kaggle score is the real one.
- **plugin-run-only** — participants predict only from plugin-trained runs (single Plugin-run source, server rejects direct weights paths off-host); closes the train-elsewhere-submit-as-yolo11n loophole.
- **the slug** — `the-3-lc-low-light-object-detection-comepetition-test`; the "comepetition" typo is real (it's in the Kaggle URL) and immutable for the test comp; must not survive into the public one (LAUNCH-VERIFY).
- **starter kit** — the distributed data+config bundle (dataset.yaml + split images/labels); scripts were deliberately moved out to `reference/` (kit is data+config only).
- **entered participant** — Kaggle `user_has_entered=True` (accepted rules); required to submit; 3/day budget; probe also returns the daily limit. A non-entered user sees a friendly "not joined" state before an attempt is burned.
- **training-sanity reference points** — pretrained run ≈ 0.53 val mAP50 @ epoch 2, ~0.71 @ 10, 0.571 on the hidden test; from-scratch ≈ 0.004 @ 10 was normal convergence (historical).

## The four tabs & UI language

- **the four tabs** — Import · Train · Predict + Submit · Status, under the sidebar entry "Kaggle" (AI Tools), joined by the 4-step stepper (pipeline indicator; checkmarks share the tabs' backend truth).
- **six-state machine** — every tab: 1 Empty · 2 Preflight/gate · 3 In progress · 4 Success · 5 Failure · 6 Revisit; tab-open resolution: running job → verified snapshot → form.
- **Import specifics** — YAML preflight → single staged job → 9/9 cross-split checks incl. the GT-leak guard ("test table carries no ground-truth boxes"); canonical rows 5,910 / 733 / 715.
- **Train specifics** — gate (read-only table existence checks) → in-run (header + batch-determinate bar + metrics strip/sparklines) → terminal (banner + provenance panel); locked-contract banner with read-only rows.
- **Predict + Submit specifics** — two-step gated flow: step 1 Run inference (free, repeatable; results panel is the decision surface) unlocks step 2 Submit to Kaggle (costly; names its basis; confirm states "spends 1 of your 3 daily submissions").
- **Status specifics** — hero strip (best score · latest activity · budget · Live now) + history table; polls 15s while visible; friendly degradation for known Kaggle API failures.
- **revisit-first** — a tab with a verified snapshot opens straight into its success view, form hidden behind "Start over"/"Start new run".
- **the playbook** — docs/ui-notes.md; "apply the playbook" means those decisions are settled, not re-litigated.
- **?kgdev fixtures** — `?kgdev=<state>` renders any state from static fixtures: no fetches, job-firing buttons disabled ("demo state"), deterministic curves, and ALWAYS the participant view (host affordances stay hidden).
- **motion tokens** — `--kgl-motion-fast/base/slow`, `--kgl-stagger`, the two eases; four rules: motion is information · no exit animations · no replay on revisit · reduced-motion parity.
- **glance card** — the "Dataset at a glance" right-column card after a green Import gate (stats chips + class tags + relocated guard note).
- **verdict line** — the muted headline above check columns: "9/9 checks passed" / "7/9 checks passed — 2 failed".
- **outcome vocabulary** — history rows speak participant language, not job states: "Submitted · #ref", "CSV generated (not submitted / daily limit reached / not joined)", "Validation failed"; Δ measured against the previous scored row.
- **REUSED vs CREATED** — per-split import outcome: an identical existing table is reused; otherwise a table/revision is created (fixture state4 shows val CREATED + train/test REUSED).
- **Use latest revision / `.latest()`** — Train checkbox: resolve each table URL to its newest lineage revision at job start; unchecking (or picking an older revision in the revision picker) trains those exact revisions, and the gate's green line echoes which.
- **the session object** — one canonical store (`session` key in ui_config.json; `kgSession` client-side) for project name, table name, dataset yaml, device, `slug_override` (null = track the shipped slug), and explicit table-URL `overrides`; tabs render projections and no tab owns a default (backend defaults live only in `constants.py`, the UI gets them via GET /config). Replaced the per-tab copies + `kgSyncFieldToProject` follow machinery (v1.2.1's project follow) in v1.2.6 — stores that cannot disagree need no self-healer. Playbook: ui-notes §14.
- **session_v1 migration** — one-shot fold of the legacy per-tab copies into the session; the `_migrations.session_v1` marker records the deciding branch (`import_state` iff the snapshot's table URLs resolve on disk — the artifact's URL segments win over its string fields — else `import_form_urls_unresolved` / `import_form_no_snapshot` / `default` / `fresh`). Ordered strictly after `device_blank_default`. Cross-project URL copies are dropped; same-project revision choices survive as overrides.
- **ETA recompute rule** — "remaining" is recomputed client-side on every poll: `max(0, per-epoch pace × total epochs − elapsed)`. The pace seeds from the history median (the pre-run hint's number) until the first epoch boundary lands the trainer's measured `avg_epoch_s` (whole-run average, refreshed at every epoch end); a 1-epoch run has no boundary, so the seed carries the whole run. Past the estimate it renders "finishing up…", never an impossible number (the frozen-ETA finding from both round-2 testers; fixed in v1.2.3). The pre-run duration hint is separate: median `avg_epoch_s` of the 5 most recent finished train jobs on this machine.
- **config persistence rule** — the Import form settles (debounced input + blur) INTO the session; a settled project/table change clears the URL overrides, re-derives the follower fields (nothing persisted — derived values are never stored), and re-runs their gates. Run-start still snapshots its own tab's tab-local fields. Config writers are user-action-initiated only; the sole read-path write is the marker-guarded migration in config_store.load() (ui-notes §14 is the enforcement rule). Coherence now holds by construction (`test_config_coherence_invariant` codifies exit_gate_125 C1); the store 400s any write carrying retired keys, so a stale cached fragment fails visibly — hard-refresh is the remedy. Since v1.2.6 (superseding the v1.2.5 settle-save + follow).
- **connection guard** — `kgConn`: owns network-level failures in every finished tab (one banner slot each), backoff pings, resumes polls/gates on reconnect — never auto-restarts imports/trains/submits.
- **diagnostics block** — the fenced ` ```3lc-kaggle-diagnostics ` block from any Copy-diagnostics button: version/OS/time header + per-tab sections (inputs, checks, log tail); the expected shape of tester bug reports.

## Ops & environments

- **two environments** — `3lc-hub/` = frozen v1.1.x world (3lc-compute 0.1.1.47 + 3lc 2.22.3, real home, :5015/:5020, plugin loaded LIVE from the checkout on `develop`); `3lc-hub-next/` = 0.2.x (0.2.1 + 3lc 3.1.0, REDIRECTED home under `3lc-hub-next/home/`, :5021 or frontend-swap to :5020, installs from git tags).
- **catalog / gist / source spec** — `catalog.json` lists installable versions; each `source` is a PEP-508 git reference pinned to a tag; the repo copy is truth, the public gist is the live mirror URL hubs consume (private-repo raw URLs 404).
- **catalog version history** — the `versions` array keeps one entry per released version, newest first; when the gist advertises a version newer than the installed one, the installed card grows an **Update** button. Mirror mechanics + pitfalls: CLAUDE.md §B Releasing.
- **Mac-local (Apple silicon)** — VALIDATED 2026-08-10, round-2 pairing test: blank Device auto-resolves to `mps`; measured ~4 min/epoch training and ~9 s for the full 715-image predict, pinned-checkpoint sha verified; zero service env vars needed (see TESTER_SETUP_0.2 macOS appendix).
- **worker venv / managed-plugins** — the shop materializes the plugin's venv at `~/.3lc-compute/managed-plugins/kaggle-exdark/<version>/.venv`; the plugin runs out-of-process (`tlc_plugin_sdk.worker`), host reverse-proxies `/api/plugins/kaggle-exdark/*`; reload = kill worker, respawn on next request.
- **W-series** (Windows/platform bugs, ledgered for the Hub team — W4 was never assigned):
  W1 = 0.2.1 spawns workers as POSIX `<venv>/bin/python` on every OS; per-plugin env-var override (`TLC_COMPUTE_PLUGIN_VENV_<ID>`) is the workaround.
  W2 = venvs based on a uv-managed Python export `PYTHONHOME` and cross-wire worker stdlibs; build host + plugin venvs from the system Python.
  W3 = shop uninstall never stops the worker; the orphan's file lock breaks same-version reinstall until it dies.
  W5 = harmless `ConfigIndexingTable` / `object_type 'configfile'` traceback at Object Service startup on the 0.2.1+3.1.0 pairing; not a finding.
- **the ledger** — platform/shop bugs owed to the Hub team (Gudbrand): `../3lc-hub-next/PORT_PLAN.md` §6 "Ledger items" + addendum.
- **UV_TORCH_BACKEND=auto** — set in the compute-service env; the shop's `uv pip install` inherits it and uv picks the CUDA wheel index matching the driver; no-op on non-NVIDIA hosts (Macs); superseded the cu128 `TLC_COMPUTE_PLUGIN_INDEX_URLS` pin.
- **resolve_device cascade** — a blank Device field resolves worker-side to CUDA → MPS → CPU (`predictor.resolve_device`); needed because ultralytics never auto-selects MPS and an explicit `0` raises without CUDA; host-side validation stays torch-free.
- **KGAT** — the Kaggle access-token auth the plugin uses (README §2); Submit/Status need it, Import/Train don't.

## Naming

- **run names** — `kaggle_run_<YYYYMMDD_HHMMSS>` when the field is blank; sanity-control runs live apart (project `control-sanity`, run `control_pretrained_DO_NOT_SUBMIT` — never submit non-plugin outputs).
- **project name** — default 3LC project `exdark-competition`; tables `exdark_train` / `exdark_val` / `exdark_test`.
- **tags** — `vX.Y.Z`; the version string is identical in pyproject.toml, plugin.toml, and the catalog entry; never retag. Current release: **v1.2.5** (tagged 2026-08-12; config persistence on settle + coherent-project follow — the round-2 tester-handoff version, replacing v1.2.4).
- **plugin id** — `kaggle-exdark` (since v1.2.1; collision safety). The legacy id `kaggle` is retired and reserved for the future generic multi-competition fork; the W1 env-var name derives as `TLC_COMPUTE_PLUGIN_VENV_` + id upper-cased with `-` → `_`.
