# Design notes — 3LC Kaggle competition compute plugin

Research date: 2026-07-20. Sources: local clones under `plugin-research/` of
`3lc-compute-plugin-sdk`, `-template`, `-example` (Mission Control), `-yolo` (HEAD `7cf3149`,
v0.1.3), `-sam3`, and the umbrella `3lc-compute-plugins`, plus the **installed** Hub
(`3lc_compute` 0.1.1.47 in `3lc-hub\.venv`). File:line citations are relative to each repo's
root. The SDK's `docs/plugin-guide.md` is the canonical author guide; the SDK repo's
`CLAUDE.md` is the agent-facing condensed version.

> **Headline caveat (read first).** The reference repos document a **new catalog-based,
> venv-isolated plugin host** (SDK contract 0.1). The Hub we actually run locally
> (`3lc-compute` **0.1.1.47**, part of the 3lc 2.22.3 install) implements an **older
> directory-import architecture**: external plugins are added to `sys.path` and imported
> **in-process into the host venv** (`tlc_compute/plugins/external_loader.py:143-272`), there
> is **no catalog endpoint, no venv provisioning, no git install** — the catalog/repository
> fields exist only as placeholders marked *"not yet built"*
> (`tlc_compute/plugins/base.py:52-63`).
> **[UNKNOWN — verify with Hub team]** which host version the competition Hub will run, and
> whether the new venv/catalog host ships before our launch. Everything below documents the
> new contract (what we should build against), with "installed-Hub reality" notes where they
> differ.

---

## 1. Plugin anatomy

### 1.1 The manifest

All metadata lives in a `plugin.toml` next to the package `__init__.py`, read by the host
**without importing** the plugin. `read_manifest()` also accepts an equivalent
`[tool.tlc-compute]` table inside `pyproject.toml`, but checks `plugin.toml` first
(sdk `docs/plugin-guide.md:93-97`) — every first-party plugin uses the standalone
`plugin.toml`. The fully annotated exemplar is
`3lc-compute-plugin-example/src/tlc_plugin_example/plugin.toml:1-47`.

Surface:

- **Top level**: `id` (URL-safe slug; also the default SocketIO namespace `/<id>`), `name`,
  `description`, `version` (SemVer), `icon` (emoji), `icon_svg` (inline 16×16 SVG),
  `min_service_version`, optional `max_service_version` / `min_frontend_version`,
  `repository_url`. Catalog-signaling fields (`update_available`, `changelog_url`,
  `upgrade_required`) are host-populated, left empty by the plugin (guide `:831-839`).
- **`[ui]`**: `display_mode` = `sidebar` | `action` | `hidden`; `section` (sidebar group);
  `priority`; `compatible_with` (`["table"]`/`["run"]`); action-mode fields `input_types`,
  `min_input_count`, `action_param_names`, `output_types`; dashboard `quick_action` +
  `quick_action_label`/`_description`.
- **`[runtime]`**: `isolation` = `venv` (own uv-managed venv, out-of-process worker over a
  UDS — the default for new plugins) | `host` (imported in-process; deps must be a subset of
  the service); `entrypoint = "pkg.module:ClassName"`; `provision_extra` (**required** for
  venv — host runs `uv sync --extra <this>`, guide `:140-143`); `requires_gpu` (true routes
  jobs through the shared GPU queue, one GPU job at a time across all plugins); optional
  `training = true` (informational, marks training-style jobs — yolo sets it,
  `3lc-compute-plugin-yolo/src/tlc_plugin_yolo/plugin.toml:31`); optional `venv_python`,
  `socketio_namespace` (only to override the `/<id>` default), and `auth_exempt_paths`
  (routes served without the `Authorization` header, e.g. `<img>` sources — example
  `plugin.toml:43-46`).

### 1.2 The `ComputePlugin` contract

`tlc_plugin_sdk/contract.py` — an ABC with **two abstract methods** and no metadata:

- `get_ui_fragment() -> str` (`contract.py:51-54`) — the self-contained HTML+CSS+JS fragment
  (typically read from `ui.html` and cached).
- `compute(params: dict) -> dict` (`contract.py:56-59`) — handles the generic
  `GET /api/plugins/{id}/compute`.
