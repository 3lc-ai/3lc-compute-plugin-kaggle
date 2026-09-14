# Releasing a plugin version

Publishing `vX.Y.Z` is three moves, **in this order** — the catalog points at
the tag, so the tag must exist before the catalog advertises it.

## 1. Push the tag

```powershell
git tag vX.Y.Z
git push origin vX.Y.Z
```

The catalog's install `source` is a PEP-508 git reference pinned to this tag
(`...git@vX.Y.Z`); the shop installs whatever the tag points at, never the
working copy or a branch.

## 2. Update `catalog.json` in this repo

Add a new entry to the `versions` array of the `kaggle-exdark` plugin (newest
first): bump `version`, point `source` at the new tag, and paste in a fresh
copy of the manifest (it must match `src/tlc_plugin_kaggle/plugin.toml` —
`version` included). Bump `generated_at`. Commit and push.

`description` is part of that match and is checked:
`test_packaging::test_the_description_is_the_same_on_every_surface` compares
`plugin.toml`, the `[tool.tlc-compute]` mirror, and **this newest entry only**.
Older entries record what shipped at their version and are never rewritten to
satisfy it. `[project] description` is not in that set — it is the wheel's PyPI
`Summary`, not a Hub surface, and is deliberately its own shorter string.

The catalog `id` must equal the `plugin.toml` id, and the catalog carries one
entry per plugin id: a stale id advertises an installable card for a plugin
that no longer exists, and a mismatched id shows a phantom "available" card
beside the installed one.

**Version pins that must ride this same commit** — the catalog bump makes
every one of them stale the moment it lands. This list IS the sweep, so a
list shorter than reality reads as complete: entries get added, never pruned,
and each one says why it is easy to walk past. Pins only — PRETAG checklists
and ideas files record what was true at their tag and stay as written:

- `docs/TESTER_SETUP_0.2.md` — the title line, the §2 W1 comment and its
  env-var path, the §3b tag references, and the W1 row in the troubleshooting
  table. The version appears in prose, in a code block and inside a table cell,
  so grep this file rather than counting on a remembered list of sites.
- `scripts/setup-0.2-tester.ps1` — the header "tested against" comment and
  the `$PLUGIN_VER` variable. The W1 path and the preflight both derive from
  that variable, so it is the only site in the script to edit.
- `README.md` — the setup env-var line AND the troubleshooting torch-check
  path. Two sites, far apart, both spelling a full managed-venv path.
- `CONTEXT.md` — the "Current release" sentence under **tags**.
- `SMOKE_TEST.md` — the footer expectation in §0 and the "Plugin version
  shown in the page footer" field in the header block. A sweep is only as
  complete as this list, so the tester-facing version claim has to be named
  here: nothing else in the repo asserts what a tester should see in the
  footer, and the checklist reads as current whatever version it spells.
- `pyproject.toml` — **both** `[project] version` and
  `[tool.tlc-compute] version`. A `sed` on `^version = ` matches both; a
  hand-edit of "the version line" matches one.
- `uv.lock` — the `[[package]] name = "3lc-compute-plugin-kaggle"` entry's own
  `version`, and the `3lc-ultralytics` / `ultralytics` entries, which must
  agree with the pins in `pyproject.toml`. This is the one census entry that
  regenerates rather than being typed, so it is not a hand-edit: bump
  pyproject/plugin.toml first, then run `uv lock` (or any `uv sync`/`uv pip
  install -e .` against the repo) and commit the result. A lock that disagrees
  with the pins does not describe what ships to participants.

The sweep is manual: grep the tree for the OLD version string (`*.md`,
`*.ps1`) and update every hit that is a pin.

**The repo copy is the source of truth.** The gist (step 3) is only a mirror.

## PRETAG files freeze at their tag

`docs/PRETAG_<version>.md` is the record of what was verified before that
tag; a later edit makes it evidence of something other than what it claims.
Everything above the file's **Post-tag verification** section is FROZEN once
the tag exists. The one legitimate post-tag write is ticking that section
itself — its checks ("footer reads vX.Y.Z after a catalog install") cannot
exist before the tag. Tick-only appends there; never edit above the line.

## 3. Mirror the change to the gist

Paste the new `catalog.json` content into the gist at
<https://gist.github.com/Rishikesh-Jadhav/926ead27a6a1ed6429cf86d1924a24ce>
(edit → replace file content → save).

The gist is the **live URL that hubs actually consume**:

```
https://gist.githubusercontent.com/Rishikesh-Jadhav/926ead27a6a1ed6429cf86d1924a24ce/raw/catalog.json
```

That's the *latest-revision* raw form (no revision hash in the path), so the
URL never changes — saving the gist is all it takes. Every Hub with this
catalog source configured sees the new version on its next fetch, and the
installed card grows an **Update** button.

## 4. Verify the update landed

After installing/updating from the catalog, open any plugin tab: **the
footer must show the new version.** It renders `_meta.version`, which is
the installed dist's own metadata (derived `__version__`), never a
hand-synced constant. A stale footer means a stale install or worker, not a
cosmetic glitch — and diagnostics blocks stamp this same version, so triage
trusts it.

