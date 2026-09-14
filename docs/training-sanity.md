# Training sanity — what a healthy run looks like

The competition locks YOLOv11n from the plugin-managed, sha256-pinned
COCO-pretrained checkpoint at `imgsz=640`. Every participant starts from
byte-identical weights, and the Run's recorded checkpoint hash is the proof.

This page is the answer sheet for "is training broken?".

## The reference trajectory

A plain plugin run on the untouched tables — 10 epochs, batch 16, imgsz 640,
seed 0:

| epoch | val mAP50 |
|------:|----------:|
| 1 | 0.143 |
| 2 | 0.533 |
| 3 | 0.629 |
| 4 | 0.651 |
| 5 | 0.665 |
| 6 | 0.674 |
| 7 | 0.688 |
| 8 | 0.693 |
| 9 | 0.703 |
| 10 | **0.706** |

At epoch 10: P 0.754, R 0.621, mAP50-95 0.455. The curve flattens after that —
the productive range is 10 to 50 epochs, and the Train tab defaults to 20.
Per-class mAP50 spans 0.55 (Table) to 0.84 (Bus), with **no class at zero**.

So the 2-epoch smoke run in SMOKE_TEST should land near **0.5 val mAP50**.
Materially below that band is worth investigating. Slower wall-clock on a
smaller GPU is not: only a *failure* is a finding.

## Val and the leaderboard read differently

The same 10-epoch run scores **0.571 mAP@0.5 on the full test set** (run
`kaggle_run_20260722_150451`, Kaggle ref 54911899). The hidden test split is
harder than val, so a val number never transfers directly — expect the
leaderboard score to sit below the val score, and don't treat the gap as a bug.

For scale, a COCO-pretrained yolo11x scores 0.640 on this test set with no
ExDark training at all, so the organizer reference sits above a plain run's
starting line. Movement past that band is expected to come from data work —
the point of the competition — rather than from more epochs.

## Is the pipeline healthy?

Three checks, none of which depend on the training contract. Run them before
concluding that training is broken.

### 1. Label flow — GT boxes in the trainer's own plots

Open `train_batch0/1/2.jpg` and `val_batch*_labels.jpg` in the run dir. Boxes
should sit tightly on the objects, and the rendered names should match the
objects they cover ("Car", "People", "Dog", "Bottle"…). Off-image, shifted, or
swapped boxes there mean the label path is wrong.

`val_batch*_pred.jpg` is a different signal: empty prediction plots mean the
model has no confident detections *yet*, which is an under-trained model, not
bad labels. Bad labels still render misplaced boxes in the `_labels` images.

### 2. Learning curve — losses fall, recall rises

Plot the run's `results.csv`. `box_loss`, `cls_loss` and `dfl_loss` should
decline essentially every epoch while val recall climbs. A data-path bug
(wrong boxes, wrong xywh convention, wrong normalization, wrong class mapping)
produces **flat or diverging** losses instead — the model cannot fit noise that
contradicts the images.

Precision is not the early signal: an uncertain model emits many low-confidence
boxes, so precision lags while recall moves first.

### 3. Class map — table indices match dataset.yaml

The canonical value map is `0=Bicycle, 1=Boat, 2=Bottle, 3=Bus, 4=Car, 5=Cat,
6=Chair, 7=Cup, 8=Dog, 9=Motorbike, 10=People, 11=Table`, identical to
`starter_kit/dataset.yaml`. Verified against the imported tables by sampling 20
rows covering all 12 classes and cross-checking class index plus all four xywh
coordinates against the raw YOLO label files (tolerance 2e-3): 20/20 matched,
no off-by-one.

Per-class results are the independent check on this. An off-by-one in the label
map craters specific classes rather than scaling all of them down, so a healthy
run with no class at zero is evidence the mapping is intact.

## Reproducing these checks

1. Open `runs\kaggle-plugin\<run>\train_batch0.jpg` and `val_batch0_labels.jpg`
   — boxes should sit on objects with sensible names.
2. Plot `results.csv` — losses should fall monotonically, recall should rise.
3. Compare the run's per-class mAP50 against the spread above; no class should
   read zero.

Submissions must come from plugin-trained runs with recorded provenance. A run
trained outside the plugin has no recorded checkpoint hash and cannot be
submitted, whatever it scores.