- Optional no-op/default hooks: `initialise_runtime()` / `shutdown_runtime()`
  (`contract.py:63-74`), `run_job(ctx)` (`contract.py:76-89`, raises `NotImplementedError`
  unless overridden), `get_route_handlers()` (`contract.py:95-108`, relative Litestar
  handlers served under `/api/plugins/{id}/…`; the reserved routes `/run`, `/health`, `/ui`,
  `/compute`, `/jobs/*` are host-owned and must not be defined).
- `id` is **stamped onto the instance by the host** from the manifest; there is no
  `register()` call and no `get_active_jobs`/`cancel_job` — job listing and cancellation are
  host-owned (`contract.py:91-93`).

### 1.3 How config fields and panels are declared

There is **no declarative form schema in the contract** — a plugin's panels and fields are
hand-written HTML in `ui.html`, using shared CSS classes (`.plugin-page-narrow`,
`.plugin-hero`, `.card`, `.plugin-param-group`, `.plugin-form-grid`, `.plugin-action-bar`;
guide `:599-736`). "Select vs free-text" is literally `<select>` vs `<input>` in the
fragment.

The **yolo plugin adds its own server-driven field schema on top**: the model registry
returns param descriptors and the UI renders them generically:

- Field descriptors live in `models/yolo.py get_params()` — e.g. the checkpoint field
  `{"id": "model", "label": "Checkpoint", "type": "select", "default": "yolov8n.pt",
  "options": [...], "group": "YOLO Settings"}` (`models/yolo.py:40-87`) and
  `{"id": "imgsz", "type": "number", "default": 640, "min": 32, "max": 1280, "step": 32}`
  (`models/yolo.py:108-117`). Supported descriptor types render as `<select>` (from
  `options`), number inputs, and checkboxes.
- The UI fetches them via `GET /api/plugins/yolo/models/{name}/params` and renders in
  `trRenderParamFields` — selects at `ui.html:835-846` (with per-option task filtering at
  `ui.html:840`), numbers at `ui.html:847-854`.

This registry-driven pattern is worth copying for our Train panel: field definitions live in
Python, the JS renders whatever it's given.

### 1.4 Exact fork points in the yolo training form (lock model + imgsz)

Two distinct "model" selectors exist — don't confuse them:

- `#tr-model-select` (`ui.html:157-160`) picks the *registry implementation* (`"yolov8"`),
  populated from `GET /models` (`ui.html:736-743`). Leave this alone.
- The **checkpoint field** (`id="model"`) is the one with `yolo11n.pt`-style choices —
  declared server-side at **`models/yolo.py:40-87`** (options list `:45-83`, all `.pt`,
  default `"yolov8n.pt"` at `:44`).

Value flow: rendered field → `trCollectFormData()` gathers every `[data-param-id]` element
into `params` (`ui.html:635-673`; `params["model"]`/`params["imgsz"]` collected at
`ui.html:637-641`) → the whole form is saved as a *project* via `POST /projects`
(`ui.html:1137`; stored verbatim, **no validation**, `routes.py:97`) → run starts with just
`{project_id}` posted to `/api/plugins/yolo/run` (`ui.html:1145`) → `run_job` re-reads
`project.params` untouched (`__init__.py:149`) → consumed with fallback defaults at
**`models/yolo.py:333`** (`model_name = params.get("model", "yolov8n.pt")` → `YOLO(model_name,
task=...)` at `:439`) and **`:336`** (`imgsz = int(params.get("imgsz", 640))` →
`train_kwargs["imgsz"]` at `:527`); the metrics-collection path repeats both at `:611`/`:613`.

**To lock model = `yolo11n.yaml` (from-scratch) and imgsz = 640 in our fork:**

1. In the field declaration `models/yolo.py:40-87`: single option
   `{"value": "yolo11n.yaml", "label": "YOLOv11n (from scratch)"}` and
   `"default": "yolo11n.yaml"`; for imgsz (`:108-117`) set `min = max = 640` (default is
   already 640) — or drop both fields from `get_params()` entirely and render them as static
   text in the UI.
2. Hard backend guarantee (survives stale saved projects and hand-crafted API calls):
   overwrite at the consumption points — `model_name = "yolo11n.yaml"` at `yolo.py:333`/`:611`
   and `imgsz = 640` at `yolo.py:336`/`:613`.
3. Also neutralize `pretrained_model_url`, which **overrides** the model when set
   (`yolo.py:424-435`, collect-path `:659-670`) — remove the form field
   (collected at `ui.html:654-658`) or ignore the param in `train()`.

