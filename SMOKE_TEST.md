# Smoke test — the 15-minute path

Prereqs: README §1–§3 done (services up, plugin in sidebar, Kaggle token saved,
starter kit unzipped). Work top to bottom; every step has an expected result —
check it off only if the expectation holds **exactly**, otherwise note what you saw
and keep going. Report the filled checklist plus any **Copy diagnostics** output.

Tester: ______________  Date: ______________  GPU: ______________
Plugin version shown in the page footer: ______________ (expect **v1.2.8**)

> Updating from an earlier version? **Hard-refresh the plugin page**
> (Ctrl+Shift+R) after the update — required, not optional. A stale cached
> page saves settings in a retired format and every save silently fails
> (nothing on the page signals it) until you refresh.

> Round-1 testers: the plugin id changed to `kaggle-exdark` in v1.2.1 —
> follow the migration note at the top of
> [docs/TESTER_SETUP_0.2.md](docs/TESTER_SETUP_0.2.md) before anything below.

## 0. Page loads

- [ ] Sidebar shows **Kaggle** under AI TOOLS; the page opens with four tabs
      (Import / Train / Predict + Submit / Status) and a stepper.
- [ ] Footer reads `3LC Kaggle Competition plugin v1.2.8`.

## 1. Import (~2–5 min)

- [ ] Paste the full path to the kit's `dataset.yaml` → preflight panel goes
      **green** (12 classes; 5,910 / 733 / 715 rows found on disk).
- [ ] Set **Project name** to `smoke-` + your initials (e.g. `smoke-ab`).
      Deliberately NOT the default: a later step checks that everything lands
      in this project, which a default name would pass by accident.
- [ ] Click **Import & Validate** → progress runs through
      train → val → test → validate.
- [ ] Result: three tables created — `exdark_train` (5,910), `exdark_val` (733),
      `exdark_test` (715).
- [ ] **Checks: 9/9 green**, including "test table carries no ground-truth boxes".
- [ ] Stepper marks step 1 complete. Leave and revisit the tab: the success
      snapshot re-renders (no re-import).

## 2. Train — 2 epochs (~5–8 min on GPU)

- [ ] Contract panel shows locked **Model yolo11n.pt · Init sha256 `0ebbc80d4a76…`
      · Image size 640** — not editable anywhere.
- [ ] Under **3LC settings**, the read-only **Session** project row shows the
      project from step 1 (your `smoke-…` name). There is no editable Project
      field on this tab; the run goes where the tables are, by construction.
- [ ] Set **Epochs = 2** (all else default) → **Start Training**.
- [ ] First-ever run: a "Fetching official checkpoint (5.4 MB)" stage appears once.
      A first-ever start that errors instead of starting is a **finding** in
      v1.2.1 (the round-1 "signal is aborted" cold-start bug is fixed — report
      the exact message if you see one).
      *Also expected on the very first train:* ultralytics' AMP check downloads
      `yolo26n.pt` (~5 MB) once — its own sanity check, **not** part of the
      contract (the pinned init stays `yolo11n.pt`). Needs internet; on a
      firewalled network see README troubleshooting #11.
- [ ] Live metrics tick per epoch. **Val mAP50 at epoch 2 ≈ 0.5** (reference run:
      0.533; anywhere 0.45–0.60 is a pass — below 0.2 is a failure, report it).
      8 GB GPUs run a smaller effective batch and take longer — slow ≠ fail.
- [ ] **Epoch counter tops out at 2/2** and the finished run reads "2 epochs"
      everywhere (run selector included). A "final validation" line in the log
      after epoch 2 is expected and is **not** an epoch 3.
- [ ] On completion: **"Verified provenance recorded" panel, 4/4 assertions green**,
      including the checkpoint sha256.
- [ ] The run and ALL THREE tables are in the **same** 3LC Dashboard project —
      the `smoke-…` project from step 1. Open that project in the Dashboard and
      confirm it lists the run plus `exdark_train` / `exdark_val` /
      `exdark_test`. A run in any other project (including
      `exdark-competition`) is a finding, not a variation.
- [ ] The **Open Run in Dashboard** link opens a dashboard that actually shows
      the run (v1.2.1 appends `object_service=` to every dashboard link; a
      dashboard that opens empty is a finding).

## 3. Predict (~1–2 min)

- [ ] Predict + Submit tab, Step 1: weights source lists **your plugin run** (a
      revision/run picker; no free weights-path field — that's organizer-only).
- [ ] Test table URL is prefilled with `exdark_test`. Click **Run inference**.
- [ ] Inference streams in VRAM-sized chunks: the per-image counter climbs
      smoothly to 715 and there is **no CUDA OOM** — including when Predict
      runs right after Train in the same session (the round-1 12 GB OOM is
      fixed; an OOM here is a finding, include your GPU + VRAM).
- [ ] Result panel: **all format checks green**, `submission.csv` path shown,
      sanity summary renders (total boxes / empty images / boxes-per-image mean).
      A soft "boxes unusually low" warning is not a check failure — note it if
      it appears.
- [ ] **No local mAP score is shown** — by design for everyone except the
      organizer machine. The Kaggle leaderboard score is the real one.

## 4. CSV download — and (round 2) optionally submit

- [ ] Click **Download CSV** → file downloads.
- [ ] Open it: header `id,image_id,prediction_string` + **715 data rows**; ids
      0–714; prediction strings are 6-value groups or `no box`.
- [ ] **Round-2 policy:** testers invited to the competition MAY submit to
      Kaggle to see a score (3/day budget — one is plenty). Expected: the
      submission is accepted, and the score appears on Kaggle/Status —
      remember, no local mAP for non-hosts is correct.
- [ ] **If you have NOT joined the competition on Kaggle** (accepted the rules
      on the competition page): the plugin should show the friendly
      **not-joined** state *before* burning an attempt — that's a pass. A raw
      500/error dump on submit instead of the friendly state is a **finding**
      (this bit a round-1 tester; the pre-submit GetCompetition probe should
      catch it).

## 5. Status

- [ ] Hero strip reflects your run and CSV (best/latest, freshness line).
- [ ] History table lists the prediction with a working **Download CSV** action.
- [ ] Kaggle connection card: your username when the token is valid; a friendly
      "not connected" hint (not an error dump) when it isn't. A missing
      "used today" counter is a known private-competition limitation — pass.

## 6. Failure & fixture spot-checks (~3 min)

- [ ] Import with `C:\nope\dataset.yaml` → readable error with **Copy diagnostics**
      button; no spinner hang, no stack trace in the UI.
- [ ] Append `?kgdev=train-state4` to the page URL → provenance fixture renders,
      action buttons are **disabled** with a "demo state — actions disabled" note.
- [ ] Remove `?kgdev` → your real state returns intact.
- [ ] ~680 px viewport: no horizontal scroll. `prefers-reduced-motion: reduce`:
      page fully usable, no animation.

## Report

Paste: this checklist, the footer version string, any **Copy diagnostics** blocks,
and your rough timings per section.
