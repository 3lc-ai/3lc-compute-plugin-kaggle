# v1.2.10 pre-tag checklist

Scope: the project-root findings from Gudbrand (non-default
`project-root-url`) — root resolution, the `/projects/` anchor in the URL
parse and its ui.html mirror, and test coverage for the class. Rules:
RELEASING.md order (tag → repo catalog.json → gist mirror), never retag,
`pytest` last thing before tagging.

**Epistemic status:** the root cause was established by **measurement, not
inference** — every claim below was produced by running code, and the probe
outputs are quoted. The reporter's symptom was reproduced end to end in the
BACKEND on the 0.2.x host (real tlc 3.1.0.28, real tables, a genuinely
non-default root). It was **not** reproduced through the browser: the UI
click-through checks are listed under "Open pre-tag items" and belong to
whoever next has the service up.

## The two defects

1. `importer._project_root_url` called
   `ConfigStore.instance().get(tlc_options.ROOT_URL)` — a **string**-keyed
   API handed an `Option` **object**. Miss → `None` → no raise, no warning
   → a truthiness fallback returned `_get_default_root_url()`. Every
   derived table URL was built under the DEFAULT project root, on every 3.x
   host, since the helper was written (v1.2.0).
2. `config_store.url_project` (and its mirror `kgUrlSeg`) required a
   literal `/projects/` path segment. A root like `D:/3lc-data` has none, so
   `classify_override` answered `drop` and a corrected or hand-picked
   revision URL was never persisted — the reason the manual workaround died
   on reload.

Import looked correct throughout because creation passes
`project_name=`/`dataset_name=` and lets tlc resolve the root: the tables
landed in the right place while every URL derived for another tab pointed
at the wrong one.

## Verified at review (2026-09-03, dev machine + both hub venvs)

- [x] **The lookup misses silently.** `get(opts.ROOT_URL)` → `None`;
      `get("project-root-url")` → the configured value;
      `get_source(...)` → `ConfigSource.USER_CONFIG_FILE`. `get`'s
      signature is `(key: 'str') -> 'Any | None'` in the dev venv (tlc
      3.1.0.28), `3lc-hub-next/.venv` (3.1.0) and `3lc-hub-ga/.venv`
      (3.3.0) alike — so this never worked on any 3.x host.
- [x] **One string key covers every input form** (measured against a
      freshly loaded store): canonical `project-root-url:`; the deprecated
      `indexing:` → `project-root-url:` spelling (the store canonicalizes
      it and warns); `TLC_PROJECT_ROOT_URL` (no `claim_pending_env` needed);
      the deprecated `TLC_CONFIG_PROJECT_ROOT_URL` alias; and
      `--project-root-url` via `load_cli` into the same key.
- [x] **But the store returns values UNEXPANDED** — which is why the fix
      uses `tlc.config.project_root_url`, not a keyed store read.
      Measured on both hosts:
      - tlc **3.1.0.28** (`3lc-hub-next`), root set to `~/…/probe-tilde`:
        `tlc.config.project_root_url` → `C:/Users/.../3lc-hub-next/home/.../probe-tilde`
        (expanded, and against the redirected home);
        `store.get(...)` → `'~/…/probe-tilde'` (literal).
      - tlc **3.3.0** (`3lc-hub-ga`), root set to `${KGPROBE}/rootB`:
        `tlc.config.project_root_url` → the expanded absolute path;
        `store.get(...)` → `'${KGPROBE}/rootB'` (literal).
      `hasattr(tlc.config, "project_root_url")` is True on both.
- [x] **`tlc.Url` normalizes**, so however the root is spelled the built
      URL is one canonical string: a backslash root, a forward-slash root
      and a trailing-slash root all produce the identical
      `…/projects/exdark-competition/datasets/exdark_train/tables/initial`.
      Hence **no behavior change on a default root**: the option is unset
      there (commented out in the generated `config.yaml` — checked in the
      real home and both hub homes), so the same default value is used by
      the same code path.
- [x] **The on-disk layout assumption is real**, walked in
      `3lc-hub-next/home/.../projects/exdark-competition`:
      `<root>/<project>/datasets/<dataset>/tables/<table>`. And
      `list_project_tables`' `.parent.parent.parent` arithmetic yields
      `<root>/<project>/datasets` for a bare (`D:/3lc-data`) and a
      `projects`-shaped (`E:/relocated/projects`) root alike.
