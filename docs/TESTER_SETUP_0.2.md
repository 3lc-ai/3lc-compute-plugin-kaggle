# Tester setup — 0.2.x Hub + Kaggle plugin v1.2.0 (catalog install)

Fresh-machine path. Every version below is **the exact pairing this build was
tested against** — don't float them. Time budget: ~15 min + one big download
(the plugin's worker venv pulls CUDA torch on first install).

## 0. Prerequisites (one-time)

| What | How |
|---|---|
| Python 3.12 | `winget install Python.Python.3.12` |
| uv | `winget install astral-sh.uv` — **required**: the plugin shop installs run through uv |
| git + GitHub access to `3lc-ai` | the plugin repo is private; run `git ls-remote https://github.com/3lc-ai/3lc-compute-plugin-kaggle.git` once so Git Credential Manager stores a token. Without it the shop install fails with `fatal: could not read Username for 'https://github.com'`. |
| NVIDIA GPU + driver (CUDA ≥ 12.8) | `nvidia-smi` |
| 3LC API key | dashboard → account |
| Kaggle credentials | `kaggle.json` in `%USERPROFILE%\.kaggle\` (Submit tab needs it; Import/Train work without) |

## 1. Run the setup script (recommended)

From this repo (or a copy of just the script):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup-0.2-tester.ps1
```

It creates `C:\3lc-hub-next\.venv`, installs **3lc-compute==0.2.1 + 3lc==3.1.0**
from the 3LC package indexes, runs `3lc login` (3lc 3.x uses a **new key
store** — log in again even if a 2.x Hub was logged in on this machine), sets
the two required service env vars (below), and starts both services in their
own windows. Then skip to step 3.

## 2. Manual path (what the script does)

```powershell
uv venv --python 3.12 C:\3lc-hub-next\.venv
uv pip install --python C:\3lc-hub-next\.venv\Scripts\python.exe `
  --extra-index-url https://pypi.3lc.ai/public/repositories/prereleases-public/ `
  --extra-index-url https://pypi.3lc.ai/public/repositories/releases-public/ `
  --index-strategy unsafe-best-match `
  "3lc-compute==0.2.1" "3lc==3.1.0"
C:\3lc-hub-next\.venv\Scripts\3lc.exe login    # paste your API key
```

Set these in the shell that starts the compute service — **both are
Windows-required**:

```powershell
# W1: 0.2.1 spawns plugin workers as <venv>/bin/python (POSIX layout) on every
# OS. On Windows that file doesn't exist and every plugin worker fails with a
# 500 on first use. This per-plugin override pins the correct interpreter path
# (pre-stating where the shop materializes the kaggle venv, version 1.2.0):
$env:TLC_COMPUTE_PLUGIN_VENV_KAGGLE = "$env:USERPROFILE\.3lc-compute\managed-plugins\kaggle\1.2.0\.venv\Scripts\python.exe"

# CUDA torch: shop installs (uv pip install) don't read the plugin's own uv
# index config, so plain `torch` resolves CPU-only on Windows without this:
$env:TLC_COMPUTE_PLUGIN_INDEX_URLS = "https://download.pytorch.org/whl/cu128"
```

Start the services (two windows):

```powershell
C:\3lc-hub-next\.venv\Scripts\3lc.exe service          # Object Service :5015
C:\3lc-hub-next\.venv\Scripts\3lc-compute.exe          # Compute Service :5020 (env vars above set in THIS window)
```

## 3. Install the plugin from the catalog

1. Open the Hub in your browser and go to **Plugins → Available**.
2. Under **Catalog sources**, add:

   ```
   https://raw.githubusercontent.com/3lc-ai/3lc-compute-plugin-kaggle/develop/catalog.json
   ```

   (Private repo: if the raw URL 404s in the Hub, use the local-file
   fallback — clone the repo and add the absolute path to its `catalog.json`
   as the catalog source instead. Both forms are supported.)
3. The **Kaggle Competition** card appears under Available → **Install**.
   First install builds the worker venv (CUDA torch — several GB; watch the
   card's progress). It registers live; no service restart.
4. Click **Kaggle** in the sidebar (AI Tools) — the four-tab page loads.

## 4. Smoke test

Run `SMOKE_TEST.md` from the repo root as before — the flow is unchanged
(Import → Train (2 epochs) → Predict → Submit). Differences from the 1.1.x
manual install you may notice:

- No `settings.json` editing, no plugin-deps pip install, no service restart —
  the catalog install did all of it.
- Job cancel is served by the Hub (generic queue), and running jobs also show
  in the Hub's Queue & Progress panel, not only in the plugin's own tabs.
- If the very first job start reports "worker … provisioning", give the venv
  build a minute and retry — that's the one-time heavy install.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Kaggle page 500s on first open | W1 env var not set in the compute-service window (see step 2), or set to a wrong path — it must point at `...\managed-plugins\kaggle\1.2.0\.venv\Scripts\python.exe` |
| Install fails: `could not read Username for 'https://github.com'` | git has no GitHub token — prerequisite row 3 |
| Install fails: `uv executable not found` | uv not on the PATH of the compute-service process |
| Training says CUDA unavailable | `TLC_COMPUTE_PLUGIN_INDEX_URLS` was not set when the plugin venv was built → uninstall the plugin in the shop, set the env var, reinstall |
| `API key not found` at service start | run `3lc login` **from this venv** (3.x key store is new) |

## Appendix — machine also runs the 1.1.x Hub

Don't share state: the two stacks fight over `~/.3lc-compute/settings.json`
(the old service's writer silently drops the new one's keys). Run the 0.2.x
service with a redirected home (see `3lc-hub-next/PORT_PLAN.md` § switch
procedure in the research workspace) or on a different machine.