The version string is hand-synced in **four** places: `[project] version` AND
`[tool.tlc-compute] version` in `pyproject.toml`, plus `plugin.toml` and the
catalog manifest. The count is enforced by
`tests/test_packaging.py::test_the_four_version_strings_agree`, not by this
sentence — prose is not a check. If the two disagree, the test is right.

## Starter-kit data releases (separate from code releases)

The competition data ships through its own channel and its own rules. None
of the code-release steps above apply to it, and vice versa.

**The CDN prefix is the distribution.** `make_kit_manifest.py` generates
manifest.json + sharded zips into `cdn/<version>/`; the whole version dir is
staged to `competitions.3lc.ai/kaggle/<competition_id>/starter-kit/<version>/`
(the prefix `constants.starter_kit_prefix()` resolves). The downloader
verifies per-file sha256 from the manifest — never the HTTP ETag, because the
shards are multipart uploads whose ETags are `"<hash>-<parts>"` markers, not
content MD5s.

- **A version prefix is IMMUTABLE once staged.** Updating the kit means
  regenerating with a NEW version (`v2`, ...), staging that, and bumping
  `STARTER_KIT_VERSION` in `constants.py` in a normal code release. Never
  overwrite objects under an existing version: the 24-hour CDN edge cache
  would serve a mixed manifest/shard set that fails checksum verification in
  ways that look like corruption.
- **Data tags use the `kit-*` namespace, never `v*`** (e.g.
  `kit-exdark-v1`), so they can never be confused with code tags — the
  catalog's `source` pins parse `v*` tags only.
- **The committed manifest is the verification anchor.**
  `kit/<competition_id>/<version>/manifest.json` in this repo is a byte copy
  of the staged manifest. The generator is deterministic (fixed zip
  timestamps, sorted entries), so anyone with the kit tree can REBUILD the
  shards and arrive at the same hashes — the committed manifest is
  verifiable, not trusted. That determinism is what makes "CDN + committed
  manifest" a sufficient canonical record. Two limits on that rebuild claim:
  - **The kit tree tracks the newest staged version only.** There is one
    mutable kit tree and N immutable prefixes, so after a kit update
    `check_kit_parity.py --dir` against an OLDER version's manifest is
    *expected* to exit 1, naming exactly the files the update changed. That is
    not drift. The older tree state is recovered from git (the kit's config
    trio is tracked in `../competition_exdark/`) plus that version's committed
    anchor. Every staged prefix stays byte-verifiable against its own
    manifest, which is what participants and the downloader actually use.
  - **`part-09-root-labels.zip`'s archive sha256 is Windows-specific.**
    `_plan_shards` sorts `Path` objects, and `PurePath.__lt__` case-folds on
    Windows but compares bytewise on POSIX, so the two uppercase basenames
    (`LICENSE-ExDark.txt`, `README.md`) order differently and the zip's
    central directory differs. Rebuild on Windows to reproduce the archive
    hash, or verify with `check_kit_parity.py`, which compares `files[]`
    per path and is order-independent. The image shards are unaffected —
    every other basename is digits plus a lowercase extension.
- **Disaster recovery is the kit tree plus the committed manifest**, not a
  release asset. The kit tree lives in the workspace and parity is checked
  per-file with `scripts/check_kit_parity.py` against the committed manifest,
  which is the anchor. Do not publish a canonical zip of the tree as a
  recovery artifact: a zip of the tree is not byte-identical to the CDN
  shards — the shards are the deterministic build generated FROM the tree —
  so the two hash sets cannot be reconciled, and a zip sitting beside them
  invites the attempt.
- **The `kit-exdark-v1` tag is not a provenance anchor.** It resolves to a
  different commit locally than on `origin` (both lightweight, both on
  `port/0.2.x`), so it cannot answer "which kit-tree state was `v1` built
  from" — reconstruct that from the committed `v1` manifest against the kit
  tree in git, and never cite the tag. **Do not retag it:** CLAUDE.md §B
  forbids retagging outright, and here anyone who has fetched either side
  already has that commit cached under this name, so moving the ref turns a
  visible disagreement into a silent one. Nothing downstream depends on it —
  the verification anchor is the committed
  `kit/<competition_id>/<version>/manifest.json`, checked per-file by
  `scripts/check_kit_parity.py`, and the `v1` CDN prefix is immutable and
  still verifies against its own manifest.
- **This repo has no GitHub Release entries.** Do NOT create them for code
  tags: code versions are git tags only, and release entries would add a
  maintenance surface this repo deliberately does not have.

> **Ordering that must not be inverted:** a new version's CDN prefix has to be
> LIVE before the tag that ships `STARTER_KIT_VERSION = "<new>"` is pushed.
> `starter_kit_prefix()` resolves at download time with no fallback and
> `fetch_manifest` fails the job on a 404, so a tester who installs the new
> tag while the dev → prod sync is pending gets a hard failure on the Import
> tab — in the exact surface the change exists to improve.
>
> A superseded prefix stays in place for installs already pinned to it, and is
> never advertised once its successor is live.

