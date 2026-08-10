# Remote-compute audit — browser and services on different machines

Audited 2026-08-04 against plugin v1.2.1 + `3lc-compute 0.2.1` + `3lc 3.1.0`.
Scenario: **compute service (and object service) on a remote Linux GPU box;
the user browses from a Mac or a GPU-less laptop.** Setup steps for this
scenario live in [TESTER_SETUP_REMOTE.md](TESTER_SETUP_REMOTE.md); this file
is the audit of every browser==host assumption in the plugin, with a verdict
per surface.

## How the pieces talk (verified in the 0.2.1 source)

- The compute service binds `127.0.0.1:5020` by default; `--host 0.0.0.0` or
  `TLC_COMPUTE_HOST=0.0.0.0` exposes it (`tlc_compute/config.py`,
  `app.py`). The object service equivalents are `3lc service --host` /
  `TLC_SERVICE_HOST`, default `127.0.0.1:5015`; `3lc service --ngrok` is the
  documented tunnel path.
- CORS is `*` and **not configurable** (`config.py: cors_origins = ("*",)`),
  for both HTTP and SocketIO — cross-origin browsing is not the blocker,
  bind address is. Auth (JWT/HMAC) still applies to every request.
- The plugin fragment reaches its backend exclusively through
  `PLUGIN_API.getConfig('compute_service_url')` + relative routes — nothing
  in the plugin hardcodes a host or port.
- Dashboard deep links must carry `?object_service=<url>` or the dashboard
  silently falls back to its own `localhost:5015` — the plugin appends it
  everywhere as of v1.2.1 (`kgWithObjectService`).

## Verdicts

### Works remotely (no change needed)

| Surface | Why it works |
|---|---|
| All tab fetches, job start/poll/cancel | relative routes over `compute_service_url`; host proxies to the worker |
| **Download CSV** | `GET /submissions/{job}/download` streams the file bytes over HTTP (`Response(content=read_bytes())`) — never a client-side path reference |
| Dashboard links (Explore, Open Run, Loop inspect/fix-labels, Status run cell) | all append `object_service=` as of v1.2.1 |
| Kaggle credentials | read by the `kaggle` package **on the compute host** (`~/.kaggle/access_token` there); the browser never touches them. Doc'd in the remote guide |
| Checkpoint cache | `~/.3lc-kaggle-plugin/checkpoints` on the host, fetched inside the train job |
| Config store / job store / predict-submit snapshots | host-side JSON, served over routes |
| `?kgdev` fixtures | static, no fetches |
| Copy-diagnostics builder | assembles strings from route responses only |
| Local scoring / `is_host` gate | consistent: files under the host's `~/.3lc-kaggle-plugin/host/` gate host-only UI for whoever browses that service — correct, since predictions and scoring happen there |

### Works but was confusing (labeled in v1.2.1)

| Surface | Confusion | v1.2.1 change |
|---|---|---|
| Import "Dataset YAML path" | it's a **host** filesystem path; a remote browser's local path can't work | form-help under the field says the kit must be on the service's machine |
| Weights path (host-only source) | same | callout notes it's a host path |
| Copy-path buttons (table URL, weights, CSV) | copied paths are host paths | tooltips say so; CSV tooltip points at Download CSV as the remote-safe action |

### Broken remotely — small, fixed

None found beyond the dashboard-link parameter, which was fixed as part of
Part 1 (`kgWithObjectService` on every outbound link). Download CSV already
streamed. No hardcoded `localhost` exists in the plugin's shipped code.

### Broken / not supported remotely — big, out of plugin scope

| Gap | Detail |
|---|---|
| No file upload for the starter kit | the kit must be placed on the host via scp/wget — v1.2's planned auto-download-from-Kaggle erases this step entirely |
| Hub frontend's compute-URL discovery | whether the Hub UI can be pointed at a remote compute service is a frontend/config concern, not something the plugin can influence; the remote guide documents the pattern that works today |
| Worker sockets are loopback-only | SDK design (worker is spawned by the host on the same machine) — irrelevant to users, noted for completeness |
| `remote_url` worker seam | the SDK has a wired-but-unreachable remote-worker endpoint (`WorkerSpec.remote_url`); nothing sets it in 0.2.1 — not a supported pattern, do not document it for testers |

## Env vars that matter on a remote Linux host

- `TLC_COMPUTE_HOST=0.0.0.0`, `TLC_COMPUTE_PORT=5020`
- `TLC_SERVICE_HOST=0.0.0.0` (or `3lc service --host 0.0.0.0`), port 5015
- `TLC_COMPUTE_PLUGIN_VENV_KAGGLE_EXDARK` is **not needed on Linux** — the
  POSIX `<venv>/bin/python` layout the 0.2.1 spawner assumes is the real
  layout there (W1 is Windows-only)
- `UV_TORCH_BACKEND=auto` still required for CUDA torch in shop installs
  (uv detects the box's NVIDIA driver and picks the matching CUDA wheel
  index; supersedes the old `TLC_COMPUTE_PLUGIN_INDEX_URLS` cu128 pin)
