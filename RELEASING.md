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

(v1.2.1 renamed the plugin id `kaggle` → `kaggle-exdark`; the old id's catalog
entry was removed on purpose — keeping it would advertise a stale installable
card next to the renamed plugin. The catalog `id` must always equal the
`plugin.toml` id or the shop shows a phantom "available" card.)

**Version pins that must ride this same commit** — the catalog bump makes
every one of them stale the moment it lands (the version-pin class
finding, v1.1-ideas.md LAUNCH-VERIFY: the setup script shipped pinned at
1.2.2 across two releases because no list existed). Pins, not history —
audit docs, PRETAG checklists, and ideas files stay as written:

- `docs/TESTER_SETUP_0.2.md` — title line, round-1 migration note
  ("installs under `managed-plugins\kaggle-exdark\<version>\`"), §2 W1
  comment + env-var path, troubleshooting table W1 row.
- `scripts/setup-0.2-tester.ps1` — header "tested against" comment and
  the `$PLUGIN_VER` variable (single site since v1.2.7; the W1 path and
  the preflight both derive from it).
- `README.md` — the setup env-var line and the troubleshooting
  torch-check path.
- `CONTEXT.md` — the "Current release" sentence under **tags**.

Until the Phase C version-drift CI check exists the sweep is manual:
grep the tree for the OLD version string (`*.md`, `*.ps1`) and update
every hit that is a pin.

**The repo copy is the source of truth.** The gist (step 3) is only a mirror.

## PRETAG files freeze at their tag

`docs/PRETAG_<version>.md` is the record of what was verified before that
tag; a later edit makes it evidence of something other than what it claims.
Everything above the file's **Post-tag verification** section is FROZEN once
the tag exists. The one legitimate post-tag write is ticking that section
itself — its checks ("footer reads vX.Y.Z after a catalog install") cannot
exist before the tag. Tick-only appends there; never edit above the line.
(Codified 2026-08-27 after review flagged the v1.2.6 file's post-tag tick —
that edit was exactly this legitimate case, but the boundary was implicit.
PRETAG_1.2.7 onward makes it structural.)

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
the installed dist's own metadata (derived `__version__`; never a
hand-synced constant — a hardcoded copy shipped v1.2.3 with a v1.2.2
footer). A stale footer means a stale install or worker, not a cosmetic
glitch — and diagnostics blocks stamp this same version, so triage
trusts it. The version string is hand-synced in exactly three places:
pyproject.toml, plugin.toml, and the catalog manifest.

## Starter-kit data releases (separate from code releases)

The competition data ships through its own channel and its own rules. None
of the code-release steps above apply to it, and vice versa.

**The CDN prefix is the distribution.** `make_kit_manifest.py` generates
manifest.json + sharded zips into `cdn/<version>/`; the whole version dir is
staged to `competitions.3lc.ai/kaggle/<competition_id>/starter-kit/<version>/`
(the prefix `constants.starter_kit_prefix()` resolves). The downloader
verifies per-file sha256 from the manifest — never the HTTP ETag, because the
shards are multipart uploads whose ETags are `"<hash>-<parts>"` markers, not
content MD5s (verified at staging, 2026-08-27).

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
  manifest" a sufficient canonical record. Two limits on that rebuild claim,
  both established at the v2 build (2026-09-03):
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
    central directory differs. This was already true of v1 (whose `files[]`
    records normcase order). Rebuild on Windows to reproduce the archive
    hash, or verify with `check_kit_parity.py`, which compares `files[]`
    per path and is order-independent. The image shards are unaffected —
    every other basename is digits plus a lowercase extension.
- **Disaster recovery is the kit tree plus the committed manifest**, not a
  release asset. The `kit-exdark-v1` GitHub Release once carried
  `exdark_starter_kit_canonical.zip` (587 MB, sha256 `e84105db…`); it was
  **deleted 2026-09-02, before this repo went public**, with 0 recorded
  downloads. Recovery is unaffected: the kit tree survives in the workspace
  and parity is checked per-file with `scripts/check_kit_parity.py` against
  the committed manifest, which is the actual anchor. The **tag**
  `kit-exdark-v1` is kept — it marks the kit-tree state and costs nothing.
  Note the zip was never byte-identical to the CDN shards: the zip archived
  the tree, the shards are the deterministic build generated FROM it. Never
  try to reconcile those hashes.
- **This repo now has no GitHub Release entries at all.** Do NOT create them
  for code tags; code versions are git tags only, and release entries would
  add a maintenance surface this repo deliberately does not have.

> **The un-attributed-images blocker is CLOSED as of 2026-09-03** — v2 is
> built and `STARTER_KIT_VERSION` is `"v2"`. `v1` still serves 7,358 ExDark
> images with no `starter_kit/LICENSE-ExDark.txt` and is immutable by the rule
> above, so it is not fixed but superseded: `v2` carries the notice (1,502 B,
> sha256 `51340966…`) plus a README that attributes ExDark under BSD-3, cites
> Loh & Chan, licenses the organizers' own contributions CC BY 4.0, and drops
> the wrong "non-commercial" claim. **v1 must not be advertised once v2 is
> live**; leave the prefix in place for installs already pinned to it.
>
> **Ordering that must not be inverted:** the `v2` prefix has to be LIVE
> before the tag that ships `STARTER_KIT_VERSION = "v2"` is pushed.
> `starter_kit_prefix()` resolves at download time with no fallback and
> `fetch_manifest` fails the job on a 404, so a tester who installs the new
> tag while the dev → prod sync is pending gets a hard failure on the Import
> tab — in the exact surface the change exists to improve.

### Staging to the CDN

Upload the version dir to the dev bucket. **The dev → prod sync is run by the
Hub team** — ask them to stage the one version prefix you just uploaded, and
name that prefix explicitly in the request.

- Verify after staging: HEAD returns `Accept-Ranges: bytes`, a `-r 0-1023`
  GET returns 206/1024 (the downloader's resume depends on ranges), and the
  manifest round-trips byte-identically through the CDN.

## Why the gist exists at all

The Hub fetches catalog sources **unauthenticated**. While this repo was
private its `raw.githubusercontent.com` URLs returned 404 (verified
2026-07-31), so the catalog was mirrored to a public gist. That reason is now
spent: the repo is public and its own raw `catalog.json` URL serves
anonymously.

**The gist is therefore superseded**, and is kept only until the cutover lands
so that hubs already pointed at it keep resolving. Retiring it means
publishing the repo's raw `catalog.json` URL in README and TESTER_SETUP and
here, then deleting the gist once no hub is pointed at it.

**The cutover's precondition is now met.** It required the raw URL to serve
the CURRENT catalog. That was blocked while `develop` was the default branch,
because its `catalog.json` is stale (plugin id `kaggle`, newest 1.2.0) and a
raw URL serving an id that does not match the plugin id would fail every
install. The default branch is now `port/0.2.x`, which carries the live
catalog (id `kaggle-exdark`, through 1.2.9), so

```
https://raw.githubusercontent.com/3lc-ai/3lc-compute-plugin-kaggle/HEAD/catalog.json
```

resolves to it. `HEAD` is deliberate: it follows the default branch, so the
URL survives a future rename the way the gist URL does.

**The cutover itself is not done** — README and TESTER_SETUP still tell
testers to paste the gist URL, and hubs already configured with it must keep
resolving. Doing it means publishing the raw URL in those two docs and here,
mirroring the catalog one last time, then deleting the gist once no hub
points at it. Until then the gist stays authoritative for testers.
