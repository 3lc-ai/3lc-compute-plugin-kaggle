# Tester setup — remote compute host (Linux GPU box, browse from anywhere)

For testers whose GPU lives in a different machine than their browser — a
Linux GPU workstation or cloud box runs both 3LC services; you browse to it
from a Mac or any laptop. Validated surface notes are in
[REMOTE_COMPUTE.md](REMOTE_COMPUTE.md); the Windows single-machine path is
[TESTER_SETUP_0.2.md](TESTER_SETUP_0.2.md).

> **Reality check before you start:** the browser is a thin client here.
> Everything — dataset, training, prediction, Kaggle credentials, the CSV —
> lives on the **host**. The only things that cross the network are the Hub
> UI, the plugin page, and the Download CSV stream.

## 1. Host setup (Linux, NVIDIA GPU)

Prerequisites on the host: Python 3.12, `uv`, `git` (with a GitHub token
that can read the private repo: run
`git ls-remote https://github.com/3lc-ai/3lc-compute-plugin-kaggle.git`
once), NVIDIA driver with CUDA ≥ 12.8 userspace (`nvidia-smi`).

```bash
# Hub venv — the same pinned pairing as the Windows guide
uv venv --python 3.12 ~/3lc-hub-next/.venv
uv pip install --python ~/3lc-hub-next/.venv/bin/python \
  --extra-index-url https://pypi.3lc.ai/public/repositories/prereleases-public/ \
  --extra-index-url https://pypi.3lc.ai/public/repositories/releases-public/ \
  --index-strategy unsafe-best-match \
  "3lc-compute==0.2.1" "3lc==3.1.0"

# 3LC login ON THE HOST (3lc 3.x key store; paste your API key)
~/3lc-hub-next/.venv/bin/3lc login

# Kaggle token ON THE HOST (the compute host is what talks to Kaggle):
mkdir -p ~/.kaggle
printf '%s' "KGAT_<your token>" > ~/.kaggle/access_token
chmod 600 ~/.kaggle/access_token
# (printf, not echo — the file must have no trailing newline)
```

**Starter kit onto the host** (~616 MB; it must live on the host, that's
where Import reads it). Either push it from your laptop:

```bash
scp starter_kit.zip user@gpu-host:~/kits/
```

or pull it on the host from the competition's Data tab (needs the Kaggle
token above; the CLI resumes partial downloads):

```bash
~/path/to/venv/bin/kaggle competitions download -c <competition-slug> -p ~/kits/
```

then:

```bash
cd ~/kits && unzip starter_kit.zip -d starter_kit   # keep this folder permanent
```

The Import tab's "Dataset YAML path" is then the **host** path, e.g.
`/home/user/kits/starter_kit/dataset.yaml`.

> v1.2's planned auto-download/auto-slug will erase the scp/wget step and
> the manual path paste entirely — the plugin will pull the kit from Kaggle
> on the host by itself. The venv/login/token steps above survive that.

## 2. Expose the services / connect the browser

Bind both services to an address your browser can reach (LAN example;
for anything crossing the open internet put a VPN or SSH tunnel in front —
the services authenticate every request, but don't expose them naked):

```bash
# window/tmux pane 1 — Object Service on :5015
TLC_SERVICE_HOST=0.0.0.0 ~/3lc-hub-next/.venv/bin/3lc service
# (alternative documented tunnel: 3lc service --ngrok, needs NGROK_TOKEN)

# window/tmux pane 2 — Compute Service on :5020
TLC_COMPUTE_HOST=0.0.0.0 \
TLC_COMPUTE_PLUGIN_INDEX_URLS=https://download.pytorch.org/whl/cu128 \
~/3lc-hub-next/.venv/bin/3lc-compute
```

Notes:
- `TLC_COMPUTE_PLUGIN_VENV_KAGGLE_EXDARK` is **not needed on Linux** — the
  W1 interpreter-path bug is Windows-only.
- CORS is already `*` on the compute service; no config needed there.
- SSH-tunnel alternative when you can't open ports:
  `ssh -L 5015:localhost:5015 -L 5020:localhost:5020 user@gpu-host`,
  then browse `http://localhost:5015` on your laptop as if local.

Open the Hub from your laptop at `http://<gpu-host>:5015` (or
`http://localhost:5015` over the tunnel). The Hub's plugin pages talk to the
compute service at the URL the Hub is configured with — over a tunnel the
default localhost URLs just work; on a LAN address, check the Hub's service
settings point at `http://<gpu-host>:5020`.

## 3. Install the plugin + smoke test (same as local)

Catalog source, install, and the smoke path are identical to
[TESTER_SETUP_0.2.md](TESTER_SETUP_0.2.md) §3-4 — add the gist catalog URL,
install **Kaggle Competition** (id `kaggle-exdark`), first install builds
the worker venv with CUDA torch on the host.

Remote-specific expectations while running [SMOKE_TEST](../SMOKE_TEST.md):

- Import's YAML path = host path (the field says so).
- **Download CSV** works from your laptop — it streams over HTTP.
  Copy-path buttons copy *host* paths (tooltips say so); that's expected.
- Dashboard links open with `?object_service=...` appended so the
  dashboard talks to the right object service — if a dashboard opens but
  shows an empty project list, that parameter is missing (report it).
- Local mAP score: only if the organizer host-files are on the *compute
  host* — for testers, no score shown is correct.