Note on "checkpoint-only": nothing in plugin code rejects `.yaml` — `validate_params` is a
no-op and never called (`models/base.py:54-56`), and the value goes straight into
`YOLO(model_name)` (`yolo.py:439`), which ultralytics builds from scratch for `.yaml`. The
limitation we observed (2026-07-15) is purely that the dropdown offers no `.yaml` option,
plus whatever the provisioned `3lc-ultralytics` version (`pyproject.toml:32`,
`>=0.3.3`) does at construction time. **[UNKNOWN — verify with Hub team]** that the
`3lc-ultralytics` resolved in the plugin venv supports `.yaml` from-scratch construction
end-to-end (our earlier finding was that installed 0.1.1.47 and repo 0.1.3 both *present*
checkpoint-only UIs; the code path itself is open).

---

## 2. Job model

### 2.1 `JobContext`

`tlc_plugin_sdk/job_context.py` — stdlib-only, identical surface in host and venv modes
(only the event sink and cancel signal differ, `job_context.py:3-16`):

| Member | Purpose |
|---|---|
| `ctx.job_id` / `ctx.params` | Job id; parsed request body of `POST /api/plugins/{id}/run`. |
| `ctx.state_dir` | Writable per-plugin scratch dir that survives venv reinstall/reload (`:35-36`) — never write inside the package. In venv mode it's `state_root/<job_id>` (`worker.py:72-74`). |
| `ctx.cancelled` | `True` once cancel requested — poll at checkpoints (`:58-61`). |
| `ctx.progress(percent=…, label=…, timing=…)` | Generic progress bar; `percent=-1` = indeterminate; `timing = {elapsed_s, eta_s, avg_step_s, step_label}` (`:63-65`). |
| `ctx.metric(label, value)` | Scalar key/value card on the generic panel (`:67-69`). |
| `ctx.log(message)` | Log line (`:71-73`). |
| `ctx.result(run_url=…)` | The one canonical "open result" link; last write wins (`:75-87`). |
| `ctx.emit(name, payload)` | Custom event relayed verbatim on the plugin's SocketIO namespace for the plugin's OWN rich UI; `job_update` is reserved and rejected (`:89-111`). |

### 2.2 How a long-running training job reports into the Hub UI

The host owns the whole lifecycle: `POST /api/plugins/{id}/run` → host queues (GPU jobs
serialized across all plugins when `requires_gpu = true`) → calls `run_job(ctx)` (in-process,
or in the venv worker where `POST /jobs/{job_id}/run` streams NDJSON events back —
`worker.py:18-21`). Every job broadcasts a generic `job_update` SocketIO event on `/<id>`
with the plugin-agnostic schema (`status`, `progress.{percent,label,timing}`, `run_url`,
`metrics[]`), which feeds both the generic Queue & Progress panel
(`GET /api/plugins/jobs`) and the plugin's own UI.

Browser side, the SDK ships `window.PluginJobs` (inject `job_tracker_script()` from
`tlc_plugin_sdk.shared.job_tracker` via `inject_scripts()`): `PluginJobs.run(id, params,
{onUpdate, onDone, onError})` starts the job and pre-subscribes so a fast-finishing job
still delivers its terminal event (guide `:544-575`).

How yolo actually does it (the pattern to copy for Train):

- Per-epoch/batch telemetry rides `ctx.emit`: `ctx.emit("epoch_progress", {job_id, epoch,
  total_epochs, metrics, timing})` (`__init__.py:205-214`), lifecycle via
  `ctx.emit("job_status"| "job_completed" | "job_failed", …)` (`__init__.py:119, 299-307,
  313`). Final metrics ride the `job_completed` emit, deliberately **not** `ctx.metric`
  (`__init__.py:296-297`) — training fields never leak into the generic schema (guide
  `:592-595`).
- The generic panel is fed in parallel via `ctx.progress(percent, label, timing)`
  (`__init__.py:224, 236-240, 298`) and `ctx.log` (`:132, 243`).
- The bridge from ultralytics: `run_job` passes an `on_epoch` callback into the model;
  ultralytics callbacks (`on_train_batch_end`, `on_fit_epoch_end`, registered at
  `models/yolo.py:516-519`) call it with train losses / val metrics
  (`yolo.py:470-482, 484-514`).

### 2.3 Cancellation

