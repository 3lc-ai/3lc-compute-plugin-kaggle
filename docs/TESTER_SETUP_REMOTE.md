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

Prerequisites on the host: Python 3.12, `uv`, `git` (the repo is public, so
no GitHub token is needed), NVIDIA driver with CUDA ≥ 12.8 userspace
(`nvidia-smi`).

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

**Starter kit onto the host** (~625 MB; it must live on the host, that's
where Import reads it). **Use the plugin**: the Import tab's "Starter kit"
section has a **Download starter kit** button that fetches the kit from 3LC's
content network, verifies every file against a published manifest by checksum,
and fills the Dataset YAML path for you.

This is the one setup step that a remote host makes *easier* rather than
harder. The download runs in the plugin's worker, which lives on the **host**,
so the bytes go straight to the machine that needs them. Nothing travels
through your laptop, there is no scp, and there is no path to paste: a browser
sitting somewhere else changes none of it (docs/REMOTE_COMPUTE.md is the
browser-is-not-the-host audit). A dropped connection resumes from the finished
shards rather than restarting, which matters more on a remote link than a
local one.

Navigating away is safe. The job runs in the worker, not the browser, and the
section reattaches to a download in progress when you come back.

The kit lands in a versioned folder under `~/.3lc-kaggle-plugin/data/` on the
host; the section names the exact path. Leave it where it is — the Hub reads
your images from there for as long as the tables exist.

> The Kaggle **Data** tab does not carry the dataset. It holds the competition
> README and `sample_submission.csv`; the plugin is how you get the data.

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
UV_TORCH_BACKEND=auto \
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
