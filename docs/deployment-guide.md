# Deployment guide: getting a plugin visible & reloadable on the installed Hub

Operator's guide for **this machine's** Hub: `3lc_compute` distribution **0.1.1.47**
(3lc 2.22.3 install), Object Service on **:5015**, Compute Service on **:5020**, venv at
`3lc-hub\.venv`. Written 2026-07-20 against the actual installed source plus live probes of
the running service.

**Citation convention.** Bare `tlc_compute/...` paths are relative to
`3lc-hub\.venv\Lib\site-packages\`. `template ...` / `sdk ...` cite the clones under
`plugin-research\3lc-compute-plugin-template` / `-sdk`. Every step is tagged:

- ✅ **works on 0.1.1.47**: verified in the installed source (and, where noted, probed live)
- 🔮 **new-host-only**: documented by the SDK/template for the newer catalog/venv host;
  does **nothing** on our install

**Version gotcha (read first).** The *distribution* is `3lc_compute-0.1.1.47`
(`Scripts\..\3lc_compute-0.1.1.47.dist-info`), but the package reports
`__version__ = "0.2.0"` (`tlc_compute/__init__.py:12`), confirmed live:
`GET :5020/health` → `{"status":"ok","service":"3lc-compute","version":"0.2.0","mode":"all"}`.
All `min_service_version` gates compare against **0.2.0**, parsed as a dotted int tuple
(`tlc_compute/plugins/discover.py:62-84`). Keep `min_service_version = "0.1.0"`.

---

## 1. Discovery mechanics: what makes a folder "a plugin" to 0.1.1.47

The single most important divergence from the SDK/template docs:

> ✅ **The installed host never reads `plugin.toml`, `pyproject.toml`, or any manifest
> file.** There are zero TOML references anywhere in the installed `tlc_compute` package
> (verified by grep over `tlc_compute/**/*.py`, 2026-07-20). Discovery is **import-based**:
> a plugin is a Python package that, *at import time*, instantiates a `ComputePlugin`
> subclass and calls `register()` on it.

Mechanics, in order (`tlc_compute/plugins/external_loader.py`):

1. **A registered path is a "plugin root", not a plugin.** Its *immediate subdirectories*
   are the plugin candidates: *"A 'plugin directory' is a directory whose immediate
   subdirectories each contain an `__init__.py` and register a `ComputePlugin` at import
   time"* (`external_loader.py:17-19`; same wording in
   `tlc_compute/config.py:37-42`). For our repo that means you register
   **`...\3lc-compute-plugin-kaggle\src`**, *not* the repo root and *not* the package dir
   itself. (Registering the repo root silently finds nothing: `docs` is skip-listed and
   `src` has no `__init__.py`.)
2. **Candidate filter** (`external_loader.py:125-140`): immediate subdir, not starting with
   `_` or `.`, name not in the skip set `{"__pycache__", "shared", "tests", "test",
   "docs"}` (`external_loader.py:45`), and containing an `__init__.py`.
3. **The root goes on `sys.path`** (`sys.path.insert(0, abs_path)`,
   `external_loader.py:189-190`) and each candidate is imported **as a top-level module
   in the host process**: `importlib.import_module(package_name)`
   (`external_loader.py:227-228`).
4. **Registration is detected by side effect.** After the import, the loader diffs the
   registry: any plugin id not registered before the import is credited to this package
   (`external_loader.py:202, 246-249`). If the import registers nothing, the folder is
   skipped with reason `"no plugin registered"` (`external_loader.py:247-249`). The
   `register()` call itself just inserts the instance into a module-level dict and refuses
   duplicate ids (`tlc_compute/plugins/registry.py:53-67`).
5. **Name-conflict guards** (`external_loader.py:206-225`): a candidate is skipped if its
   folder name is already owned by another external dir, or already present in
   `sys.modules`. ⚠️ Because the root is *prepended* to `sys.path`, a plugin folder named
   `kaggle` would shadow the `kaggle` pip package for every later import in the host
   process. **Name the package `tlc_plugin_kaggle`, never `kaggle`.**

Three ways a root gets registered, all landing in `add_external_dir()`:

| Channel | Origin tag | Survives restart? | Evidence |
|---|---|---|---|
| `--plugin-dir PATH` CLI flag (repeatable) or `TLC_COMPUTE_EXTERNAL_PLUGIN_DIRS` env (`;`-separated on Windows) | `transient` | Yes, if you always start with the flag (never written to disk) | flag def `tlc_compute/app.py:249-260`, flag→env `app.py:277-278`, env→config `tlc_compute/config.py:49-59`, loaded at startup `external_loader.py:384-402` |
| `POST :5020/api/admin/plugins/dirs` `{"directory": "...", "persist": true}` | `persistent` | Yes; appended to `~\.3lc-compute\settings.json` under `plugin_dirs`, reloaded every boot | route `tlc_compute/routes/plugins.py:342-399`, store `tlc_compute/persistent_settings.py:38-50, 84-106`, boot load `external_loader.py:405-422` |
| Same POST with `"persist": false` | `session` | No; gone at next restart | `routes/plugins.py:377-378` |

Startup order: built-ins import first via `tlc_compute/plugins/discover.py:32-41`, then
CLI/env dirs, then persisted dirs (`registry.py:280-307`). The startup banner prints
`External plugin dirs: ...` when the CLI/env channel is set (`app.py:290-291`).

🔮 **New-host-only:** manifest-file discovery (`read_manifest()` reading `plugin.toml` or
a `[tool.tlc-compute]` table in `pyproject.toml` *without importing*; template
`README.md:25, 30-33`; sdk `docs/plugin-guide.md:93-97`), the
`[project.entry-points."tlc_compute.plugins"]` installed-package path (template
`pyproject.toml:39-40`), and venv provisioning on registration (template `README.md:70-71`).
None of that machinery exists in the installed package. Ship a `plugin.toml` in the repo
anyway for the future migration; 0.1.1.47 ignores it harmlessly.

---

## 2. Manifest fields: what 0.1.1.47 actually reads

✅ On the installed host the manifest is **class attributes on your `ComputePlugin`
subclass** (`tlc_compute/plugins/base.py:23-173`), serialized to JSON by `get_manifest()`
(`base.py:181-218`). Anything you'd put in `plugin.toml` for the new host must be mirrored
as a class attribute here.

**Hard minimum for the plugin to load at all:**

- A subclass of `tlc_compute.plugins.base.ComputePlugin` implementing the two abstract
  methods `get_ui_fragment()` and `compute(params)` (`base.py:222-236`); Python refuses to
  instantiate the class otherwise.
- A unique `id` (registry keys on it and rejects duplicates, `registry.py:63-64`).
- A module-level `register(YourPlugin())` call in `__init__.py` (`registry.py:53-67`;
  convention stated in `discover.py:16-18`).

**Minimum for it to appear in the sidebar** (on top of the above): `display_mode =
"sidebar"` (the class default is `"action"`, `base.py:72-74`), plus a human-readable
`name`, and a `section` label so it lands in a named group (`base.py:85-87`). Everything
else has workable defaults.

Field map (installed attr ↔ new-host `plugin.toml` key):

| Installed class attr (`base.py`) | Read by 0.1.1.47? | New-host `plugin.toml` equivalent |
|---|---|---|
| `id`, `name`, `description`, `version` (`:31-41`) | ✅ | top-level `id/name/description/version` |
| `min_service_version` / `max_service_version` (`:43-47`) | ✅ (enforced against internal `0.2.0`; incompatible plugins stay listed but disabled, `discover.py:70-84`) | same, top-level |
| `icon` (emoji fallback), `icon_svg` (16×16, `currentColor`) (`:65-70`) | ✅ | `icon`, `icon_svg` |
| `display_mode` (`:72-74`) | ✅ (`sidebar`/`action`; no `hidden` here) | `[ui] display_mode` (adds `hidden`) |
| `section`, `priority`, `group`, `group_icon_svg` (`:85-87, 141-157`) | ✅ | `[ui] section/priority` (grouping differs) |
| `compatible_with`, `input_types`, `output_types`, `min_input_count`, `action_param_names` (`:76-101`) | ✅ | `[ui]` same names |
| `quick_action`, `quick_action_label`, `quick_action_description` (`:103-110`) | ✅ | `[ui]` same names |
| `requires_gpu` (`:112-117`) | ✅ (also the `--mode cpu/gpu` filter unregisters non-matching plugins, `discover.py:48-54`; our service runs `mode: all`) | `[runtime] requires_gpu` |
| `training` (`:119-123`) | ✅ (informational) | `[runtime] training` |
| `socketio_namespace`, `socketio_runner_module`, `socketio_runner_fn` (`:125-139`) | ✅ (auto-registered after runtime init, `external_loader.py:101-111`) | replaced by the SDK's default `/<id>` namespace |
| `auth_exempt_paths` (`:159-173`) | ✅, but **collected once at app creation** (`app.py:179-187`), so useless for runtime-added plugins; needs the plugin present at service start | `[runtime] auth_exempt_paths` |
| `update_available`, `changelog_url`, `upgrade_required`, `repository_url` (`:52-63`) | ⚠️ echoed in the manifest JSON but the repository system is "not yet built" (`base.py:52`) | catalog-populated |
| — | 🔮 not read | `[runtime] isolation`, `entrypoint`, `provision_extra`, `venv_python` (venv-host concepts with no installed counterpart) |

---

## 3. Where it appears in the UI: the sidebar entry

The sidebar data comes from one endpoint on the compute service:

- `GET :5020/api/plugins/` returns every registered plugin's manifest, **sorted by
  `priority` descending, then `name`** (`tlc_compute/routes/plugins.py:49-57` calling
  `get_manifests()` at `tlc_compute/plugins/registry.py:269-272`).
- The manifest carries everything the sidebar needs: `display_mode`, `section`, `icon` /
  `icon_svg` (docstring: *"The frontend uses this for sidebar, breadcrumb, and hero
  sections. If empty, falls back to `icon`"*, `base.py:68-70`), `priority` (*"Sort priority
  within a sidebar section"*, `base.py:141-146`), and `group`/`group_icon_svg` for
  collapsible sub-groups (`base.py:148-157`).

The rendering code is **not on this machine**: the Hub page is the hosted web frontend
(the Object Service banner points at the hosted dashboard; the compute venv contains no
sidebar HTML/JS, and grep for `display_mode` across `site-packages\**\*.js` returns
nothing). So the contract, as observed: the frontend takes `display_mode == "sidebar"`
manifests and groups them under uppercased `section` headers. The three entries you see
under **AI TOOLS** are exactly the three built-ins that declare `section = "AI Tools"`:
sam3 (`tlc_compute/plugins/sam3/__init__.py:32,36`), yolo, and timm (the only three files
in the venv containing the string `"AI Tools"`). Set the same three attributes and our
plugin joins that group:

```python
display_mode = "sidebar"
section = "AI Tools"
priority = 40          # yolo/sam3/timm order first if higher; 40 puts us below them
```

The frontend polls `/api/plugins` frequently (it's on the service's access-log quiet list,
`app.py:33`), so a newly registered plugin generally pops into the sidebar without a
manual page refresh; a hard refresh (Ctrl+F5) is the fallback.

---

## 4. First deployment walkthrough (this machine)

From "repo cloned locally" to "visible in sidebar". Assumes the repo at
`C:\Users\Owner\Desktop\3LC Kaggle Competitions\3lc-compute-plugin-kaggle` grows a
`src\tlc_plugin_kaggle\` package (see §7 for a minimal one).

**Auth reality check (probed live 2026-07-20).** Our service runs **JWT (SaaS) auth**
(printed in its startup banner, `app.py:285-287`; middleware wiring `app.py:185-203`).
Every `/api/*` route, including all admin routes, returns **403 without a valid JWT**;
only `/health`, `/live`, `/schema` are exempt (`app.py:187`). The 36-char 3LC API key does
**not** work as a Bearer token (tested: still 403). Working tokens:

- **Borrow the Hub's JWT**: open the Hub in the browser → DevTools → Network → any
  `localhost:5020` request → copy the `Authorization: Bearer eyJ...` header. Fine for a
  dev session; it expires with the Hub session.
- **Skip HTTP entirely** for registration (steps below use this by default): the CLI flag,
  the env var, and hand-editing the settings file all bypass auth because they're read at
  process start, not over HTTP. The Hub's own Settings page is the UI wrapper over the
  same persisted store (`persistent_settings.py:14-22`).

**Step 0: install the plugin's deps into the host venv** (see §6 for why):

```powershell
cd "C:\Users\Owner\Desktop\3LC Kaggle Competitions\3lc-hub"
uv pip install kaggle          # plus anything else our plugin imports at module level
```

**Step 1: persist the plugin root.** Easiest no-token method: write the settings file the
service reads at every boot (`persistent_settings.py:38-39, 150-153`; the schema is just
`{"plugin_dirs": [...]}`):

> ⚠️ **BOM trap (hit for real, 2026-07-20).** Do **not** use PowerShell 5.1's
> `Out-File -Encoding utf8`: it writes a UTF-8 **BOM**, and the host reads the file with
> plain `read_text(encoding="utf-8")` + `json.loads` (`persistent_settings.py:138`), which
> rejects it: `json.decoder.JSONDecodeError: Unexpected UTF-8 BOM`. The failure is
> **silent**: the service logs `Could not parse ... starting with empty persistent
> settings` (`persistent_settings.py:140-142`) and boots with zero plugin dirs. Write
> BOM-less:

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.3lc-compute" | Out-Null
$json = @'
{
  "plugin_dirs": [
    "C:\\Users\\Owner\\Desktop\\3LC Kaggle Competitions\\3lc-compute-plugin-kaggle\\src"
  ]
}
'@
[IO.File]::WriteAllText("$env:USERPROFILE\.3lc-compute\settings.json", $json,
  (New-Object System.Text.UTF8Encoding($false)))

# Sanity-check that the HOST can parse it before restarting:
& "C:\Users\Owner\Desktop\3LC Kaggle Competitions\3lc-hub\.venv\Scripts\python.exe" `
  -c "from tlc_compute.persistent_settings import PersistentSettingsStore; print(PersistentSettingsStore().get_plugin_dirs())"
```

Alternatives that do the same thing: the Hub Settings page, or (with a borrowed JWT):

```powershell
curl -X POST http://localhost:5020/api/admin/plugins/dirs `
  -H "Authorization: Bearer <JWT>" -H "Content-Type: application/json" `
  -d '{\"directory\": \"C:\\\\Users\\\\Owner\\\\Desktop\\\\3LC Kaggle Competitions\\\\3lc-compute-plugin-kaggle\\\\src\", \"persist\": true}'
```

The POST loads the plugin **immediately** (`routes/plugins.py:342-399` →
`add_external_dir`, which init-runtimes new plugins post-startup,
`external_loader.py:256-260`) *and* persists it, but see the restart caveat next.

**Step 2: restart the Compute Service window.** Not optional for a real plugin: custom
Litestar route controllers are collected **once** in `create_app()`
(`app.py:206-224`): a plugin hot-added at runtime gets its generic `/ui` / `/manifest` /
`/compute` endpoints (served by the wildcard `PluginsController`,
`routes/plugins.py:91-131`) but **its own controllers are never mounted, and its
`auth_exempt_paths` are never collected** (`app.py:179-187`). Note the installed host has
**no generic `POST /{id}/run`** (the `PluginsController` route list is `/, /by-resource,
/{id}/manifest, /{id}/ui, GET /{id}/compute, /jobs, /jobs/{id}/cancel`,
`routes/plugins.py:44-171`), so long-running jobs require our own routes, like yolo's
`/train` (`tlc_compute/plugins/yolo/routes.py:230`). So: Ctrl+C in the compute window,
then:

```powershell
cd "C:\Users\Owner\Desktop\3LC Kaggle Competitions\3lc-hub"
.\.venv\Scripts\3lc-compute.exe
```

(Equivalent one-shot without the settings file:
`.\.venv\Scripts\3lc-compute.exe --plugin-dir "C:\Users\Owner\Desktop\3LC Kaggle Competitions\3lc-compute-plugin-kaggle\src"`,
flag def `app.py:249-260`. But then the flag must accompany *every* start, so prefer the
settings file.) Leave the Object Service window (`:5015`) alone; plugins never touch it.

**Step 3: verify registration state.**

- No token: watch the compute service's stderr log. The definitive line (verified live)
  is `Plugin <id> runtime initialized` (`app.py:127`), printed after the built-ins during
  startup; `Registered plugin: ... (package: ...)` (`registry.py:67`) fires at import
  time. Import failures log `External plugin '...' failed to import` with the exception
  (`external_loader.py:230`). Tip: if you start the service detached instead of in a
  console, capture the logs:
  `Start-Process .\.venv\Scripts\3lc-compute.exe -WorkingDirectory $hub -RedirectStandardOutput "$hub\compute-service.out.log" -RedirectStandardError "$hub\compute-service.err.log" -WindowStyle Hidden`
  (banner goes to stdout, all plugin logging to stderr).
- With a JWT: ✅ **yes, there is a GET endpoint**.
  `GET :5020/api/admin/plugins/dirs` returns
  `{"directories": [...], "plugins_by_dir": {...}, "origins": {...}}`
  (`routes/plugins.py:318-340`), and `GET :5020/api/plugins/kaggle/manifest` returns our
  manifest (`routes/plugins.py:72-89`). Caveat, observed live: once a plugin mounts its
  **own** controller at `/api/plugins/<id>` the wildcard `/manifest` (and `/ui`) routes
  are shadowed and 404, e.g. `GET /api/plugins/yolo/manifest` → 404. That's the
  shadowing behavior `base.py:326-341` warns about; use `GET /api/plugins/` for
  enumeration instead.

**Step 4: see it in the Hub.** Open the Hub page; the entry appears under the `section`
you declared (AI TOOLS). If it doesn't: hard-refresh, then check
`GET /api/plugins/` (JWT) for the manifest and confirm `display_mode == "sidebar"` and
`compatible: true` (a wrong `min_service_version` shows up here as `compat_reason`,
`discover.py:74-77`).

---

## 5. The iteration loop

✅ **The per-plugin reload endpoint exists on 0.1.1.47**:
`POST :5020/api/admin/plugins/kaggle/reload`
(route `tlc_compute/routes/plugins.py:183-220`; JWT required; `?force=true` to reload past
running jobs, else 409). It calls `reload_plugin()` (`registry.py:153-251`) which:

1. rejects if the plugin has running jobs and `force` is off (`registry.py:188-191`),
2. `shutdown_runtime()` + unregister (`registry.py:207-208`),
3. **purges every `sys.modules` entry for the package** (`registry.py:210-211`, purge
   helper `:109-123`),
4. re-imports the package, which re-runs your module-level `register()`
   (`registry.py:215-228`),
5. `initialise_runtime()` on the new instance (`registry.py:230-234`),
6. clears `_ui_cache` if the plugin has one (`registry.py:236-237`).

**What a reload picks up:** all Python code in the package (fresh import), the manifest
(class attributes are re-evaluated on import; the sidebar updates once the frontend
re-fetches `/api/plugins/`), and the UI fragment (fresh `get_ui_fragment()`, cache
cleared; keep the read-`ui.html`-into-`_ui_cache` pattern, `sam3/__init__.py:54-67`).

There's also a whole-dir variant, `POST :5020/api/admin/plugins/dirs/reload` with
`{"directory": "...\\src"}` (`routes/plugins.py:472-503`), which fully detaches and
re-adds the root (`external_loader.py:356-381`): use it when you've added a *new* plugin
folder under the same root. 🔮 On the new host this same endpoint re-provisions venvs on
dependency changes (template `README.md:83-88`); on 0.1.1.47 it re-imports in-process,
nothing more.

**What needs more than a reload:**

| Change | Why reload isn't enough | Action |
|---|---|---|
| New/renamed/removed **custom routes** (your Litestar controller) | Handlers are bound once at `create_app` (`app.py:206-224`); reload docstring: *"Litestar routes registered at startup are NOT affected"* (`registry.py:167-171`) | Restart the compute service |
| **Dependency changes** | Deps live in the host venv (§6); a purge only forgets *your* modules, and third-party libs already imported elsewhere stay | `uv pip install ...` in `3lc-hub`, then restart |
| Changing the plugin **`id`** or the **package folder name** | Registry/module-owner maps key on the old names (`registry.py:30, 66`; `external_loader.py:253-254`) | `POST /dirs/reload` (dir-level), or restart |
| Stale references held by **bound custom handlers** | A controller that imports implementation at module level (yolo style, `plugins/yolo/routes.py:19-22`) keeps pointing at the *old* purged modules after reload | Design rule for our plugin: custom handlers lazy-import inside the function body (like yolo's `/ui` handler, `routes.py:30-37`) so each request resolves the freshly imported module |

Day-to-day loop, concretely: edit code/`ui.html` → `curl -X POST -H "Authorization:
Bearer <JWT>" http://localhost:5020/api/admin/plugins/kaggle/reload` → refresh the plugin
page in the Hub. When the JWT has expired, grab a fresh one from DevTools, or just
restart the service window (slower, never blocked).

---

## 6. The in-process import caveat

0.1.1.47 imports external plugins **into the compute-service process and venv**: there is
no venv provisioning, no worker process, no isolation (`external_loader.py:20-23`; the
new-host counterparts are 🔮: template `README.md:30-33`, sdk worker).

Practical consequences:

- **Dependencies go into `3lc-hub\.venv`**, the venv that owns
  `Scripts\3lc-compute.exe` (confirmed live: PID on :5020 runs that exact exe). Install
  with `uv pip install <dep>` from the `3lc-hub` directory. Our stack largely pre-exists
  there (torch cu128, `tlc_ultralytics`, the full `tlc` SDK); the `kaggle` client is a
  light pure-Python addition. ⚠️ Never let a plugin dep *upgrade* a pinned host package
  (torch, ultralytics, litestar…); that can break the whole Hub. Check what an install
  would do first (`uv pip install --dry-run kaggle`).
- **Import errors fail gracefully, per-plugin.** The loader wraps each candidate import in
  `try/except`: a failing plugin is logged and reported in the `skipped` list with the
  exception text; for `ModuleNotFoundError` it appends the exact instruction *"Install
  missing dependency in the compute-service venv: `pip install <name>`"*
  (`external_loader.py:227-243`). The service keeps running; other plugins are unaffected.
  Same containment at runtime-init (`external_loader.py:89-99`) and per-plugin at startup
  (`app.py:117-130`, built-in discovery `discover.py:38-41`).
- **Crashes after loading are only as contained as HTTP.** An exception inside `compute()`
  or a custom route is a 500 on that request. But the plugin shares the process: a
  segfaulting native lib, an OOM, or `sys.exit` takes the whole compute service down.
  Treat host-venv compatibility as a hard requirement, not a nice-to-have.
- **GPU is shared, not sandboxed.** Set `requires_gpu = True` and route long GPU work
  through the shared queue (`tlc_compute/shared/gpu_queue.py`, initialized at
  `app.py:104-109`) like yolo/sam3 do, or our training jobs will fight the built-ins for
  the 5070 Ti.

---

## 7. Smoke test: the smallest plugin that shows up in the sidebar

Goal: prove the whole pipeline (discovery → manifest → sidebar → UI fragment → compute →
reload) before writing real code. Two files, no dependencies beyond the host venv.

**Layout** (a throwaway root, so the real `src\` stays clean until we mean it):

```
C:\Users\Owner\Desktop\3LC Kaggle Competitions\3lc-compute-plugin-kaggle\
└── smoke\                        ← the "plugin root" you register
    └── tlc_plugin_hello\         ← the plugin package (name ≠ any pip package!)
        ├── __init__.py
        └── ui.html
```

**`smoke\tlc_plugin_hello\__init__.py`**, complete contents:

```python
"""Hello-world smoke-test plugin for the installed 3LC Hub (tlc_compute 0.1.1.47)."""

from pathlib import Path
from typing import Any

from tlc_compute.plugins.base import ComputePlugin
from tlc_compute.plugins.registry import register


class HelloPlugin(ComputePlugin):
    id = "hello"
    name = "Hello Smoke Test"
    description = "Proves external plugin discovery, sidebar placement, UI, and reload."
    version = "0.1.0"
    min_service_version = "0.1.0"
    icon = "👋"
    display_mode = "sidebar"
    section = "AI Tools"
    priority = 1  # bottom of the AI TOOLS group

    # Dev-only: exempt this plugin's own endpoints (and its reload) from the
    # JWT middleware so the smoke test is verifiable with plain curl. This is
    # a real host feature (base.py:159-173) but patterns are only collected at
    # app creation (app.py:179-187), so the plugin must be present at startup.
    # Remove for anything beyond smoke testing.
    auth_exempt_paths = [
        r"^/api/plugins/hello/",
        r"^/api/admin/plugins/hello/reload$",
    ]

    _ui_cache: str | None = None

    def get_ui_fragment(self) -> str:
        if self._ui_cache is None:
            ui_path = Path(__file__).resolve().parent / "ui.html"
            self._ui_cache = ui_path.read_text(encoding="utf-8")
        return self._ui_cache

    def compute(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"hello": "world", "echo": params}


register(HelloPlugin())
```

**`smoke\tlc_plugin_hello\ui.html`**, complete contents:

```html
<div class="plugin-page-narrow" style="padding: 24px;">
  <h2>👋 Hello from an external plugin</h2>
  <p>If you can read this in the Hub, discovery + sidebar + UI serving all work
     on the installed host (tlc_compute 0.1.1.47 / internal 0.2.0).</p>
  <button id="hello-btn" class="btn">Call compute()</button>
  <pre id="hello-out" style="margin-top: 12px;"></pre>
  <script>
    document.getElementById("hello-btn").addEventListener("click", async () => {
      // The fragment runs inside the HOSTED Hub frontend, so relative URLs would
      // hit the wrong origin. Prefix with the compute-service base and use
      // authFetch so the Hub's Authorization header rides along — the exact
      // pattern the built-ins use (merger ui.html:163-164, 244).
      const API = window.PLUGIN_API;
      const computeUrl = API.getConfig("compute_service_url");
      const res = await API.authFetch(computeUrl + "/api/plugins/hello/compute?probe=1");
      document.getElementById("hello-out").textContent =
        JSON.stringify(await res.json(), null, 2);
    });
  </script>
</div>
```

Notes: `_ui_cache` is what the reload endpoint clears (`registry.py:236-237`), so keep it
even here. `compute()` is served by the host's generic wildcard route
`GET /api/plugins/hello/compute` (`routes/plugins.py:111-131`). The smoke plugin needs
**no custom controller**, which is exactly why it *can* be hot-added without a restart.

**Run it** (this exact sequence was executed and verified end-to-end on this machine,
2026-07-20; the smoke root used was `...\plugin-smoketest\hello-world\`):

```powershell
# 1. Register the root: add it to plugin_dirs in %USERPROFILE%\.3lc-compute\settings.json
#    per §4 step 1 — BOM-less write, then the host-side parse sanity check.
# 2. Restart the compute service. (POST /api/admin/plugins/dirs would hot-load a
#    routeless plugin, but auth_exempt_paths only take effect when the plugin is
#    present at app creation — so for the tokenless smoke test, restart.)
# 3. Verify discovery in the stderr log — verified line:
#      INFO ... tlc_compute.app - app - Plugin hello runtime initialized
# 4. Verify serving (tokenless thanks to auth_exempt_paths) — all verified 200:
curl http://localhost:5020/api/plugins/hello/manifest   # {"id":"hello","name":"Hello Smoke Test",...,"section":"AI Tools","compatible":true,...}
curl http://localhost:5020/api/plugins/hello/ui         # the fragment HTML
curl "http://localhost:5020/api/plugins/hello/compute?probe=1"  # {"hello":"world","echo":{"url":"","kwargs":null}}
# 5. Iteration loop — edit the <h2> text in ui.html, then (verified: 200 in ~2.1 s,
#    {"reloaded":true,"plugin_id":"hello","old_version":"0.1.0","new_version":"0.1.0",
#     "modules_purged":1,"package":"tlc_plugin_hello"}):
curl -X POST http://localhost:5020/api/admin/plugins/hello/reload
curl http://localhost:5020/api/plugins/hello/ui         # serves the changed text immediately
# 6. Hub sidebar → AI TOOLS → "Hello Smoke Test" (bottom of the group, priority=1).
#    Click the button; expect {"hello":"world",...}.
# 7. Tear down: remove the smoke path from settings.json (or DELETE
#    /api/admin/plugins/dirs?directory=... with a JWT) and restart.
```

Without the `auth_exempt_paths` dev block, steps 4-5 require a JWT borrowed from Hub
DevTools (§4), the guide's original curl-with-JWT variant. Everything else is identical.

---

## Appendix: divergences to revisit at catalog migration

When the Hub moves to the SDK-contract host, these installed-host behaviors flip:

| Today (0.1.1.47, this guide) | New host (template/SDK) |
|---|---|
| Manifest = class attributes, read by importing | `plugin.toml` read without import (template `README.md:25,30`) |
| Deps in host venv, in-process import | `[runtime] isolation = "venv"`, `uv sync --extra <provision_extra>`, out-of-process worker |
| No generic run endpoint; bring your own controller + queue integration | Host-owned `POST /api/plugins/{id}/run` + `run_job(ctx)` / `JobContext` |
| Custom routes require presence at service start | Same repo registers identically via `3lc-compute --plugin-dir <repo>/src` (template `README.md:64-68`); keep the `src/` layout and the move is config-only |
| No catalog endpoints (`grep catalog` over installed source: zero hits; `base.py:52` "not yet built") | `POST /api/admin/plugins/catalogs` + `catalog.json` (template `README.md:118-131`) |

The repo should therefore carry **both** representations from day one: the class-attribute
manifest (authoritative today) and a matching `plugin.toml` (authoritative later), with a
CI check or comment discipline keeping them in sync.
