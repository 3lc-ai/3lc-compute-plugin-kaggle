# 3lc-compute-plugin-kaggle

A 3LC Hub compute plugin for **The 3LC Low-Light Detection Challenge (ExDark)**.
One sidebar page walks a participant through the whole competition loop:

> **1 Import → 2 Train → 3 Predict + Submit → 4 Status**

*(screenshot placeholder — Hub page with the four cards)*

Demo screenshot list (all reachable via `?kgdev` fixtures, identical on
every load):

1. Header + stepper — chip "YOLOv11n · COCO-pretrained · 640px"
2. Train contract panel (Model / Init `yolo11n.pt · sha256 0ebbc80d4a76…` /
   Image size) — `?kgdev=train-state2`
3. **Provenance panel with the checkpoint-hash assertion** (the
   centerpiece) — `?kgdev=train-state4`
4. Predict results panel + hero — `?kgdev=submit-results`
5. Participant view, single Plugin-run source — `?kgdev=submit-participant`
6. Legacy run truthfully tagged — `?kgdev=predict-legacy-run`
7. Status hero strip + history — `?kgdev=status-history`

The point of the competition is the **data loop**: edit labels in the 3LC
Dashboard, re-train on the newest revision (`.latest()`), and climb the
leaderboard with better data — the model is fixed.

## The four cards

1. **Import** — point at the starter kit's `dataset.yaml`. Creates
   `exdark_train` / `exdark_val` / `exdark_test` tables and validates them
   against the competition dataset (5,910 / 733 / 715 rows, canonical
   12 classes). The test split imports **images-only by construction** —
   hidden ground truth can never enter the table. Re-import reuses existing
   tables (reported, never duplicated) and re-validates.
2. **Train** — constrained training via 3lc-ultralytics. **Locked
   server-side: `yolo11n.pt` (the official COCO-pretrained checkpoint,
   plugin-managed and sha256-pinned) · imgsz 640 · pretrained locked True.**
   Identical starting weights for every participant; the locks hold against
   the extra-args escape hatch, and the produced 3LC Run's recorded
   parameters (including the checkpoint hash) prove the provenance.
   Everything else (epochs, batch, lr, optimizer, full 3LC
   metrics-collection settings) is yours.
3. **Predict + Submit** — inference on the test table → `submission.csv`
   (`id,image_id,prediction_string`, image_id = filename stem) → strict
   pre-flight validation implementing the competition metric's exact parsing
   rules (so a format error never burns a Kaggle submission) → optional
   upload via the Kaggle API. Works without credentials in CSV-only mode.
   Predictions are **plugin-run-only** for participants (enforced
   server-side); the direct Weights-file source is host-only, gated by the
   same check as local scoring.
4. **Status** — local submission history (runs, CSVs, scores) plus live
   Kaggle state (recent submissions, best public score, leaderboard) once
   `~/.kaggle/kaggle.json` and the competition slug are configured.

## Install (installed Hub, tlc_compute 0.1.x)

The installed host discovers plugins by importing subdirectories of a
registered "plugin root" — full operator's guide in
[docs/deployment-guide.md](docs/deployment-guide.md). Short version:

1. Dependencies live in the compute-service venv (in-process host):
   `uv pip install kaggle` — everything else (torch, 3lc, 3lc-ultralytics)
   ships with the Hub install.
2. Register this repo's `src/` as a plugin root in
   `%USERPROFILE%\.3lc-compute\settings.json` (write it WITHOUT a UTF-8 BOM):

   ```json
   { "plugin_dirs": ["C:\\path\\to\\3lc-compute-plugin-kaggle\\src"] }
   ```

3. Restart the compute service. The sidebar shows **Kaggle Competition**
   under AI TOOLS.

Iterate with the hot-reload endpoint (code + UI changes; route changes need a
service restart):

```
curl -X POST -H "Authorization: Bearer <JWT>" http://localhost:5020/api/admin/plugins/kaggle/reload
```

Kaggle credentials are read from `~/.kaggle/kaggle.json` only — the plugin
never stores them.

## Repo layout

```
src/tlc_plugin_kaggle/   the plugin (manifest = class attrs on KagglePlugin)
├── __init__.py          plugin class + registration
├── ui.html              the four-card page
├── routes.py            REST endpoints under /api/plugins/kaggle
├── importer.py          card 1: import + dataset validation (GT-leak guard)
├── trainer.py           card 2: locked pinned-init training + provenance
├── predictor.py         card 3+4: inference, submission.csv, Kaggle API
└── jobs.py              disk-persisted job store (survives hot reload)
docs/                    design notes + deployment guide (research phase)
scripts/                 one-off maintenance (job-record migration)
pyproject.toml           dist metadata + [tool.tlc-compute] for the future
                         catalog host (hand-synced with the class attrs)
```
