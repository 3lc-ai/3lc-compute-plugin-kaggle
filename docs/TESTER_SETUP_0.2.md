# Tester setup — 0.2.x Hub + Kaggle plugin v1.2.7 (catalog install)

> **MIGRATION — round-1 testers only (installed v1.2.0 under the old id `kaggle`).**
> v1.2.1 renamed the plugin id to **`kaggle-exdark`** (collision safety). The old
> install won't update in place — do this once, in this order:
>
> 1. **Kill the orphan worker first** (known 0.2.1 bug W3: uninstall does NOT stop
>    the worker process, and the leftover lock breaks reinstall): **close the
>    compute-service window and start it again** — that's the whole step
>    (verified clean 2026-08-14: no orphaned directory, uninstall succeeded).
>    Optional alternative for the restart-averse: the reload endpoint
>    `Invoke-RestMethod -Method Post http://localhost:5020/api/admin/plugins/kaggle/reload`
>    — but on 0.2.x admin routes answer `403 unauthenticated` without the Hub's
>    Bearer token (copy one from a logged-in Hub tab's DevTools → Network →
>    any request's Authorization header), so the restart is the primary path.
> 2. **Uninstall** the old *Kaggle Competition* card (Plugins → Installed → Uninstall).
>    Then verify `%USERPROFILE%\.3lc-compute\managed-plugins\kaggle\` is actually gone —
>    if not, close the service window and delete the folder by hand.
> 3. **Update the env var** in the compute-service window: the old
>    `TLC_COMPUTE_PLUGIN_VENV_KAGGLE` is dead; set
>    `TLC_COMPUTE_PLUGIN_VENV_KAGGLE_EXDARK` as shown in step 2 below, then restart
>    the compute service.
> 4. **Re-add the catalog** only if you had the local-clone fallback (pull first);
>    the gist URL is unchanged. **Install** the new card — it installs under
>    `managed-plugins\kaggle-exdark\1.2.7\`.
>
> Job history, saved form values, and run artifacts live in `~/.3lc-kaggle-plugin/`
> and survive the rename untouched. *(This note comes out once round-2 starts clean.)*

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
| Kaggle credentials | KGAT token saved byte-exact to `~/.kaggle/access_token` — dual-platform commands in README §2 (Submit tab needs it; Import/Train work without; legacy `kaggle.json` also works) |

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
# (pre-stating where the shop materializes the venv: id kaggle-exdark,
# version 1.2.7 — the env-var name is TLC_COMPUTE_PLUGIN_VENV_ +
# id.upper() with hyphens as underscores. The version segment tracks the
# INSTALLED plugin version — repoint on every update, see the note after
# the service-start block):
$env:TLC_COMPUTE_PLUGIN_VENV_KAGGLE_EXDARK = "$env:USERPROFILE\.3lc-compute\managed-plugins\kaggle-exdark\1.2.7\.venv\Scripts\python.exe"

# CUDA torch: shop installs (uv pip install) don't read the plugin's own uv
# index config, so plain `torch` resolves CPU-only on Windows without this.
# "auto" makes uv detect the machine's GPU driver and pick the matching torch
# wheel index itself (right CUDA version per driver; harmless no-op on
# machines without an NVIDIA GPU, Macs included). Needs a current uv — the
# winget one qualifies:
$env:UV_TORCH_BACKEND = "auto"
```

Start the services (two windows):

```powershell
C:\3lc-hub-next\.venv\Scripts\3lc.exe service          # Object Service :5015
C:\3lc-hub-next\.venv\Scripts\3lc-compute.exe          # Compute Service :5020 (env vars above set in THIS window)
```

> **Updating the plugin later (Windows):** the venv path in
> `TLC_COMPUTE_PLUGIN_VENV_KAGGLE_EXDARK` is version-suffixed, so every
> plugin update moves it. After installing a new version from the catalog:
>
> 1. Close the compute-service window (this kills the plugin worker —
>    never mid-train).
> 2. Repoint the env var at the new
>    `...\managed-plugins\kaggle-exdark\<new version>\.venv\Scripts\python.exe`
>    and start the service again. A stale path fails exactly like W1: the
>    worker 500s on first use while the shop still shows the new version
>    installed.
> 3. **Hard-refresh the plugin page** (Ctrl+Shift+R) — required, not
>    optional. Until you do, the browser may keep serving the old cached
>    page, and every settings change silently fails to save: nothing on
>    the page signals it, values just revert on the next reload. One
>    hard refresh fixes it for good.

## 3. Install the plugin from the catalog

1. Open the Hub in your browser and go to **Plugins → Available**.
2. Under **Catalog sources**, paste the hosted catalog URL:

   ```
   https://gist.githubusercontent.com/Rishikesh-Jadhav/926ead27a6a1ed6429cf86d1924a24ce/raw/catalog.json
   ```

   (That's the latest-revision raw form — the URL never changes; it always
   serves the newest published catalog. The Hub fetches catalogs without
   auth, which is why the catalog is hosted on a public gist while the repo
   is private — repo raw URLs 404. The *install source* inside the catalog
   is unaffected — it goes through git, which has your credentials; that's
   what the `git ls-remote` prerequisite above is for.)

   *Fallback (gist unreachable / offline):* local paths are also a
   supported catalog form — clone the repo and add the absolute path to its
   `catalog.json`:

   ```powershell
   git clone https://github.com/3lc-ai/3lc-compute-plugin-kaggle C:\src\kgplugin
   # then add as catalog source in the Hub:  C:\src\kgplugin\catalog.json
   ```
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

> **A traceback in the object-service window at startup is HARMLESS** (known
> bug W5: `ConfigIndexingTable` / `object_type 'configfile'` — public-examples
> indexing broken in the 0.2.1 + 3.1.0 pairing, caught and logged). Not a
> finding; don't report it.

| Symptom | Cause / fix |
|---|---|
| `nvcc : The term 'nvcc' is not recognized...` | Wrong command — you don't need the CUDA toolkit. Run `nvidia-smi` and read the top-right **CUDA Version** (driver capability, needs ≥ 12.8). |
| Install fails: `Repository not found` | git has a **stale** GitHub credential (vs. row below = none at all). Credential Manager → Windows Credentials → delete `git:https://github.com`, re-run the `git ls-remote` prerequisite, sign in fresh. |
| uv behaves unlike this doc / version mismatch | An older uv shadows the winget one until the shell restarts. `(Get-Command uv).Source` + `uv --version` to see which runs; restart the shell after installing. |
| `ERROR ... API key` printed before your first login | Normal ordering artifact — clears on the next start after `3lc login`. Only a persistent key error *after* a successful login is a finding. |
| Kaggle page 500s on first open | W1 env var not set in the compute-service window (see step 2), or set to a wrong path — it must point at `...\managed-plugins\kaggle-exdark\1.2.7\.venv\Scripts\python.exe`. Round-1 machines: the OLD name `TLC_COMPUTE_PLUGIN_VENV_KAGGLE` no longer does anything. |
| `Failed to load plugin: Internal Server Error` on the Kaggle page | The W1 env var's **version segment** points at a plugin venv that doesn't exist — typical after a plugin update (the shop installs the new version under a new `...\kaggle-exdark\<version>\.venv` and the old pin was never repointed). List what's actually on disk with `Get-ChildItem $env:USERPROFILE\.3lc-compute\managed-plugins\kaggle-exdark`, repoint the env var's version segment in the compute-service window, restart the service. **The silent twin:** if the OLD version's venv is still on disk (uninstall never removes venvs, bug W3), the stale pin *passes* the path check and the worker quietly runs the old plugin — no error, wrong footer version. The setup script's preflight now detects both shapes. |
| Install fails: `could not read Username for 'https://github.com'` | git has no GitHub token — prerequisite row 3 |
| Install fails: `uv executable not found` | uv not on the PATH of the compute-service process |
| Training says CUDA unavailable | `UV_TORCH_BACKEND=auto` was not set when the plugin venv was built → uninstall the plugin in the shop, set the env var, reinstall. (Round-1/2 machines: the old `TLC_COMPUTE_PLUGIN_INDEX_URLS` cu128 pin still works, but `UV_TORCH_BACKEND=auto` supersedes it.) |
| Settings don't persist / revert on reload (after an update) | Stale cached fragment: the old page saves settings in a format the new version rejects, and nothing visible fails at save time. **Hard-refresh the plugin page** (Ctrl+Shift+R) once — see step 3 of the update note in §2. |
| `API key not found` at service start | run `3lc login` **from this venv** (3.x key store is new) |
| `The filename, directory name, or volume label syntax is incorrect` on the setup commands | You're in **cmd**, not PowerShell — the setup commands are PowerShell. Type `powershell` first, then re-run the block. |

## Appendix — macOS (Apple silicon)

Same flow, Windows-isms swapped out:

- **Prerequisites:** `brew install uv git` (or the official installers); Python 3.12
  via `uv python install 3.12`. No NVIDIA/driver row — there is no CUDA on macOS.
- **Neither service env var is needed.** W1 is Windows-only (macOS really has the
  POSIX `<venv>/bin/python` layout the 0.2.1 spawner assumes), and
  `UV_TORCH_BACKEND=auto` is a harmless no-op on macOS — the default PyPI torch
  wheels already include MPS (Apple GPU) support. Setting them anyway breaks nothing.
- **Paths:** venv interpreters are `.venv/bin/python`; the worker venv lands at
  `~/.3lc-compute/managed-plugins/kaggle-exdark/<version>/.venv/bin/python`.
- **Device field (Train and Predict):** leave blank — auto resolves
  CUDA → `mps` → CPU, so Apple silicon trains on the GPU. Typing `0` requests
  NVIDIA GPU #0 and **fails** on a Mac; `mps` and `cpu` also work explicitly.
- **Kaggle token:** same `~/.kaggle/access_token` path; the macOS command is in
  README §2 (`printf '%s' …` — printf, not echo: no trailing newline allowed).
- **Pre-tag testing** (validating branch commits that aren't in a tag yet):
  clone the repo, edit your local `catalog.json` so the version's `source` ends
  in `@port/0.2.x` (or a commit sha) instead of the pinned `@vX.Y.Z` tag, and add that file's
  absolute path as the catalog source instead of the gist URL.

## Appendix — organizer machines (local scoring)

Participants never need this section. On the organizer's machine the plugin
also scores each prediction locally (mAP@0.5 next to the CSV) and unlocks the
host-only UI (the direct weights-file source). The gate is two files that are
never shipped:

```
<host dir>\metric_exdark.py
<host dir>\solution.csv
```

**Where `<host dir>` is:** by default `~\.3lc-kaggle-plugin\host\` resolved
under the home of the **worker process**, not the person browsing. On a plain
install those are the same. They differ whenever the service runs with a
redirected home (the 1.1.x-coexistence setup below) or as another user — the
files then sit in your home while the worker looks in its own, and the host
UI silently stays participant-mode. That silence is by design (participants
must never see an error about files they are not supposed to have), so check
this appendix first when local scores don't render.

Two supported fixes — both verified live (local mAP renders, e.g. 0.4308):

1. **`TLC_KAGGLE_HOST_DIR`** (organizer capability, v1.2.7) — a service env
   var pointing the host dir anywhere. Set it in the service window before
   starting, alongside the other env vars from §2:

   ```powershell
   $env:TLC_KAGGLE_HOST_DIR = "$env:USERPROFILE\.3lc-kaggle-plugin\host"
   ```

   The worker reads it at start — if the service is already running, reload
   the plugin (or restart the service) after setting it.

2. **The 0-LOC copy** — put the two files where the worker already looks.
   For the redirected-home setup (worker home = `<hub-next>\home`):

   ```powershell
   New-Item -ItemType Directory -Force "<hub-next>\home\.3lc-kaggle-plugin\host" | Out-Null
   Copy-Item "$env:USERPROFILE\.3lc-kaggle-plugin\host\*" "<hub-next>\home\.3lc-kaggle-plugin\host\"
   ```

   No restart needed — the gate stats the files on every check.

## Appendix — machine also runs the 1.1.x Hub

Don't share state: the two stacks fight over `~/.3lc-compute/settings.json`
(the old service's writer silently drops the new one's keys). Run the 0.2.x
service with a redirected home (see `3lc-hub-next/PORT_PLAN.md` § switch
procedure in the research workspace) or on a different machine.

**Working-copy branch rule:** the 0.1.x service loads the plugin **live from
the repo working copy** (`plugin_dirs` points at `<repo>\src`), so that
checkout must be on `develop` (v1.1.x code) whenever the old service runs —
a working copy left on `port/0.2.x` breaks the old host at import. The 0.2.x
service is immune: it installs from the **git tag** into its own managed venv
and never reads the working copy.
