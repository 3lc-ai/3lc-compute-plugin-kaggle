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

<!-- VALIDATE (user): screenshots not yet captured. Capture per demo/SHOT_LIST.md
     (workspace), save into docs/shots/ with these filenames, commit, and delete
     this comment. The provenance panel (?kgdev=train-state4) is the centerpiece. -->
![Verified provenance panel — the centerpiece](docs/shots/03_provenance_hash.png)
![Train contract panel](docs/shots/02_train_contract.png)
![Predict results](docs/shots/05_predict_results.png)
![Status hero + history](docs/shots/09_status_history.png)

**Version pairing (v1.2.0):** 3LC Hub with `3lc-compute==0.2.1` + `3lc==3.1.0`
(the 0.2.x plugin platform). For the legacy 0.1.x-host install (plugin v1.1.x),
see [Appendix A](#appendix-a--legacy-01x-host-install-plugin-v11x).

---

## 1. Install — catalog (the primary path)

**Full walkthrough with the exact pinned commands and a one-shot setup script:
[docs/TESTER_SETUP_0.2.md](docs/TESTER_SETUP_0.2.md).** The short version:

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
   interpreter workaround + CUDA torch index — details in the tester doc):

   ```powershell
   $env:TLC_COMPUTE_PLUGIN_VENV_KAGGLE = "$env:USERPROFILE\.3lc-compute\managed-plugins\kaggle\1.2.0\.venv\Scripts\python.exe"
   $env:TLC_COMPUTE_PLUGIN_INDEX_URLS = "https://download.pytorch.org/whl/cu128"
   ```

3. **Start services** (`3lc service` on :5015, `3lc-compute` on :5020), open the
   Hub, **Plugins → Available → Catalog sources**, add the hosted catalog URL

   ```
   https://gist.githubusercontent.com/Rishikesh-Jadhav/926ead27a6a1ed6429cf86d1924a24ce/raw/catalog.json
   ```

   (the Hub fetches catalogs unauthenticated, so the catalog is hosted on a
   public gist while the repo is private — repo raw URLs 404; the install
   source inside the catalog goes through git, which has your credentials.
   Fallback: the absolute path to [`catalog.json`](catalog.json) in a local
   clone also works as a catalog source), and
   click **Install** on the *Kaggle Competition* card. First install builds the
   worker venv (CUDA torch, several GB, one-time). It registers live — **no
   settings.json editing, no dependency pip installs, no service restart.**

4. **Kaggle** appears in the sidebar under **AI TOOLS**.

Updating later: publishing v1.2.x means a new catalog entry — the card grows an
**Update** button; one click swaps the version. Publishing steps are in
[RELEASING.md](RELEASING.md).

---

## 2. Kaggle auth (KGAT token)

The plugin never stores credentials; the `kaggle` client reads them itself. Create a
token on kaggle.com (**Settings → API → Create New Token** — new tokens look like
`KGAT_...`), then save it with **exactly** this (the bash commands kaggle.com shows
will not work on Windows):

```powershell
mkdir "$env:USERPROFILE\.kaggle" -Force
Set-Content -Path "$env:USERPROFILE\.kaggle\access_token" -Value "KGAT_<your token>" -NoNewline -Encoding ascii
```

The file must be byte-exact: plain ASCII, **no BOM, no trailing newline** —
`-NoNewline -Encoding ascii` guarantees that. (Legacy `~/.kaggle/kaggle.json` and the
`KAGGLE_API_TOKEN` env var also work.) Everything except the actual Kaggle upload
works with no credentials at all — you get a CSV either way.

---

## 3. Getting the data

The competition starter kit is **not in this repo** (it is ~616 MB).

<!-- VALIDATE (user): distribution channel for testers — currently the kit exists as
     a local build artifact and on the private Kaggle competition's Data tab. -->
- Ask the organizer (Rishikesh) for `starter_kit.zip`.
- If you received the organizer's build: **615,995,197 bytes**, sha256
  `5bf297eed3dc6d12811c7c7eee1c8cc28ba6db4197f0530bd2322f63adbbdca1`
  (`Get-FileHash starter_kit.zip` to check).
- If you downloaded it from the Kaggle competition page instead, Kaggle re-zips the
  files: **616,590,902 bytes**, sha256 `39f2b48c…` — different hash, byte-identical
  contents. Don't file a bug about the mismatch.

