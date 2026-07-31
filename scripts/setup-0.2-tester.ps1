# 3LC Hub 0.2.x tester setup — creates the Hub venv, installs the PINNED
# stack this plugin was tested against, logs in, and starts both services.
# Windows PowerShell 5.1 compatible. Safe to re-run (idempotent installs).
#
#   powershell -ExecutionPolicy Bypass -File setup-0.2-tester.ps1 [-Root C:\3lc-hub-next]
#
# Prerequisites you must have first (the script checks and stops if missing):
#   * Python 3.12 on PATH        (winget install Python.Python.3.12)
#   * uv on PATH                 (winget install astral-sh.uv)  <- REQUIRED by the plugin shop
#   * git on PATH + GitHub access to 3lc-ai (private repo; sign in once so
#     Git Credential Manager has a token: `git ls-remote https://github.com/3lc-ai/3lc-compute-plugin-kaggle.git`)
#   * An NVIDIA GPU + driver (CUDA >= 12.8 userspace)
#   * Your 3LC API key (dashboard -> account)

param(
    [string]$Root = "C:\3lc-hub-next"
)

$ErrorActionPreference = "Stop"

# Versions this plugin (v1.2.0) was tested against — do not float.
$TLC_CORE = "3lc==3.1.0"
$TLC_COMPUTE = "3lc-compute==0.2.1"
$INDEX_PRE = "https://pypi.3lc.ai/public/repositories/prereleases-public/"
$INDEX_REL = "https://pypi.3lc.ai/public/repositories/releases-public/"
$TORCH_CU128 = "https://download.pytorch.org/whl/cu128"

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
# will materialize the kaggle plugin's venv (version 1.2.0).
$managed = Join-Path $env:USERPROFILE ".3lc-compute\managed-plugins\kaggle\1.2.0\.venv\Scripts\python.exe"
$env:TLC_COMPUTE_PLUGIN_VENV_KAGGLE = $managed

# CUDA torch for catalog installs: `uv pip install` does not read the
# plugin's own [tool.uv.index] config, so without this the worker venv gets
# CPU-only torch on Windows. Passed to every shop install as an extra index.
$env:TLC_COMPUTE_PLUGIN_INDEX_URLS = $TORCH_CU128

Write-Host "==> Starting the Object Service (window 1) and Compute Service (window 2)"
Start-Process powershell -ArgumentList "-NoExit", "-Command",
    "Set-Location '$Root'; .venv\Scripts\3lc.exe service"
Start-Process powershell -ArgumentList "-NoExit", "-Command",
    "Set-Location '$Root'; `$env:TLC_COMPUTE_PLUGIN_VENV_KAGGLE='$managed'; `$env:TLC_COMPUTE_PLUGIN_INDEX_URLS='$TORCH_CU128'; .venv\Scripts\3lc-compute.exe"

Write-Host ""
Write-Host "Done. Object Service -> http://localhost:5015, Compute Service -> http://localhost:5020."
Write-Host "Next: open the Hub in your browser, Settings -> Plugins -> Catalogs, add the catalog URL"
Write-Host "from docs/TESTER_SETUP_0.2.md, and Install 'Kaggle Competition' from the Available tab."