Host-owned endpoint: `POST /api/plugins/jobs/{job_id}/cancel` (venv worker:
`POST /jobs/{job_id}/cancel`, `worker.py:21`). It just sets the cancel event; the plugin
cancels **cooperatively** by polling `ctx.cancelled`. Yolo bridges it as
`is_cancelled = lambda: ctx.cancelled` (`__init__.py:254-255`) and every ultralytics
callback checks it and sets `trainer.stop = True` (`yolo.py:465-467, 470-476, 484-493` —
the fit-epoch-end variant also disables 3LC collection before final eval); after training
returns, `run_job` marks the 3LC run cancelled (`__init__.py:279-286`). Don't `async`-def
`run_job`; it runs synchronously on a worker thread (SDK `CLAUDE.md`).

---

## 3. Venv isolation & where the `kaggle` package goes

Per-plugin dependencies are declared as an **extra in the plugin repo's own
`pyproject.toml`**, never in base deps:

- Base `dependencies` = the SDK floor only, e.g. yolo:
  `3lc-compute-plugin-sdk[shared]>=0.1.0,<0.2.0` (`3lc-compute-plugin-yolo/pyproject.toml:23-25`).
- The heavy stack goes under `[project.optional-dependencies]` in the extra named by the
  manifest's `provision_extra` — yolo's `[yolo]` extra carries `3lc-ultralytics>=0.3.3`,
  `torch`, `torchvision`, `3lc[pacmap,umap]>=3.0.0,<4.0.0` (`pyproject.toml:30-40`).
- Provisioning: the host materializes the plugin's own uv-managed venv with
  `uv sync --extra <provision_extra>` against the repo (template `README.md:70-71`), then
  runs the worker out-of-process:
  `python -m tlc_plugin_sdk.worker --entry pkg:Class --socket …` (`worker.py:5-11`).
- Index plumbing: `[[tool.uv.index]]` entries for `3lc-releases` / `3lc-prereleases`
  (`https://pypi.3lc.ai/public/repositories/{releases,prereleases}-public`, both
  `explicit = true`) and `[tool.uv.sources]` pins (`3lc` → releases,
  `3lc-compute-plugin-sdk` → prereleases; torch → the pytorch index with platform markers)
  — yolo `pyproject.toml:54-77`, template `:48-65`. Never commit a relative `path=` source
  (breaks remote consumers; template `:60-63`).
- An entry point advertises the package:
  `[project.entry-points."tlc_compute.plugins"] kaggle = "tlc_plugin_kaggle"`
  (template `:39-40`) — the installed-package discovery path; folder-source scanning is the
  primary dev path.

**So the `kaggle` pip package (and our pinned torch/`3lc-ultralytics` stack) goes in our
plugin's extra** — e.g. `kaggle = ["kaggle>=1.6", "3lc-ultralytics>=0.3.3", …]` — and lands
only in the plugin's provisioned venv, never the host venv.

> **Installed-Hub reality:** 0.1.1.47 has **no venv provisioning** — external plugin dirs
> are imported in-process and missing deps produce a "pip install into the host venv"
> instruction (`tlc_compute/plugins/external_loader.py:236-241`). If we must ship on
> 0.1.1.x, our deps have to coexist with the host venv (they largely do — the host already
> runs ultralytics + torch cu128 for its built-in yolo plugin, and `kaggle` is a light pure-
> Python client). **[UNKNOWN — verify with Hub team]** whether we target the old in-process
> host or a new venv-capable host build.

Kaggle credentials: the `kaggle` client reads `~/.kaggle/kaggle.json` or
`KAGGLE_USERNAME`/`KAGGLE_KEY` env vars. In venv mode the worker inherits the host
environment; credentials should be a setup step on the Hub machine, with `ctx.state_dir`
(or a config-store entry, see §5) holding per-competition settings — never inside the
package dir.

---

## 4. Deployment — catalog.json and the private-repo question

### 4.1 Catalog schema and registration

`catalog.json` is a static "shop listing" committed at the repo root
(template `catalog.json:1-34`, example `catalog.json:1-40`):

```json
{
  "schema_version": 1,
  "generated_at": "",
  "plugins": [{
    "id": "<plugin-id>",
    "versions": [{
      "version": "0.1.0",
      "source": "<dist>[<extra>] @ git+https://github.com/<owner>/<repo>.git@<ref>",
      "wheel_url": "",
      "manifest": { …raw inline copy of plugin.toml… }
    }]
  }]
}
```

- `source` is a **PEP 508 requirement with a git URL** — installing resolves the repo at
  `<ref>` and `uv sync`s the named extra; no wheel publishing needed (template
  `README.md:118-125`). `wheel_url` is the alternative (unused so far).
