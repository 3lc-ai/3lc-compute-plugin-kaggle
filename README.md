# 3LC Kaggle Competition plugin

This is the 3LC Hub plugin for **The 3LC Low-Light Detection Challenge (ExDark)**, a
Kaggle object-detection competition where the model is fixed and the leaderboard is
climbed by improving the *data*. Every participant trains the same YOLOv11n from the
same sha256-pinned COCO-pretrained checkpoint at 640 px, and each training run records
verifiable provenance (including the checkpoint hash), so a submission provably came
from the shared contract: the **verified-contract thesis**. The plugin puts the whole
loop on one Hub sidebar page, four tabs: **1 Import → 2 Train → 3 Predict + Submit →
4 Status**. Between rounds you edit labels in the 3LC Dashboard, retrain on the
newest table revision, submit, and repeat.

<!-- VALIDATE (user): screenshots not yet captured. Capture per demo/SHOT_LIST.md
     (workspace), save into docs/shots/ with these filenames, commit, and delete
     this comment. The provenance panel (?kgdev=train-state4) is the centerpiece. -->
![Verified provenance panel (the centerpiece)](docs/shots/03_provenance_hash.png)
![Train contract panel](docs/shots/02_train_contract.png)
![Predict results](docs/shots/05_predict_results.png)
![Status hero + history](docs/shots/09_status_history.png)

---

## 1. Prerequisites

Target platform: **Windows 11 + NVIDIA GPU** (the reference machine is an RTX 5070 Ti;
CPU-only works but the 15-minute smoke test becomes an hour). You need:

- **Python 3.12** via [uv](https://docs.astral.sh/uv/) (`uv venv` downloads it for you)
- A **3LC account** (sign-up is part of the Hub login flow; API key from
  <https://account.3lc.ai/api-key>)
- A **Kaggle account** (for the auth check and Status tab; you will NOT be submitting)

### 1.1 Create the service venv

Pick a permanent folder for the Hub services (referred to as `<hub>` below):

```powershell
mkdir <hub>; cd <hub>
uv venv --python 3.12
.\.venv\Scripts\activate
```

### 1.2 Install 3LC packages: order is load-bearing

`3lc` is **not on public PyPI** (pulled during the 2026 quarantine); every install
goes through 3LC's private index. Core comes from `releases-public`, compute from
`prereleases-public`. Install **core → compute → CUDA torch, in that order**. If
CUDA torch goes in first, the compute install resolves it back to CPU-only torch and
training silently runs on CPU.

```powershell
# (a) core — 3lc 2.22.3 (2.23.0 is core-only and CANNOT run a Hub)
uv pip install "3lc==2.22.3" datasets `
  --index-strategy unsafe-best-match `
  --index-url https://pypi.3lc.ai/public/repositories/releases-public `
  --extra-index-url https://pypi.org/simple

# (b) compute service + 3lc-ultralytics
uv pip install `
  --index-strategy unsafe-best-match `
  --index-url https://pypi.3lc.ai/public/repositories/prereleases-public `
  --extra-index-url https://pypi.3lc.ai/public/repositories/releases-public `
  --extra-index-url https://pypi.org/simple `
  "3lc-compute[timm,sam3]" 3lc-ultralytics-beta

# (c) CUDA torch LAST. This line is for RTX 50-series (Blackwell, sm_120).
#     Older GPUs: pick your channel at https://pytorch.org/get-started/locally/
uv pip install torch==2.11.0+cu128 torchvision==0.26.0+cu128 torchaudio==2.11.0+cu128 `
  --index-url https://download.pytorch.org/whl/cu128

# (d) this plugin's one extra dependency (in-process host = same venv)
uv pip install kaggle
```

Verify GPU torch survived:

```powershell
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
# expect: 2.11.0+cu128 True   (RTX 50-series: 'sm_120' in torch.cuda.get_arch_list())
```

Reference versions (the machine this release was frozen on): `3lc 2.22.3`,
`3lc_compute 0.1.1.47`, `3lc-ultralytics-beta 0.2.1`, `torch 2.11.0+cu128`,
`ultralytics 8.4.6`, `kaggle 2.2.3`, Python `3.12.13`.

### 1.3 Log in

```powershell
3lc login <your-api-key>    # key from https://account.3lc.ai/api-key
```

A successful login prints "API key verified".

### 1.4 Register this plugin

Clone the repo, then register its `src/` directory (NOT the repo root, NOT the
package dir) as a plugin root. The settings file **must be written without a UTF-8
BOM**: PowerShell 5.1's `Out-File -Encoding utf8` writes one, and the service then
*silently* boots with zero plugins. Use this exact block:

```powershell
git clone https://github.com/3lc-ai/3lc-compute-plugin-kaggle
New-Item -ItemType Directory -Force "$env:USERPROFILE\.3lc-compute" | Out-Null
$json = @'
{
  "plugin_dirs": [
    "C:\\path\\to\\3lc-compute-plugin-kaggle\\src"
  ]
}
'@
[IO.File]::WriteAllText("$env:USERPROFILE\.3lc-compute\settings.json", $json,
  (New-Object System.Text.UTF8Encoding($false)))
```

(Edit the path, and keep the doubled backslashes: JSON needs them.) Then confirm the
**host** can parse it before starting anything:

```powershell
& <hub>\.venv\Scripts\python.exe -c "from tlc_compute.persistent_settings import PersistentSettingsStore; print(PersistentSettingsStore().get_plugin_dirs())"
# expect: ['C:\\path\\to\\3lc-compute-plugin-kaggle\\src']
```

### 1.5 Start the two services

Two terminals, both with the venv activated, both left open:

```powershell
# Terminal 1 — Object Service (:5015)
cd <hub>; .\.venv\Scripts\activate
3lc service

# Terminal 2 — Compute Service (:5020) — must start AFTER the plugin is registered
cd <hub>; .\.venv\Scripts\activate
3lc-compute
```

Terminal 2's log must contain `Plugin kaggle runtime initialized`. Quick health check:

```powershell
Invoke-WebRequest http://localhost:5020/health -UseBasicParsing
# expect 200: {"status":"ok","service":"3lc-compute", ...}
```

Open the Hub at **http://localhost:5015**, log in with your 3LC account, and find
**Kaggle** in the sidebar under **AI TOOLS**.
<!-- VALIDATE (user): fresh-account first-login flow at localhost:5015; verified only
     with an already-logged-in account on this machine. -->

---

## 2. Kaggle auth (KGAT token)

The plugin never stores credentials; the `kaggle` client reads them itself. Create a
token on kaggle.com (**Settings → API → Create New Token**; new tokens look like
`KGAT_...`), then save it with **exactly** this (the bash commands kaggle.com shows
will not work on Windows):

```powershell
mkdir "$env:USERPROFILE\.kaggle" -Force
Set-Content -Path "$env:USERPROFILE\.kaggle\access_token" -Value "KGAT_<your token>" -NoNewline -Encoding ascii
```

The file must be byte-exact: plain ASCII, **no BOM, no trailing newline**. The
`-NoNewline -Encoding ascii` flags guarantee that. (Legacy `~/.kaggle/kaggle.json`
and the `KAGGLE_API_TOKEN` env var also work.) Everything except the actual Kaggle
upload works with no credentials at all: you get a CSV either way.

---

## 3. Getting the data

The competition starter kit is **not in this repo** (it is ~616 MB).

<!-- VALIDATE (user): distribution channel for testers; currently the kit exists as
     a local build artifact and on the private Kaggle competition's Data tab. -->
- Ask the organizer (Rishikesh) for `starter_kit.zip`.
- If you received the organizer's build: **615,995,197 bytes**, sha256
  `5bf297eed3dc6d12811c7c7eee1c8cc28ba6db4197f0530bd2322f63adbbdca1`
  (`Get-FileHash starter_kit.zip` to check).
- If you downloaded it from the Kaggle competition page instead, Kaggle re-zips the
  files: expect **616,590,902 bytes** and sha256 `39f2b48c…`. Different hash,
  byte-identical contents. Don't file a bug about the mismatch.

**Unzip it somewhere permanent.** The Hub reads images from that folder forever after
import. Don't move or rename it. Inside: `dataset.yaml`, `sample_submission.csv`,
`images/` (train 5,910 · val 733 · test 715) and `labels/` (train + val only; test
ground truth is hidden). There is nothing to run in the kit: the whole loop happens
in the plugin.

---

## 4. Running the loop (the 15-minute smoke path)

The strict checklist version of this section, with pass/fail boxes, is
[SMOKE_TEST.md](SMOKE_TEST.md). Use that when reporting. Prose version:

1. **Import**: paste the full path of the kit's `dataset.yaml` into the Import tab
   (the field strips the quotes "Copy as path" adds). Preflight goes green; click
   **Import & Validate**. Expected in 2 to 5 minutes: three tables
   (`exdark_train` 5,910 · `exdark_val` 733 · `exdark_test` 715) and **9/9 validation
   checks green**, including "test table carries no ground-truth boxes".
2. **Train**: the contract panel shows the locked trio (yolo11n.pt + sha256, 640 px,
   pretrained). Set **Epochs = 2**, leave the rest at defaults, **Start Training**.
   First run downloads the pinned checkpoint (5.4 MB, one-time). Expected: live
   epoch metrics; **val mAP50 ≈ 0.5 by epoch 2** (reference: 0.533); on completion a
   **Verified provenance recorded** panel with **4/4 assertions**, one of them the
   checkpoint sha256 `0ebbc80d4a76…`.
3. **Predict**: in Step 1 of the Predict + Submit tab, the weights source is your
   plugin run (participants have no other option) and the test table is prefilled.
   Click **Run inference**. Expected in 1 to 2 minutes: results panel, all format
   checks green, `submission.csv` written (path shown). A local mAP score appears
   **only on the organizer machine**. On your machine no score is expected; that's
   by design, not a bug.
4. **Download the CSV**: click **Download CSV** on the results panel and open it:
   715 rows + header, columns `id,image_id,prediction_string`.
   **Do NOT proceed to Step 2 (Submit to Kaggle).** Submissions are budgeted
   (3/day on the private competition) and reserved for the organizer. If you're not
   invited to the private competition you'll see a friendly "not joined" state,
   which is also expected. (The competition slug you'll see contains a real typo,
   `...comepetition-test`; it's in the actual Kaggle URL.)
5. **Status**: the hero strip shows your latest run/CSV; the history table lists the
   prediction with a Download CSV action. With Kaggle connected, the connection card
   shows your username; the used-today counter may be absent (a known API 403 on the
   private competition; it self-heals on the public one).

---

## 5. What to test & how to report

Happy paths (per tab), then the deliberate failure paths:

- [ ] Import, Train (2 epochs), Predict, CSV download, Status: the section-4 path.
- [ ] **One failure path**: point Import at a nonsense yaml path (e.g.
  `C:\nope\dataset.yaml`). Expect a readable error state, not a spinner or a stack
  trace, and a working **Copy diagnostics** button.
- [ ] **Fixture tour**: append `?kgdev=<state>` to the plugin page URL and skim each
  state: Import `state1…state6` (incl. `state2-mismatch`, `state2-error`, `state5`),
  Train `train-state1…train-state6`, `submit-results`, `submit-success`,
  `submit-participant`, `predict-legacy-run`, `status-history`. Fixtures are static
  demo states: action buttons render disabled with a "demo state" note, and nothing
  fetches or fires. Full map in [docs/ui-notes.md](docs/ui-notes.md).
- [ ] **Narrow width**: DevTools responsive mode at ~680 px. Expect no horizontal
  scroll and no clipped panels.
- [ ] **Reduced motion**: emulate `prefers-reduced-motion: reduce`. Everything still
  renders, minus animation.

**Found a bug?** Every tab has a **Copy diagnostics** button (also embedded in error
banners) that copies a fenced block with the plugin version, inputs, checks, and log
tail. Paste that block plus what you expected vs. saw.
<!-- VALIDATE (user): where should testers send reports, Slack channel or email? -->
Send reports to Rishikesh (rishikesh.jadhav@3lc.ai).

---

## 6. Troubleshooting: the five likely failures

1. **Plugin missing from the sidebar; compute log says
   `Could not parse ... starting with empty persistent settings`.**
   Cause: `settings.json` was written with a UTF-8 BOM (PowerShell 5.1
   `Out-File -Encoding utf8` does this). The host rejects it silently.
   Fix: rewrite with the `[IO.File]::WriteAllText` block in §1.4, rerun the parse
   check, restart the compute service.

2. **Kaggle shows "not connected" / auth fails though the token file exists.**
   Cause: the token file isn't byte-exact: a BOM, a trailing newline, or UTF-16
   encoding from a text editor.
   Fix: rewrite with the `Set-Content ... -NoNewline -Encoding ascii` one-liner in
   §2. Don't create the file in Notepad.

3. **Training crawls (many minutes per epoch) or the device field errors.**
   Cause: CPU-only torch. Either CUDA torch was installed before `3lc-compute` and
   got downgraded, or the CUDA channel is wrong for your GPU (RTX 50-series needs
   cu128).
   Fix: rerun §1.2 step (c), then the `torch.cuda.is_available()` check. CPU still
   *works* if you accept the wait (set Device to `cpu`).

4. **Plugin registered but the sidebar entry never appears / API routes 404.**
   Cause: the compute service wasn't restarted after registration: plugin routes are
   collected once at startup.
   Fix: restart Terminal 2 and look for `Plugin kaggle runtime initialized` in its
   log. (For later code/UI iteration the hot-reload endpoint works, as the
   deployment guide describes, but route changes always need a restart.)

5. **Paths with spaces break commands or imports.**
   Cause: unquoted paths (this project's own workspace has a space in it, so it
   *will* happen). PowerShell needs quotes around any path with spaces; JSON needs
   doubled backslashes. The exception is the Import tab's yaml field, which cleans
   pasted quotes itself.
   Fix: quote paths in shells; in `settings.json` use `\\` and check with the §1.4
   parse command.

---

## 7. Architecture / for reviewers

The plugin is one page (`src/tlc_plugin_kaggle/ui.html`) over a small Litestar route
set (`routes.py`) with per-card backends: `importer.py` (validated import, GT-leak
guard), `trainer.py` (locked pinned-init training + provenance assertions),
`predictor.py` (inference → strict CSV validation → optional Kaggle upload),
`jobs.py` (disk-persisted jobs that survive hot reloads), `config_store.py` (saved
form state). Depth, in reading order:

- [docs/ui-notes.md](docs/ui-notes.md): the UI playbook (states, fixtures, motion,
  a11y) and the replication recipe the four tabs were built from.
- [docs/deployment-guide.md](docs/deployment-guide.md): the operator's guide to the
  installed host (discovery, registration, JWT reality, hot reload).
- [docs/training-sanity.md](docs/training-sanity.md): why the contract is a pinned
  pretrained init, with the from-scratch control evidence.
- [docs/design-notes.md](docs/design-notes.md): research-phase notes (host source
  analysis; §7 is a *proposed* skeleton, kept as history).

```
src/tlc_plugin_kaggle/   the plugin (manifest = class attrs on KagglePlugin)
├── __init__.py          plugin class + registration
├── ui.html              the four-tab page (Import / Train / Predict+Submit / Status)
├── routes.py            REST endpoints under /api/plugins/kaggle
├── importer.py          tab 1: import + dataset validation (GT-leak guard)
├── trainer.py           tab 2: locked pinned-init training + provenance
├── predictor.py         tab 3+4: inference, submission.csv, Kaggle API
├── jobs.py              disk-persisted job store (survives hot reload)
└── config_store.py      saved form values per tab
docs/                    design docs (see §7 links above)
scripts/                 one-off maintenance (job-record migration)
pyproject.toml           dist metadata + [tool.tlc-compute] manifest for the
                         future catalog host (hand-synced with the class attrs)
```
