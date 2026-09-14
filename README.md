# 3LC Kaggle Competition plugin

This is the 3LC Hub plugin for **The 3LC Low-Light Detection Challenge (ExDark)** — a
Kaggle object-detection competition where the model is fixed and the leaderboard is
climbed by improving the *data*. Every participant trains the same YOLOv11n from the
same sha256-pinned COCO-pretrained checkpoint at 640 px, and each training run records
verifiable provenance (including the checkpoint hash), so a submission provably came
from the shared contract — the **verified-contract thesis**. The plugin puts the whole
loop on one Hub sidebar page, four tabs: **1 Import → 2 Train → 3 Predict + Submit →
4 Status** — edit labels in the 3LC Dashboard between rounds, retrain on the newest
table revision, submit, repeat.

**Version pairing (v1.2.14):** 3LC Hub with `3lc-compute==0.2.1` + `3lc==3.1.0`
(the 0.2.x plugin platform), or `3lc-compute==1.0.1` + `3lc==3.3.0` (the 1.0.x
line). v1.2.14 installs on both — see [1.0.x deltas](#10x-deltas) for the three
steps that differ.

**Platform support — no promises beyond what's tested:**

| Setup | Status |
|---|---|
| Windows + NVIDIA GPU, everything local | **Validated** — this README + [docs/TESTER_SETUP_0.2.md](docs/TESTER_SETUP_0.2.md) |
| Remote compute host (Linux GPU box), browse from any machine incl. Mac | **Supported** — guide: [docs/TESTER_SETUP_REMOTE.md](docs/TESTER_SETUP_REMOTE.md); surface audit: [docs/REMOTE_COMPUTE.md](docs/REMOTE_COMPUTE.md) |
| Mac-local training (Apple Silicon / MPS) | **Validated** — blank Device auto-selects `mps`; ~4 min/epoch training and ~9 s for the full 715-image predict, pinned-checkpoint sha verified. Setup: [TESTER_SETUP_0.2.md macOS appendix](docs/TESTER_SETUP_0.2.md) — no service env vars needed |

## Licensing

This plugin is licensed **AGPL-3.0-only** (full text in [LICENSE](LICENSE)): it links
`3lc-ultralytics` (Ultralytics YOLO, AGPL-3.0), so a distributed work must itself be
AGPL-3.0.

Ultralytics YOLO is dual-licensed: free under
[AGPL-3.0](https://github.com/ultralytics/ultralytics/blob/main/LICENSE) for use that
complies with its open-source terms, while commercial use beyond those terms requires a
paid [Ultralytics Enterprise License](https://www.ultralytics.com/license). It is the
user's responsibility to ensure their use of Ultralytics YOLO through this plugin is
appropriately licensed. The plugin's UI displays this notice at the top of the page.

**Scope.** This license covers the plugin source in this repository. The competition
dataset published under the `kit-*` tags is a separate release with its own terms; the
ExDark images carry their own upstream licenses.

---

## 1. Install — catalog (the primary path)

**Full walkthrough with the exact pinned commands and a one-shot setup script:
[docs/TESTER_SETUP_0.2.md](docs/TESTER_SETUP_0.2.md).** The short version below
is the **0.2.x** route; on a **1.0.x** host three of its steps change — see
[1.0.x deltas](#10x-deltas) right after it. Same plugin, same `@v1.2.14` tag,
same four-tab page either way.

1. **Hub venv** (Python 3.12 via uv; `uv` itself is required at runtime — the
   plugin shop installs run through it):

   ```powershell
   uv venv --python 3.12 C:\3lc-hub-next\.venv
   uv pip install --python C:\3lc-hub-next\.venv\Scripts\python.exe `
     --extra-index-url https://pypi.3lc.ai/public/repositories/prereleases-public/ `
     --extra-index-url https://pypi.3lc.ai/public/repositories/releases-public/ `
     --index-strategy unsafe-best-match `
     "3lc-compute==0.2.1" "3lc==3.1.0"
   C:\3lc-hub-next\.venv\Scripts\3lc.exe login
   ```

   No torch here — the plugin's heavy stack lives in its own worker venv, installed
   by the shop. (3lc 3.x uses a **new API-key store**; log in again even if a 2.x
   Hub was logged in on this machine.)

2. **Two Windows-required env vars** in the compute-service shell (worker
   interpreter workaround + GPU torch selection — details in the tester doc;
   neither is needed on macOS/Linux, though the second is a harmless no-op there):

   ```powershell
   $env:TLC_COMPUTE_PLUGIN_VENV_KAGGLE_EXDARK = "$env:USERPROFILE\.3lc-compute\managed-plugins\kaggle-exdark\1.2.14\.venv\Scripts\python.exe"
   $env:UV_TORCH_BACKEND = "auto"
   ```

3. **Start services** (`3lc service` on :5015, `3lc-compute` on :5020), open the
   Hub, **Plugins → Available → Catalog sources**, add the hosted catalog URL

   ```
   https://gist.githubusercontent.com/Rishikesh-Jadhav/926ead27a6a1ed6429cf86d1924a24ce/raw/catalog.json
   ```

   (the Hub fetches catalogs unauthenticated. The gist mirrors this repo's
   own [`catalog.json`](catalog.json), which stays the source of truth.
   Fallback: the absolute path to `catalog.json` in a local clone also works
   as a catalog source), and click **Install** on the *Kaggle Competition*
   card. First install builds the
   worker venv (CUDA torch, several GB, one-time). It registers live — **no
   settings.json editing, no dependency pip installs, no service restart.**

4. **Kaggle Competition** appears in the sidebar under **AI TOOLS**.

Updating later: publishing v1.2.x means a new catalog entry — the card grows an
**Update** button; one click swaps the version. Publishing steps are in
[RELEASING.md](RELEASING.md).

### 1.0.x deltas

On compute 1.0.1 + 3lc 3.3.0, steps 1, 2 and 3 above are 0.2.x-specific; the
rest of the flow is identical.

- **Step 1 — no 3LC indexes.** 1.0.1 and 3lc 3.3.0 are both on public PyPI:
  `uv pip install --index-url https://pypi.org/simple "3lc-compute==1.0.1" "3lc==3.3.0"`.
  `uv` also ships as a dependency now, so it need not be on PATH.
- **Step 2 — one env var, not two.** 1.0.x derives `Scripts\python.exe`
  itself, so `TLC_COMPUTE_PLUGIN_VENV_KAGGLE_EXDARK` is not set on this
  generation. Keep `UV_TORCH_BACKEND=auto`.
- **Step 3 — the catalog URL is an env var, not a paste.** 1.0.1 defaults to
  `plugin_install_policy: "catalog-only"`, and that policy **also gates adding a
  catalog through the API**, so the Hub's *Catalog sources* field returns 403:
  adding a catalog grants trust, so it sits behind the same gate as installing.
  Set it on the compute-service command instead, **listing both URLs** — the env
  value *replaces* the baked-in default catalog, so the gist alone would hide
  the stock 3LC cards:

  ```powershell
  $env:TLC_COMPUTE_PLUGIN_CATALOG_URLS = "https://gist.githubusercontent.com/Rishikesh-Jadhav/926ead27a6a1ed6429cf86d1924a24ce/raw/catalog.json,https://3lc-public-examples-2-2.s3.amazonaws.com/hub/catalog.json"
  ```

  Then start the service and click **Install** on the card as before.

---

## 2. Kaggle auth (KGAT token)

The plugin never stores credentials; the `kaggle` client reads them itself. Create a
token on kaggle.com (**Settings → API → Create New Token** — new tokens look like
`KGAT_...`), then save it on the machine running the compute service with **exactly**
one of these. The file must be byte-exact: plain ASCII, **no BOM, no trailing
newline** — which is why it's `-NoNewline` on Windows and `printf`, never `echo`
(echo appends a newline), on macOS/Linux:

**Windows (PowerShell)**

```powershell
mkdir "$env:USERPROFILE\.kaggle" -Force
Set-Content -Path "$env:USERPROFILE\.kaggle\access_token" -Value "KGAT_<your token>" -NoNewline -Encoding ascii
```

**macOS / Linux**

```bash
mkdir -p ~/.kaggle && printf '%s' "KGAT_<your token>" > ~/.kaggle/access_token
```

(Legacy `~/.kaggle/kaggle.json` and the `KAGGLE_API_TOKEN` env var also work.)
Everything except the actual Kaggle upload works with no credentials at all — you
get a CSV either way.

---

## 3. Getting the data

The competition starter kit is **not in this repo** (it is ~625 MB), and it is
**not on the Kaggle Data tab** either. That tab carries the competition README and
`sample_submission.csv`; the plugin is how you get the data.

**Get it from the plugin.** The Import tab opens with a **Starter kit** section:
click **Download starter kit**. It fetches the kit from 3LC's content network,
verifies every file against a published manifest by sha256, and fills the Dataset
YAML path for you, so the Import gate goes green without a keystroke.

- It downloads to the **compute host**, which is the machine that needs it — the
  browser can be somewhere else entirely (docs/TESTER_SETUP_REMOTE.md).
- Interruptions resume from the finished shards rather than restarting, and it is
  safe to navigate away: the job runs in the worker, and the section reattaches to
  a download in progress when you return.
- The revisit line's quiet **Verify** action re-checks every file on demand.

It lands in a versioned folder under `~/.3lc-kaggle-plugin/data/` (the section names
the exact path). **Leave it where it is** — the Hub reads your images from that
folder for as long as the tables exist, so don't move or rename it after importing.
Inside: `dataset.yaml`, `sample_submission.csv`, the ExDark licence notice,
`images/` (train 5,910 · val 733 · test 715) and `labels/` (train + val only; test
ground truth is hidden). There is nothing to run in the kit — the whole loop happens
in the plugin.

Already have a copy from somewhere else? Point the Dataset YAML field at its
`dataset.yaml` and Import reads it the same way; the download is an offer, not a
gate.

---

## 4. Running the loop (the 15-minute smoke path)

The strict checklist version of this section, with pass/fail boxes, is
[SMOKE_TEST.md](SMOKE_TEST.md) — use that when reporting. Prose version:

1. **Import** — paste the full path of the kit's `dataset.yaml` into the Import tab
   (quotes from "Copy as path" are fine — the field strips them). Preflight goes
   green; click **Import & Validate**. Expected in ~2–5 min: three tables
   (`exdark_train` 5,910 · `exdark_val` 733 · `exdark_test` 715) and **9/9 validation
   checks green**, including "test table carries no ground-truth boxes".
2. **Train** — the contract panel shows the locked trio (yolo11n.pt + sha256, 640 px,
   pretrained). Set **Epochs = 2**, leave the rest at defaults, **Start Training**.
   First run downloads the pinned checkpoint (5.4 MB, one-time). Expected: live
   epoch metrics; **val mAP50 ≈ 0.5 by epoch 2** (reference: 0.533); on completion a
   **Verified provenance recorded** panel with **4/4 assertions**, one of them the
   checkpoint sha256 `0ebbc80d4a76…`. Running jobs also appear in the Hub's generic
   **Queue & Progress** panel now.
   Timing: ~5–8 min for 2 epochs on a 12 GB-class desktop GPU. Smaller cards run
   at a smaller effective batch to fit VRAM — an 8 GB card trains at batch 8
   and takes roughly twice the desktop per-epoch time; slower is normal, only a
   *failure* is a finding.
   After training the plugin frees GPU memory before Predict, and Predict
   streams inference in VRAM-sized chunks.
3. **Predict** — Predict + Submit tab, Step 1: source = your plugin run (participants
   have no other option), test table prefilled, **Run inference**. Expected in ~1–2
   min: results panel, all format checks green, `submission.csv` written (path
   shown). A local mAP score appears **only on the organizer machine** — on your
   machine no score is expected; that's by design, not a bug.
4. **Download the CSV** — click **Download CSV** on the results panel and open it:
   715 rows + header, columns `id,image_id,prediction_string`.
   **Round-2 policy: submitting is allowed and encouraged.** If you're invited to
   the competition and have accepted the rules on the Kaggle page, Step 2
   (Submit to Kaggle) uploads the CSV and the score shows up on Kaggle and the
   Status tab (3/day budget — one submission is plenty; remember no local mAP on
   your machine is by design, the Kaggle score is the real one). If you have
   **not** joined the competition you'll see a friendly "not joined" state before
   an attempt is burned — also expected.
5. **Status** — the hero strip shows your latest run/CSV; the history table lists the
   prediction with a Download CSV action. With Kaggle connected, the connection card
   shows your username and your remaining daily submissions.

---

## 5. What to test & how to report

Happy paths (per tab), then the deliberate failure paths:

- [ ] Import, Train (2 epochs), Predict, CSV download, Status — the section-4 path.
- [ ] **One failure path**: point Import at a nonsense yaml path (e.g.
  `C:\nope\dataset.yaml`) — expect a readable error state, not a spinner or a stack
  trace, and a working **Copy diagnostics** button.
- [ ] **Fixture tour**: append `?kgdev=<state>` to the plugin page URL and skim each
  state: Import `state1…state6` (incl. `state2-mismatch`, `state2-error`, `state5`),
  Train `train-state1…train-state6`, `submit-results`, `submit-success`,
  `submit-participant`, `predict-legacy-run`, `status-history`. Fixtures are static
  demo states: action buttons render disabled with a "demo state" note, and nothing
  fetches or fires. Full map in [docs/ui-notes.md](docs/ui-notes.md).
- [ ] **Narrow width**: DevTools responsive mode at ~680 px — no horizontal scroll,
  no clipped panels.
- [ ] **Reduced motion**: emulate `prefers-reduced-motion: reduce` — everything still
  renders, minus animation.

**Found a bug?** Every tab has a **Copy diagnostics** button (also embedded in error
banners) that copies a fenced block with the plugin version, inputs, checks, and log
tail. Paste that block plus what you expected vs. saw.
Open an issue on this repository with that block attached.

---

## 6. Troubleshooting — the likely failures

> **Startup traceback in the object-service window = HARMLESS (known bug W5).**
> On the 0.2.1 + 3.1.0 pairing the Object Service prints a traceback at startup
> (`ConfigIndexingTable` rejecting `object_type 'configfile'` — public-examples
> indexing is broken in this pairing). It is caught and logged, affects nothing
> in the competition workflow, and is not a finding.

1. **Kaggle page 500s on first open / every job start fails.** *(0.2.x only —
   this env var is not set on 1.0.x.)*
   Cause: the Windows worker-interpreter bug (0.2.1 spawns `<venv>/bin/python`,
   a POSIX path) — the `TLC_COMPUTE_PLUGIN_VENV_KAGGLE_EXDARK` env var from §1
   step 2 is missing or wrong in the compute-service window.
   Fix: set it (exact path in [docs/TESTER_SETUP_0.2.md](docs/TESTER_SETUP_0.2.md))
   and restart the compute service window.

2. **Catalog install fails: `could not read Username for 'https://github.com'`.**
   Cause: git is prompting for a credential. The repo is public and the
   install source needs no token, so this points at a credential helper
   configured to demand one.
   Fix: `git ls-remote https://github.com/3lc-ai/3lc-compute-plugin-kaggle.git`
   once to confirm anonymous read works, then retry Install.

3. **Training says CUDA unavailable / crawls on CPU.**
   Cause: the worker venv was built without `UV_TORCH_BACKEND=auto`
   (shop installs resolve plain `torch` from PyPI = CPU-only on Windows).
   Fix: set the env var (§1 step 2), **Uninstall** the plugin in the shop,
   reinstall. Verify inside the worker venv:
   `& "$env:USERPROFILE\.3lc-compute\managed-plugins\kaggle-exdark\1.2.14\.venv\Scripts\python.exe" -c "import torch; print(torch.cuda.is_available())"`.

4. **Kaggle shows "not connected" / auth fails though the token file exists.**
   Cause: the token file isn't byte-exact — a BOM, a trailing newline, or UTF-16
   encoding from a text editor.
   Fix: rewrite with the `Set-Content ... -NoNewline -Encoding ascii` one-liner in
   §2. Don't create the file in Notepad.

5. **`API key not found` when the service starts.**
   Cause: 3lc 3.x reads a new key-store file; a 2.x-era login doesn't carry over.
   Fix: `3lc login` from the 0.2.x venv.

6. **Paths with spaces break commands.**
   PowerShell needs quotes around any path with spaces. The Import tab's yaml field
   cleans pasted quotes itself.

7. **"Do I have CUDA?" — check `nvidia-smi`, not `nvcc`.**
   `nvidia-smi`'s top-right **CUDA Version** is the driver's capability and is what
   matters (needs ≥ 12.8). `nvcc` is the compiler from the CUDA *toolkit*, which
   you do **not** need — if you typed it you saw
   `nvcc : The term 'nvcc' is not recognized...`; that is not a missing-CUDA
   symptom, it's the wrong command.

8. **Catalog install fails: `Repository not found`.**
   Different from row 2's `could not read Username`: here git *has* a stored
   GitHub credential, but a stale one (an old account or expired token). Fix:
   Windows **Credential Manager → Windows Credentials**, delete the
   `git:https://github.com` entry, then run
   `git ls-remote https://github.com/3lc-ai/3lc-compute-plugin-kaggle.git` and
   sign in fresh.

9. **`uv` errors that don't match this README (old version).**
   A previously installed uv can shadow the winget one until you restart the
   shell. Check which one runs: `(Get-Command uv).Source` and `uv --version`.
   If it points somewhere unexpected, **restart the shell** (PATH updates don't
   reach already-open windows) and check again.

10. **An `ERROR ... API key` line before you've logged in.**
    Normal ordering artifact: the service checks the key store before your first
    `3lc login` has run (or in the setup script, before the login step). It
    clears on the next start after login. Only a *persistent* key error after a
    successful login is a finding (see row 5).

11. **First training run downloads an extra file, `yolo26n.pt` — needs internet.**
    ultralytics runs a one-time AMP sanity check at train start that fetches
    `yolo26n.pt` (~5 MB) from GitHub. This is ultralytics' own health check, not
    part of the competition contract — separate from our pinned `yolo11n.pt`
    checkpoint. On a machine with no internet at all the check is skipped with a
    log warning (harmless); on a firewalled/proxied network the download can
    stall or error the first run. Workaround: run the first train once on an
    open network, or place a `yolo26n.pt` in the compute-service working
    directory — once the file exists it is never downloaded again.

---

## 7. Architecture / for reviewers

The plugin is one page (`src/tlc_plugin_kaggle/ui.html`) over a small Litestar route
set (`routes.py`) with per-card backends: `importer.py` (validated import, GT-leak
guard), `trainer.py` (locked pinned-init training + provenance assertions),
`predictor.py` (inference → strict CSV validation → optional Kaggle upload),
`jobs.py` (disk-persisted jobs bridged onto the host dispatch channel),
`config_store.py` (saved form state). On the 0.2.x host the plugin runs
**out-of-process**: an SDK worker in its own uv-provisioned venv, reverse-proxied by
the compute service; long jobs start through the host's `/run` dispatch (Queue-panel
progress, host cancel) after a fail-fast `/validate/<kind>` round-trip. Depth, in
reading order:

- [docs/ui-notes.md](docs/ui-notes.md) — the UI playbook: states, fixtures, motion,
  a11y; plus the 0.2.x worker model and the job-start contract.
- [docs/TESTER_SETUP_0.2.md](docs/TESTER_SETUP_0.2.md) — fresh-machine setup with
  the pinned stack + setup script.
- [docs/TESTER_SETUP_REMOTE.md](docs/TESTER_SETUP_REMOTE.md) — remote Linux GPU
  host setup (browse from a Mac or any laptop).
- [docs/REMOTE_COMPUTE.md](docs/REMOTE_COMPUTE.md) — the browser≠host surface
  matrix behind the remote guide.
- [docs/training-sanity.md](docs/training-sanity.md) — the reference training
  trajectory, and the evidence that the data pipeline is healthy.

```
src/tlc_plugin_kaggle/   the plugin (manifest = plugin.toml, read import-free)
├── __init__.py          SDK ComputePlugin subclass + run_job dispatch
├── plugin.toml          the manifest (id / ui / runtime / provision extra)
├── ui.html              the four-tab page (Import / Train / Predict+Submit / Status)
├── routes.py            worker-app REST endpoints (relative; host proxies them)
├── importer.py          tab 1: import + dataset validation (GT-leak guard)
├── trainer.py           tab 2: locked pinned-init training + provenance
├── predictor.py         tab 3+4: inference, submission.csv, Kaggle API
├── jobs.py              disk-persisted job store + JobContext bridge
└── config_store.py      saved form values per tab (~/.3lc-kaggle-plugin/)
catalog.json             the shop listing (id, version, source, manifest copy)
docs/                    see §7 links above
scripts/                 setup-0.2-tester.ps1 + one-off maintenance
pyproject.toml           dist metadata; [kaggle] extra = the worker venv's stack
```