**Unzip it somewhere permanent.** The Hub reads images from that folder forever after
import — don't move or rename it. Inside: `dataset.yaml`, `sample_submission.csv`,
`images/` (train 5,910 · val 733 · test 715) and `labels/` (train + val only; test
ground truth is hidden). There is nothing to run in the kit — the whole loop happens
in the plugin.

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
3. **Predict** — Predict + Submit tab, Step 1: source = your plugin run (participants
   have no other option), test table prefilled, **Run inference**. Expected in ~1–2
   min: results panel, all format checks green, `submission.csv` written (path
   shown). A local mAP score appears **only on the organizer machine** — on your
   machine no score is expected; that's by design, not a bug.
4. **Download the CSV** — click **Download CSV** on the results panel and open it:
   715 rows + header, columns `id,image_id,prediction_string`.
   **Do NOT proceed to Step 2 (Submit to Kaggle).** Submissions are budgeted
   (3/day on the private competition) and reserved for the organizer. If you're not
   invited to the private competition you'll see a friendly "not joined" state —
   also expected. (The competition slug you'll see contains a real typo,
   `...comepetition-test` — it's in the actual Kaggle URL.)
5. **Status** — the hero strip shows your latest run/CSV; the history table lists the
   prediction with a Download CSV action. With Kaggle connected, the connection card
   shows your username; the used-today counter may be absent (a known API 403 on the
   private competition — it self-heals on the public one).

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
<!-- VALIDATE (user): where should testers send reports — Slack channel or email? -->
Send reports to Rishikesh (rishikesh.jadhav@3lc.ai).

---

## 6. Troubleshooting — the likely failures

1. **Kaggle page 500s on first open / every job start fails.**
   Cause: the Windows worker-interpreter bug (0.2.1 spawns `<venv>/bin/python`,
   a POSIX path) — the `TLC_COMPUTE_PLUGIN_VENV_KAGGLE` env var from §1 step 2 is
   missing or wrong in the compute-service window.
   Fix: set it (exact path in [docs/TESTER_SETUP_0.2.md](docs/TESTER_SETUP_0.2.md))
   and restart the compute service window.

2. **Catalog install fails: `could not read Username for 'https://github.com'`.**
   Cause: the repo is private and git has no stored GitHub credential.
   Fix: `git ls-remote https://github.com/3lc-ai/3lc-compute-plugin-kaggle.git`
   once (interactive sign-in via Git Credential Manager), retry Install.

3. **Training says CUDA unavailable / crawls on CPU.**
   Cause: the worker venv was built without `TLC_COMPUTE_PLUGIN_INDEX_URLS`
   (shop installs resolve plain `torch` from PyPI = CPU-only on Windows).
   Fix: set the env var (§1 step 2), **Uninstall** the plugin in the shop,
   reinstall. Verify inside the worker venv:
   `& "$env:USERPROFILE\.3lc-compute\managed-plugins\kaggle\1.2.0\.venv\Scripts\python.exe" -c "import torch; print(torch.cuda.is_available())"`.

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
  a11y; plus the 0.2.x worker-model dev loop and the job-start contract change.
- [docs/forced-changes-0.2.md](docs/forced-changes-0.2.md) — everything the 0.2.x
  port changed, and why; nothing else moved.
- [docs/TESTER_SETUP_0.2.md](docs/TESTER_SETUP_0.2.md) — fresh-machine setup with
  the pinned stack + setup script.
- [docs/deployment-guide.md](docs/deployment-guide.md) — the LEGACY 0.1.x-host
  operator guide (kept for v1.1.x installs).
- [docs/training-sanity.md](docs/training-sanity.md) — why the contract is a pinned
  pretrained init, with the from-scratch control evidence.
- [docs/design-notes.md](docs/design-notes.md) — research-phase notes (host source
  analysis; §7 is a *proposed* skeleton, kept as history).

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

---

## Appendix A — legacy 0.1.x-host install (plugin v1.1.x)

Plugin **v1.1.1** targets the previous Hub generation (`3lc-compute 0.1.1.47` +
`3lc 2.22.3`, in-process plugins, manual registration). That path — venv build
order, BOM-free `settings.json` registration, service restart, and its
troubleshooting — is preserved verbatim in the v1.1.1 tag's
[README](https://github.com/3lc-ai/3lc-compute-plugin-kaggle/blob/v1.1.1/README.md)
and [docs/deployment-guide.md](docs/deployment-guide.md). Do not mix the two stacks
in one environment: both hosts read `~/.3lc-compute/settings.json`, and the 0.1.x
writer silently drops the 0.2.x keys. Also note the 0.1.x host loads the plugin
live from the repo working copy — keep that checkout on `develop` whenever the
old service runs; the 0.2.x host installs from the git tag and doesn't care.