- The inline `manifest` copy lets the Hub render an install card and gate
  `min_service_version` compatibility **without downloading anything**.
- Registration: hand the Hub the **raw URL** of the file —
  `POST /api/admin/plugins/catalogs` with
  `{"url": "https://raw.githubusercontent.com/<owner>/<repo>/<branch>/catalog.json",
  "persist": true}` (template `README.md:128-131`), or paste the URL into the Hub's Plugins
  page. Installing "materializes a managed venv from the git source and registers the
  plugin live" (example `README.md:98-99`). The yolo README also lists two non-catalog
  Sources: a pip index requirement (`3lc-compute-plugin-yolo[yolo]==<ver>`) and a
  `github:3lc-ai/3lc-compute-plugin-yolo@v<ver>` shorthand.

### 4.2 Private repos — the key unknown

Dug hard; conclusion: **there is no private-repo authentication mechanism anywhere today.**

- **No precedent in the reference repos**: every `source` is a public
  `git+https://github.com/3lc-ai/…` ref; no design field carries a token; searches for
  `Authorization|GITHUB_TOKEN|netrc|Bearer|PAT|credential|gh auth` across all six repos hit
  only (a) the browser↔host data-plane auth (`PLUGIN_API.authFetch`, `auth_exempt_paths`)
  and (b) CI *publish* credentials (`CLOUDREPO_USERNAME/PASSWORD` for `uv publish` to
  `pypi.3lc.ai` in the release workflows) — neither touches catalog reads or plugin installs.
- **No implementation in the installed Hub at all**: `grep catalog` over installed
  `tlc_compute` 0.1.1.47 → zero files. Admin routes cover only plugin *directories*
  (`GET/POST/DELETE /api/admin/plugins/dirs`, `/dirs/reload`, `/{id}/reload`, `/unload`,
  `/scan` — `tlc_compute/routes/plugins.py:181-503`); there is no `/catalogs` route. The
  repository system is literally commented "not yet built"
  (`tlc_compute/plugins/base.py:52`).
- **What would apply if/when the new host lands**: both fetch steps are standard tooling —
  the catalog fetch is a plain HTTP GET of a raw URL, and the install shells out to
  uv/git for the `git+https` source. So the *plausible* private-repo paths are the tools'
  own credential resolution: a PAT embedded in the URLs
  (`https://<token>@raw.githubusercontent.com/…`, `git+https://<token>@github.com/…` — works
  but bakes a secret into a JSON file/catalog entry), `~/.netrc`, a git credential helper /
  `gh auth` on the Hub machine, or `GIT_*`/`UV_INDEX_*` env vars for the worker process.
  Nothing configures, documents, or injects any of these. **[UNKNOWN — verify with Hub
  team]:** (1) does the catalog fetcher pass an `Authorization` header or support
  authenticated raw URLs; (2) does the installer inherit the service user's git credential
  helper; (3) is there a supported private-plugin story planned, or should our repo's
  catalog install assume a public repo / public wheel on `pypi.3lc.ai`?
- **Pragmatic fallback that works on every host version, private repo included**: skip the
  catalog. We clone `3lc-compute-plugin-kaggle` ourselves (our `gh` auth handles private
  access) and register it as a **folder source**: `3lc-compute --plugin-dir <repo>/src` /
  `TLC_COMPUTE_EXTERNAL_PLUGIN_DIRS` (new host), or `POST /api/admin/plugins/dirs`
  (installed 0.1.1.47, persisted in `~/.3lc-compute/settings.json` under `plugin_dirs`,
  `tlc_compute/persistent_settings.py:38-50`). Auth then lives entirely in our git clone
  step, outside the Hub. This is the recommended deployment for the competition machine.

---

## 5. Multi-panel structure — the sam3 pattern → our four panels

How sam3 structures "Setup & Preview" / "Create & Run" (842-line single `ui.html`):

- **Not tabs — one scrolling page of sequential cards.** The hero renders a static two-step
  workflow indicator (`ui.html:61-64`); step 1 is a two-column grid (`.sam3-layout`,
  `ui.html:19-24`) of a Setup card (`:91-166`) + Preview viewer card (`:169-194`); step 2 is
  a full-width Create & Run card (`:197-251`) plus Progress (`:257-276`) and Log (`:279-286`)
  cards. There is **no panel-switching JS and no dynamic `active` class** — numbered
  `plugin-section-number` badges are cosmetic; both "steps" are live simultaneously. The
  only show/hide is field-level (e.g. folder-vs-table source toggle, `ui.html:412-416`).