### Staging to the CDN

Upload the version dir to the dev bucket. **The dev → prod sync is run by the
Hub team** — ask them to stage the one version prefix you just uploaded, and
name that prefix explicitly in the request.

- Verify after staging: HEAD returns `Accept-Ranges: bytes`, a `-r 0-1023`
  GET returns 206/1024 (the downloader's resume depends on ranges), and the
  manifest round-trips byte-identically through the CDN.

## Install shapes: a dev Hub and a tester are not the same machine

A fragment or code edit makes "the running install stale" on both, but what
un-stales it is different, and the word **reload** only applies to one of them.

| | Dev Hub on a **folder source** | Tester on a **tag install** |
|---|---|---|
| Where the code lives | the checkout (`plugin_dirs` names `<repo>\src`; the provisioned venv imports from there) | a copy in a managed venv under `<home>\.3lc-compute\managed-plugins\<id>\<version>\` |
| Registered by | `POST /api/admin/plugins/dirs` (JWT), or `plugin_dirs` in `settings.json` + restart, or `--plugin-dir` / `TLC_COMPUTE_EXTERNAL_PLUGIN_DIRS` at startup | the install API, recorded in `settings.json` under `installed_plugins` with its pip/git spec |
| Picks up a working-tree edit | **yes** — worker reload, next request respawns against the source | **no.** A reload re-imports the same copied files. Nothing in the checkout reaches it |
| To get a change in front of it | reload | tag → catalog → reinstall |

Load order settles the collision, and it is deliberate: `discover_plugins`
(`registry.py:545-577` on 0.2.1) runs built-ins, then configured external dirs,
then persistent external dirs, and **installed plugins last** — the comment says
"Runs last so a folder Source / in-tree plugin of the same id wins". So a folder
source shadows an installed plugin of the same id; **nothing has to be
uninstalled first.**

### Read the home the PROCESS has, not the home the docs name

A Hub environment's venv says which code runs the service. It never says which
home the service reads. A redirected home and `C:\Users\<user>` can both hold a
`.3lc-compute` with its own `settings.json`, `managed-plugins` tree and
`installed_plugins` list, and the two disagree freely: different plugin versions
installed, different `plugin_dirs`, different last-used dates. A version read
from an environment's name, or from the home its setup doc specifies, can
therefore be several tags off from what is actually running.

**Resolve the home from the running process.** On Windows, read the process's
own environment block (`USERPROFILE` / `LOCALAPPDATA`, plus any
`TLC_COMPUTE_PLUGIN_VENV_*` override, which names the exact venv the worker
spawns from). Then confirm by content: hash the `tlc_plugin_kaggle` in that
venv against the checkout, or grep it for a marker only the version in
question has.

### Consequences

- **A tag install pins a commit and nothing ages it**, so a dev Hub can drift
  silently. **PRETAG step: state which install shape the verification ran
  against, and for a tag install the version, read from the running process's
  home rather than from memory.**
- **"Stale" is not one fact.** Before telling anyone to reload, check which
  shape they are on: `plugin_dirs` naming the checkout means a folder source is
  registered; an `installed_plugins` entry for the id means a tag install. A
  reload on the second is not a harmless no-op - it kills the worker and wipes
  in-memory job state, and then changes nothing.
- **The worker imports from the managed venv, not from `plugin_dirs`.** A home
  can carry `<repo>\src` in `plugin_dirs` AND a tag install of the same id, and
  still run the tag install. Our `plugin.toml` sets `provision_extra = "kaggle"`,
  which takes the umbrella branch of `worker_spec.py`: the worker spawns with
  `cwd = <managed-plugins>\<id>` and a python resolved through
  `resolve_managed_python` (honouring `TLC_COMPUTE_PLUGIN_VENV_KAGGLE_EXDARK`),
  so `import tlc_plugin_kaggle` resolves from that venv's `site-packages` and
  the source tree is never on the worker's path. The running worker's command
  line names the managed venv's interpreter, with the checkout nowhere in it -
  read it there rather than inferring from what is registered.

## The catalog URLs

The Hub fetches catalog sources **unauthenticated**. Two URLs serve this repo's
catalog:

```
https://gist.githubusercontent.com/Rishikesh-Jadhav/926ead27a6a1ed6429cf86d1924a24ce/raw/catalog.json
https://raw.githubusercontent.com/3lc-ai/3lc-compute-plugin-kaggle/HEAD/catalog.json
```

The gist is the one README and TESTER_SETUP tell testers to paste, and the one
hubs in the field are already configured with, so step 3 above is not optional.
The raw URL is the repo's own file with no mirroring step; `HEAD` in it is
deliberate, following the default branch so the URL survives a branch rename.

Retiring the gist means publishing the raw URL in README, TESTER_SETUP and
here, mirroring the catalog one last time, and deleting the gist once no hub
points at it.
