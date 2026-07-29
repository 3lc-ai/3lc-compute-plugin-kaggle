# Training sanity: why a 10-epoch from-scratch run scores ~0.004 mAP50

> **ADDENDUM 2026-07-22 — the competition contract changed the same day.**
> The from-scratch rule described below is **retired**. The locked contract
> is now **YOLOv11n from the official COCO-pretrained checkpoint
> (plugin-managed, sha256-pinned `0ebbc80d4a76…`) at 640px** — every
> participant starts from byte-identical weights, and the Run's recorded
> checkpoint hash is the proof. Rationale: a ~0.005 epoch-10 start
> demoralizes participants; a ~0.70 start with room to climb keeps the
> competition approachable, and fairness is preserved because the init is
> pinned for everyone. Predictions are also plugin-run-only for
> participants now (the free weights-path field is host-only), closing the
> train-elsewhere-submit-as-yolo11n loophole.
>
> **Recalibrated expectations:** the control run below is no longer the
> counterfactual — it *is* the reference trajectory. A plain
> pretrained run on the untouched tables reaches ~0.53 val mAP50 by epoch
> 2 and **~0.71 by epoch 10** (P 0.75, R 0.62), flattening after; the
> productive range is 10 to 50 epochs and the Train tab defaults to 20.
> **Val and leaderboard read differently:** the same 10-epoch run scores
> **0.571 mAP@0.5 on the full test set** (live-verified 2026-07-22, run
> `kaggle_run_20260722_150451`, Kaggle ref 54911899) — the hidden test
> split is harder than val. The organizer yolo11x reference submission
> (0.640 test) therefore still sits *above* the plain-run starting line
> on the leaderboard. Movement beyond that band is expected to come from
> data work (the point of the competition), not more epochs. The
> near-zero expectation notes this document proposed for the Train tab
> were removed with the contract change; the from-scratch evidence below
> stands as the historical record and still answers "is the pipeline
> healthy?" — it is.

**Verdict: the data pipeline is healthy. Near-zero mAP at epoch 10 is normal
from-scratch convergence, not a bug.** Verified 2026-07-22 against run
`kaggle_run_20260722_130606` (val mAP50 0.0045, P 0.003, R 0.225 after 10
epochs). If a participant posts "my mAP is 0.004, is the plugin broken?" —
this page is the answer sheet.

