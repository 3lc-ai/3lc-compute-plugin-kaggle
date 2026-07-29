# Smoke test: the 15-minute path

Prereqs: README sections 1 to 3 done (services up, plugin in sidebar, Kaggle token
saved, starter kit unzipped). Work top to bottom; every step has an expected result.
Check it off only if the expectation holds **exactly**; otherwise note what you saw
and keep going. Report the filled checklist plus any **Copy diagnostics** output.

Tester: ______________  Date: ______________  GPU: ______________
Plugin version shown in the page footer: ______________ (expect **v1.1.1**)

## 0. Page loads

- [ ] Sidebar shows **Kaggle** under AI TOOLS; the page opens with four tabs
      (Import / Train / Predict + Submit / Status) and a stepper.
- [ ] Footer reads `3LC Kaggle Competition plugin v1.1.1`.

## 1. Import (2 to 5 minutes)

- [ ] Paste the full path to the kit's `dataset.yaml` → preflight panel goes
      **green** (12 classes; 5,910 / 733 / 715 rows found on disk).
- [ ] Click **Import & Validate** → progress runs through
      train → val → test → validate.
- [ ] Result: `exdark_train` (5,910), `exdark_val` (733), and `exdark_test` (715)
      created.
- [ ] **Checks: 9/9 green**, including "test table carries no ground-truth boxes".
- [ ] Stepper marks step 1 complete. Leave and revisit the tab: the success
      snapshot re-renders (no re-import).

## 2. Train: 2 epochs (5 to 8 minutes on GPU)

- [ ] Contract panel shows locked **Model yolo11n.pt · Init sha256 `0ebbc80d4a76…`
      · Image size 640**, not editable anywhere.
- [ ] Set **Epochs = 2** (all else default) → **Start Training**.
- [ ] First-ever run: a "Fetching official checkpoint (5.4 MB)" stage appears once.
- [ ] Live metrics tick per epoch. **Val mAP50 at epoch 2 ≈ 0.5** (reference run
      0.533; anywhere in the 0.45 to 0.60 band is a pass; below 0.2 is a failure,
      report it).
- [ ] On completion: **"Verified provenance recorded" panel, 4/4 assertions green**,
      including the checkpoint sha256.
- [ ] The run appears in the 3LC Dashboard project (`exdark-competition`).

## 3. Predict (1 to 2 minutes)

- [ ] Predict + Submit tab, Step 1: weights source lists **your plugin run** (a
      revision/run picker; the free weights-path field is organizer-only).
- [ ] Test table URL is prefilled with `exdark_test`. Click **Run inference**.
- [ ] Result panel: **all format checks green**, `submission.csv` path shown,
      sanity summary renders (total boxes / empty images / boxes-per-image mean).
      A soft "boxes unusually low" warning is not a check failure; note it if
      it appears.
- [ ] **No local mAP score is shown**; that's expected off the organizer machine.

## 4. CSV download (do NOT submit)

- [ ] Click **Download CSV** → file downloads.
- [ ] Open it: header `id,image_id,prediction_string` + **715 data rows**; ids
      0 to 714; prediction strings are 6-value groups or `no box`.
- [ ] **STOP HERE.** Do not click **Submit to Kaggle** (submissions are budgeted;
      Step 2 stays disabled/"not joined" if you're not invited, and that's a pass).

## 5. Status

- [ ] Hero strip reflects your run and CSV (best/latest, freshness line).
- [ ] History table lists the prediction with a working **Download CSV** action.
- [ ] Kaggle connection card: your username when the token is valid; a friendly
      "not connected" hint (not an error dump) when it isn't. A missing
      "used today" counter is a known private-competition limitation; count it
      as a pass.

## 6. Failure & fixture spot-checks (about 3 minutes)

- [ ] Import with `C:\nope\dataset.yaml` → readable error with **Copy diagnostics**
      button; no spinner hang, no stack trace in the UI.
- [ ] Append `?kgdev=train-state4` to the page URL → provenance fixture renders,
      action buttons are **disabled** with a "demo state · actions disabled" note.
- [ ] Remove `?kgdev` → your real state returns intact.
- [ ] ~680 px viewport: no horizontal scroll. `prefers-reduced-motion: reduce`:
      page fully usable, no animation.

## Report

Paste: this checklist, the footer version string, any **Copy diagnostics** blocks,
and your rough timings per section.