- **State between panels**: shared DOM + a handful of JS module vars (`ui.html:291-311`);
  step 2's submit re-reads the same form fields step 1 used — no hand-off object. Whole-form
  snapshots persist server-side via the shared `PluginConfigStore`
  (`config_store.py:18-46`; CRUD routes `routes.py:107-150`), last-selected config id in
  `localStorage` (`ui.html:298`). Job state is host-owned; the UI keeps only the `job_id`.
- **Fast-vs-slow split**: preview and helpers are synchronous custom routes
  (`POST /preview` on one image, `/list-images`, `/read-labels`, HF-token routes —
  `routes.py:37-103`, all `sync_to_thread=True`); the long run goes through the generic
  `POST /api/plugins/sam3/run` and `run_job` **dispatches on a `mode` param**
  (`"create_and_predict"` → chains create-table then predict, `__init__.py:61-113`).
  Deliberately no custom `/run` route so nothing shadows the host's (`routes.py:3-12`).
  Live progress arrives via SocketIO (`sam3_log`/`sam3_progress` emits, `__init__.py:108,
  118, 271-281`; consumed `ui.html:789-811`).

**Mapping to Import / Train / Predict+Submit / Status:**

| Panel | Shape | Backend |
|---|---|---|
| 1. Import | Card: competition slug, data checks, "Import" button | `run_job(mode="import")` — kaggle download + `Table.from_yolo`; fast helpers as custom routes (`GET /competition-status`, `POST /validate-slug`) |
| 2. Train | Card: locked model/imgsz shown as static text, epochs/batch as fields | `run_job(mode="train")` — forked yolo trainer (§1.4), `epoch_progress` emits |
| 3. Predict + Submit | Card: checkpoint picker (from run), confidence, "Predict & Submit" | `run_job(mode="predict_submit")` — inference → `solution.csv`-format predictions → kaggle submit; a sync `POST /dry-run-format-check` custom route for validation |
| 4. Status | Progress + Log + submissions cards | No job of its own: `job_update` via `PluginJobs.track` + custom emits; `GET /submissions` custom route polling the Kaggle API |

Follow sam3: one scrolling `ui.html`, numbered section cards, single `run_job` dispatching
on `ctx.params["mode"]`, config persistence via `PluginConfigStore`, all long work through
the generic `/run`. Gate later panels client-side (disable Train card until an import job
has completed) — sam3 doesn't do step-gating, so this is our own JS, not a host feature.

---

## 6. Dev loop against the live local Hub (5015/5020)

1. **Register the working copy as a folder source** (once):
   - New host: `3lc-compute --plugin-dir "…\3lc-compute-plugin-kaggle\src"` or the
     `TLC_COMPUTE_EXTERNAL_PLUGIN_DIRS` env var (template `README.md:64-68`).
   - Installed 0.1.1.47: `POST http://localhost:5020/api/admin/plugins/dirs` with the
     directory (persist option available), or restart with the flag.
2. **Iterate**: edit files, then hot-reload **without restarting the service**:
   - Per plugin: `curl -X POST http://localhost:5020/api/admin/plugins/kaggle/reload` —
     purges the plugin's modules from `sys.modules`, re-imports, re-initialises the runtime,
     clears the UI cache; running jobs in other plugins are unaffected (guide `:739-757`).
     Exists on the installed Hub too (`tlc_compute/routes/plugins.py`).
   - Whole dir (re-provisions venvs when deps changed, new host):
     `curl -X POST http://localhost:5020/api/admin/plugins/dirs/reload -H 'Content-Type:
     application/json' -d '{"directory": "…/src"}'` (template `README.md:83-88`).
   - `POST /api/admin/plugins/{id}/unload` to remove.
3. **No Hub needed for API smoke tests**: `curl localhost:5020/api/plugins/manifest/kaggle`,
   `…/kaggle/compute`, and `curl -N -X POST …/kaggle/run -d '{…}'` streams job events
   (example `README.md:36-43`).
4. Object Service on 5015 is never touched directly — all data access goes through the
   compute service's server-side `tlc` (guide `:19`).