The competition locks `model=yolo11n.yaml` (random init), `pretrained=False`,
`imgsz=640`. A randomly-initialized detector spends its first epochs learning
what edges and objects *are*; COCO-pretrained weights already know. Published
comparisons show pretrained YOLO reaching high mAP within ~30 epochs while
from-scratch runs converge slowly, typically between epoch 200 and 300
([Ultralytics fine-tuning guide](https://docs.ultralytics.com/guides/finetuning-guide),
[Self-Supervised YOLO, arXiv:2508.01966](https://arxiv.org/html/2508.01966v1)).
Ultralytics' own official COCO checkpoints are trained from scratch for ~500
epochs. Ten epochs is ~2–5% of a from-scratch schedule.

## Evidence

### 1. Label flow — GT boxes are correct in the trainer's own plots

`train_batch0/1/2.jpg` and `val_batch*_labels.jpg` in the run dir
(`runs\kaggle-plugin\kaggle_run_20260722_130606\`) were inspected. Boxes sit
tightly on the objects, and indices/names match the canonical map everywhere:
bicycles=0, boats=1, bottles=2, buses=3, cars=4, cats=5, chairs=6, cups=7,
dogs=8, motorbikes=9, people=10, tables=11; val plots render the names
("Car", "People", "Dog", "Bottle"…) on the right objects. No off-image,
shifted, or swapped boxes. `val_batch*_pred.jpg` at epoch 10 is empty — the
model has no confident detections yet, which is the *symptom of an
under-trained model*, not of bad labels (bad labels would still show GT boxes
misplaced in the `_labels` images).

### 2. Learning curve — losses fall monotonically, recall rises

From the run's `results.csv`:

| epoch | box_loss | cls_loss | dfl_loss | val recall | val mAP50 |
|------:|---------:|---------:|---------:|-----------:|----------:|
| 1 | 3.376 | 5.219 | 4.266 | 0.104 | 0.0006 |
| 2 | 3.373 | 5.164 | 4.236 | 0.121 | 0.0007 |
| 3 | 3.359 | 5.098 | 4.193 | 0.128 | 0.0010 |
| 4 | 3.329 | 5.000 | 4.123 | 0.138 | 0.0012 |
| 5 | 3.283 | 4.913 | 4.037 | 0.148 | 0.0017 |
| 6 | 3.214 | 4.846 | 3.959 | 0.181 | 0.0040 |
| 7 | 3.172 | 4.804 | 3.888 | 0.191 | 0.0027 |
| 8 | 3.142 | 4.760 | 3.836 | 0.202 | 0.0032 |
| 9 | 3.105 | 4.758 | 3.803 | 0.215 | 0.0042 |
| 10 | 3.095 | 4.733 | 3.774 | 0.225 | 0.0045 |

Every loss declines every epoch; recall more than doubles. A data-path bug
(wrong boxes, wrong classes, wrong normalization) produces *flat or diverging*
losses — the model can't fit noise that contradicts the images. This model is
learning normally; it's just at the very start of the curve. (Precision stays
~0.003 because an uncertain model emits many low-confidence boxes; recall is
the informative early signal.)

### 3. Class map — table indices match dataset.yaml exactly

The run consumed
`projects/exdark-competition/datasets/exdark_train/tables/initial` (5,910
rows) and `exdark_val/tables/initial` (733 rows). The table's value map was
compared to `starter_kit/dataset.yaml`, and 20 sampled rows covering **all 12
classes** were cross-checked against the raw YOLO label files (class index +
all four xywh coords, tolerance 2e-3):

- Value map order: `0=Bicycle, 1=Boat, 2=Bottle, 3=Bus, 4=Car, 5=Cat,
  6=Chair, 7=Cup, 8=Dog, 9=Motorbike, 10=People, 11=Table` — identical to
  dataset.yaml. No off-by-one.
- 20/20 sampled rows match their on-disk YOLO labels exactly.

### 4. Control experiment — same tables, pretrained weights (decisive)

`control_pretrained_sanity.py` (competition workspace root, not this repo; run name
`control_pretrained_DO_NOT_SUBMIT`, 3LC project `control-sanity`) trained
**COCO-pretrained** `yolo11n.pt` through the *identical* tlc-ultralytics
path on the *identical* tables — same epochs (10), batch (16), imgsz (640),
seed (0). The only changed variable is weight initialization:

| epoch | val mAP50 (pretrained control) | val mAP50 (from-scratch run) |
|------:|-------------------------------:|-----------------------------:|
| 1 | 0.143 | 0.0006 |
| 2 | 0.533 | 0.0007 |
| 3 | 0.629 | 0.0010 |
| 4 | 0.651 | 0.0012 |
| 5 | 0.665 | 0.0017 |
| 6 | 0.674 | 0.0040 |
| 7 | 0.688 | 0.0027 |
| 8 | 0.693 | 0.0032 |
| 9 | 0.703 | 0.0042 |
| 10 | **0.706** | **0.0045** |

(Control also: P 0.754, R 0.621, mAP50-95 0.455 at epoch 10.) Per-class
control mAP50 spans 0.55 (Table) to 0.84 (Bus) with **no class at zero** —
independent confirmation that no class index is misrouted; an off-by-one in
the label map would crater specific classes, not scale all of them.

If the data pipeline were broken (normalization, xywh convention, class
mapping), pretrained weights could not fix it — the control would also score
near zero. Instead it cleared healthy mAP50 within 2 epochs. The pipeline is
proven end-to-end; the from-scratch number is pure convergence physics.

## What from-scratch trajectories look like from here

Calibration points:

- **The competition workspace's 20-epoch from-scratch baselines** (YOLOv8n,
  `train_baselines.py`, workspace root — not in this repo) on five other datasets landed anywhere from mAP50
  0.04 to 0.93 at epoch 20 depending on dataset difficulty — early
  from-scratch numbers are dominated by dataset hardness, and ExDark
  (low-light, 5.9k train images, 12 classes) is on the hard end.
- Published from-scratch runs typically converge around epochs 200–300;
  pretrained runs converge in roughly half the epochs
  ([arXiv:2508.01966](https://arxiv.org/html/2508.01966v1)).
- The observed curve is pre-liftoff: mAP50 roughly doubled over epochs 5→10
  while recall climbed steadily. Liftoff (mAP50 > 0.05) typically follows
  once precision starts moving — expect it in the ~15–30 epoch range on this
  dataset, with rapid gains after.

Expectation for the competition's productive range (**50–150 epochs**, as the
Tips page says): a plain from-scratch yolo11n run should land somewhere in
the **~0.2–0.45 mAP50** band, with data-curation work (the point of the
competition) pushing beyond that. For reference, a COCO-pretrained yolo11x
scores 0.640 mAP50 on this test set with no ExDark training at all — that
ceiling is why `pretrained=False` was locked under the retired rule: it kept
the leaderboard about the data work, not checkpoint shopping. (The current
contract achieves the same fairness by pinning one checkpoint for everyone.)

So: **10 epochs ≈ 0.004 is on-curve.** 50–150 epochs lands a respectable
score; nobody should calibrate prize expectations (or file bug reports) on a
sub-20-epoch run.

## UI consequence (historical — removed with the contract change)

The Train tab briefly set this expectation in two places (added 2026-07-22,
removed the same day when the pinned-pretrained contract landed):

- A static line under **Epochs**: from-scratch runs score near-zero mAP50
  for the first ~10–20 epochs by design.
- An in-run note under the metric strip, shown while the live mAP50 is
  < 0.05 in the first 30 epochs, that disappears once the score lifts off.

## Reproducing this check

1. Open `runs\kaggle-plugin\<run>\train_batch0.jpg` and
   `val_batch0_labels.jpg` — boxes should sit on objects with sensible names.
2. Plot `results.csv` — losses should fall monotonically, recall rise.
3. Run `control_pretrained_sanity.py` (competition workspace root) for the
   pretrained control. (Under
   the 2026-07-22 contract this is simply what a plugin run does — but
   still never submit its outputs directly: submissions must come from
   plugin-trained runs with recorded provenance.)
