# 3LC Hub 0.2.x tester setup — creates the Hub venv, installs the PINNED
# stack this plugin was tested against, logs in, and starts both services.
# Windows PowerShell 5.1 compatible. Safe to re-run (idempotent installs).
#
#   powershell -ExecutionPolicy Bypass -File setup-0.2-tester.ps1 [-Root C:\3lc-hub-next]
#
# Prerequisites you must have first (the script checks and stops if missing):
#   * Python 3.12 on PATH        (winget install Python.Python.3.12)
#   * uv on PATH                 (winget install astral-sh.uv)  <- REQUIRED by the plugin shop
#   * git on PATH (the plugin repo is public; no GitHub token needed)
#   * An NVIDIA GPU + driver (CUDA >= 12.8 userspace)
#   * Your 3LC API key (dashboard -> account)

param(
    [string]$Root = "C:\3lc-hub-next"
)

$ErrorActionPreference = "Stop"

# Versions this plugin (v1.2.10) was tested against — do not float.
$TLC_CORE = "3lc==3.1.0"
$TLC_COMPUTE = "3lc-compute==0.2.1"
# The plugin version the catalog currently advertises — the single site the
# W1 env var's version segment derives from (RELEASING.md version-pin list).
$PLUGIN_VER = "1.2.10"
$INDEX_PRE = "https://pypi.3lc.ai/public/repositories/prereleases-public/"
$INDEX_REL = "https://pypi.3lc.ai/public/repositories/releases-public/"

foreach ($tool in @("python", "uv", "git")) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        Write-Error "$tool is not on PATH - see the prerequisites block at the top of this script."
    }
}

Write-Host "==> Creating $Root and the Hub venv (Python 3.12)"
New-Item -ItemType Directory -Force $Root | Out-Null
Set-Location $Root
uv venv --python 3.12 .venv
if ($LASTEXITCODE -ne 0) { Write-Error "uv venv failed" }

Write-Host "==> Installing the pinned 0.2.x Hub stack (this is the tested pairing)"
uv pip install --python .venv\Scripts\python.exe `
    --extra-index-url $INDEX_PRE --extra-index-url $INDEX_REL `
    --index-strategy unsafe-best-match `
    $TLC_COMPUTE $TLC_CORE
if ($LASTEXITCODE -ne 0) { Write-Error "Hub install failed" }

Write-Host "==> 3LC login (3lc core 3.x uses a NEW key store - even if you used 2.x before, log in again)"
& .venv\Scripts\3lc.exe login
if ($LASTEXITCODE -ne 0) { Write-Error "3lc login failed - check the API key" }

# ── Service environment ──────────────────────────────────────────────────
# W1 workaround: 3lc-compute 0.2.1 spawns plugin workers with the POSIX
# venv layout (<venv>/bin/python) on every OS - on Windows that path does
# not exist and every venv-plugin worker fails to start. The env var below
# is the documented per-plugin override; the path pre-states where the shop
# will materialize the plugin's venv (id kaggle-exdark, version 1.2.10 — must
# match the version the catalog currently advertises, see TESTER_SETUP_0.2 §2).
# Derivation rule (SDK worker_spec.py): TLC_COMPUTE_PLUGIN_VENV_ +
# id.upper().replace('-', '_').
$pluginRoot = Join-Path $env:USERPROFILE ".3lc-compute\managed-plugins\kaggle-exdark"
$managed = Join-Path $pluginRoot "$PLUGIN_VER\.venv\Scripts\python.exe"
$env:TLC_COMPUTE_PLUGIN_VENV_KAGGLE_EXDARK = $managed

# ── D4 preflight: the env var's VERSION SEGMENT must match the venv the
# shop actually uses. Two failure shapes, checked here because Test-Path
# alone cannot tell them apart:
#   * missing  - the pinned venv does not exist. Fine on a fresh machine
#     (the shop creates it at install; the env var pre-states the path),
#     wrong after an update - the Kaggle page then fails with the browser
#     error "Failed to load plugin: Internal Server Error".
#   * stale-but-existing - the pinned venv EXISTS (uninstall never removes
#     old venvs, bug W3) while a newer version is installed: the path check
#     passes and the worker silently runs the OLD plugin code.
Write-Host "==> Preflight: W1 env-var version pin vs plugin venvs on disk"
$onDisk = @()
if (Test-Path $pluginRoot) {
    $onDisk = @(Get-ChildItem $pluginRoot -Directory | ForEach-Object { $_.Name })
}
if ($onDisk.Count -eq 0) {
    Write-Host "    No plugin venv on disk yet - normal on a fresh machine. The shop creates"
    Write-Host "    $PLUGIN_VER\.venv at install; the env var pre-states that path."
} elseif ($onDisk -notcontains $PLUGIN_VER) {
    Write-Warning ("The env var pins version $PLUGIN_VER but the venv(s) on disk are: " + ($onDisk -join ', ') + ".")
    Write-Warning "The Kaggle page will fail with: Failed to load plugin: Internal Server Error"
    Write-Warning "Fix: set `$PLUGIN_VER at the top of this script to the installed version and re-run, or edit the env var in the compute-service window and restart it."
} else {
    $newer = @($onDisk | Where-Object { try { [version]$_ -gt [version]$PLUGIN_VER } catch { $false } })
    if ($newer.Count -gt 0) {
        Write-Warning ("Version $PLUGIN_VER exists on disk, but newer installed version(s) are present: " + ($newer -join ', ') + ".")
        Write-Warning "If the catalog installed an update, the env var now pins the STALE venv: the path exists, so nothing fails - the worker just runs the old plugin. Repoint `$PLUGIN_VER (or the env var) to the newest version."
    } else {
        Write-Host "    OK: the env var pins $PLUGIN_VER and that venv is the newest on disk."
    }
}

# CUDA torch for catalog installs: `uv pip install` does not read the
# plugin's own [tool.uv.index] config, so without this the worker venv gets
# CPU-only torch on Windows. UV_TORCH_BACKEND=auto makes uv detect the GPU
# driver and pick the matching torch wheel index itself (inherited by the
# shop's uv subprocess; no-op on machines without an NVIDIA GPU).
$env:UV_TORCH_BACKEND = "auto"

Write-Host "==> Starting the Object Service (window 1) and Compute Service (window 2)"
Start-Process powershell -ArgumentList "-NoExit", "-Command",
    "Set-Location '$Root'; .venv\Scripts\3lc.exe service"
Start-Process powershell -ArgumentList "-NoExit", "-Command",
    "Set-Location '$Root'; `$env:TLC_COMPUTE_PLUGIN_VENV_KAGGLE_EXDARK='$managed'; `$env:UV_TORCH_BACKEND='auto'; .venv\Scripts\3lc-compute.exe"

Write-Host ""
Write-Host "Done. Object Service -> http://localhost:5015, Compute Service -> http://localhost:5020."
Write-Host "Next: open the Hub in your browser, Settings -> Plugins -> Catalogs, add the catalog URL"
Write-Host "from docs/TESTER_SETUP_0.2.md, and Install 'Kaggle Competition' from the Available tab."