5. Editor DX: copy the template's `jsconfig.json`; after `uv sync` the SDK wheel's
   `plugin-api.d.ts` gives typed `window.PLUGIN_API`/`PluginJobs` autocompletion inside
   `ui.html` (template `README.md:104-110`). Lint: `uvx --from 'ruff>=0.15,<0.16' ruff
   check .`.

---

## 7. Proposed repo skeleton + draft manifest

Modeled on the template (instantiated shape) + yolo (trainer) + sam3 (multi-step UI):

```
3lc-compute-plugin-kaggle/
├── pyproject.toml            # dist "3lc-compute-plugin-kaggle"; [kaggle] extra; entry point
├── catalog.json              # shop listing (source → this repo; see §4 caveat on private)
├── jsconfig.json             # typed PLUGIN_API in ui.html (copy from template)
├── docs/
│   └── design-notes.md       # this file
└── src/
    └── tlc_plugin_kaggle/
        ├── plugin.toml       # manifest (below)
        ├── __init__.py       # KagglePlugin(ComputePlugin): get_ui_fragment, compute,
        │                     #   run_job(ctx) dispatching on params["mode"]
        ├── ui.html           # one page, four numbered cards (Import/Train/Predict+Submit/Status)
        ├── routes.py         # config CRUD + sync helpers: /competition-status, /validate-slug,
        │                     #   /submissions, /dry-run-format-check
        ├── importer.py       # mode="import": kaggle download → YOLO layout → tlc tables
        ├── trainer.py        # mode="train": forked yolo trainer, model/imgsz locked (§1.4)
        ├── submitter.py      # mode="predict_submit": predict → csv → kaggle submit
        └── config_store.py   # PluginConfigStore-backed competition config (slug, paths)
```

Draft `src/tlc_plugin_kaggle/plugin.toml`:

```toml
id = "kaggle"
name = "Kaggle Competition"
description = "End-to-end Kaggle competition workflow: import the dataset, train the fixed baseline (YOLOv11n from scratch @ 640), predict and submit."
version = "0.1.0"
min_service_version = "0.1.0"
icon = "🏁"
icon_svg = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M3 14V2.5"/><path d="M3 3h9l-2 2.5L12 8H3"/></svg>'
repository_url = "https://github.com/3lc-ai/3lc-compute-plugin-kaggle"

[ui]
display_mode = "sidebar"
section = "AI Tools"
priority = 40
compatible_with = ["table"]
output_types = ["run"]
quick_action = true
quick_action_label = "Run a Kaggle Competition"
quick_action_description = "Import, train the fixed baseline, and submit to Kaggle"

[runtime]
isolation = "venv"
entrypoint = "tlc_plugin_kaggle:KagglePlugin"
provision_extra = "kaggle"
requires_gpu = true
training = true
```

Draft `pyproject.toml` essentials (full index/source plumbing copied from yolo's
`pyproject.toml:54-77`):

```toml
[project]
name = "3lc-compute-plugin-kaggle"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = ["3lc-compute-plugin-sdk[shared]>=0.1.0,<0.2.0"]

[project.optional-dependencies]
kaggle = [
    "kaggle>=1.6",
    "3lc-ultralytics>=0.3.3",
    "torch",
    "torchvision",
    "3lc[pandas]>=3.0.0,<4.0.0",
]

[project.entry-points."tlc_compute.plugins"]
kaggle = "tlc_plugin_kaggle"
```

(Torch index pins: our desktop needs cu128 for the RTX 5070 Ti; yolo's committed source pins
cu126 (`pyproject.toml:54-58`) — override locally / choose the index per target machine.
**[UNKNOWN — verify with Hub team]** what CUDA index the competition Hub machines should
pin.)

### Open questions (consolidated)

1. Private-repo catalog/install auth — no mechanism exists; folder-source deployment is the
   workaround (§4.2). **[UNKNOWN — verify with Hub team]**
2. Which host the competition Hub runs: installed 0.1.1.47 (in-process, no venv/catalog) vs
   the new SDK-contract host the reference repos target. Decides isolation mode and dep
   strategy (§3). **[UNKNOWN — verify with Hub team]**
3. `.yaml` from-scratch support in the provisioned `3lc-ultralytics` (§1.4).
   **[UNKNOWN — verify with Hub team]**
4. CUDA wheel index for target machines (§7). **[UNKNOWN — verify with Hub team]**
5. Where Kaggle API credentials should live for a venv worker (env inheritance assumed, §3).
   **[UNKNOWN — verify with Hub team]**