- [x] **End-to-end backend reproduction and fix**, on the 0.2.x host with
      real tlc 3.1.0.28, the plugin working copy on `PYTHONPATH`, the three
      real exdark tables copied under a **bare** root
      (`<scratch>/gudbrand-root`, no `/projects/` segment anywhere), root
      supplied through `TLC_PROJECT_ROOT_URL` (same store key and same
      resolution path as the `config.yaml` spelling, both verified above,
      and it leaves the hub home untouched):
      - `_project_root_url()` → the configured root
      - `/tables/defaults` → all three splits `exists=True`
      - the derived URL parses: project `exdark-competition`, dataset
        `exdark_train`, table `initial`
      - `classify_override` → `suppress` for the session revision,
        **`keep`** for a `round2` pick (i.e. a hand-picked revision now
        persists — the reporter's workaround becomes durable)
      - `/tables/list` → all three datasets with their revision chains
        (`exdark_train: initial, round2, train_v2*`)
      - `/import/revisions` → `exists: True`
- [x] **Control run on the default root**, same code, env var unset:
      unchanged behavior (tables resolve, picker lists all three datasets).
- [x] **`pytest -q`: 157 passed** (86 before this release). Every
      pre-existing test passes **unmodified in substance** — the fixtures
      are all default-shaped, which is precisely the "nothing moved on a
      default root" guard.
- [x] **The new tests fail on the pre-fix source.** With the three source
      files stashed and the new tests kept: **39 failed, 16 passed**. This
      suite would have caught both defects.
- [x] **The two mirrors agree in BEHAVIOR, not just in text.**
      `test_url_regex_parity.py` compares the pattern strings; that cannot
      see an engine difference or a broken regex literal. So `kgUrlSeg` was
      extracted from ui.html and run under node v24.16.0 against the Python
      helpers on the same eight inputs — default / relocated / bare roots, a
      backslash URL, one with surrounding whitespace, the
      `D:/datasets/staging/…` first-match trap, an unparseable string, and a
      dataset-level URL. **All eight agree**, `None`/`null` included. Not
      added as a test: node is not a dev dependency and the suite stays
      pytest-only (the textual parity test is the standing guard).
- [x] **Manifest/catalog integrity** (RELEASING.md step 2, machine-checked
      before writing): `catalog.json` round-trips byte-identically through
      `json.dumps(indent=2, ensure_ascii=False)`; the new 1.2.10 manifest
      equals `plugin.toml` exactly (`tomllib` compare, all keys); catalog
      `id` == plugin `id`; version string identical in `pyproject.toml`
      (both sites), `plugin.toml` and the catalog manifest.
- [x] **Version-pin sweep** per RELEASING.md: `docs/TESTER_SETUP_0.2.md`
      (7 pins), `scripts/setup-0.2-tester.ps1` (3, incl. `$PLUGIN_VER`),
      `README.md` (4), `pyproject.toml` (2), `plugin.toml` (1). A tree-wide
      grep for `1.2.9` leaves only history (CONTEXT.md's release narrative,
      ideas/audit docs, earlier catalog entries) — no stale pin.

## Deliberate non-goals (A3)

Found during the sweep for "same shape as this bug", all logged in
docs/v1.2-ideas.md, none fixed here: remote (`s3://`) project roots are not
walkable by `list_project_tables`; `kgUrlSeg` has no unknown-`kind` guard
(latent — every caller passes a literal); a corrupt `ui_config.json` reads
as a fresh install; and table lineage already flattens on real data
(`revisions: None` on `3lc-hub-next`, on the default root as well as a
relocated copy — pre-existing, not a regression).

No repair migration ships: `session_v1` reads the legacy URL keys and then
pops them, so an already-migrated config no longer contains the value that
was wrongly dropped. There is nothing to repair from. Configs that have
**not** yet migrated (still v1.1.x-shaped) migrate correctly under any root
from this version on.

## Open pre-tag items

- [ ] **UI click-through** (needs the service up + the :5020 frontend
      swap). Backend equivalents are all verified above, so these confirm
      rendering, not resolution: Train autofills both fields and gates
      green with no editing; Predict the same for the test URL; the
      revision picker lists the three datasets; pick a non-default
      revision, reload, it persisted; clear the field, it re-derives.
- [ ] **Tell Gudbrand.** No reset, no cleanup: his tables are under his
      configured root and his `import_state` snapshot holds their real
      URLs, nothing wrong-root was ever persisted (derived values are never
      written), and his hand-corrected URL is exactly what derivation now
      produces. Update, then **hard-refresh the plugin page** — the
      standing post-update step.
- [ ] One unrecoverable edge to state if it comes up: a v1.1.x config that
      already migrated under a non-`projects`-shaped root **and** held a
      non-default revision pick lost that pick at migration time. Re-pick
      it in the revision picker.

## Post-tag verification (tick-only below this line; everything above is frozen at the tag)

- [ ] Tag `v1.2.10` pushed; `catalog.json` entry landed; gist mirrored by
      Rishikesh (verify via an incognito fetch after the CDN lag).
- [ ] Footer reads `1.2.10` after a catalog install (RELEASING.md step 4).
- [ ] Gudbrand confirms Train/Predict autofill resolve on his machine.
