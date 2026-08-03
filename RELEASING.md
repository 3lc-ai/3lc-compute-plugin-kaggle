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

Add a new entry to the `versions` array of the `kaggle` plugin (newest first):
bump `version`, point `source` at the new tag, and paste in a fresh copy of the
manifest (it must match the class attributes in
`src/tlc_plugin_kaggle/plugin.py` — `version` included). Bump `generated_at`.
Commit and push.

**The repo copy is the source of truth.** The gist (step 3) is only a mirror.

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

## Why the gist exists at all

The Hub fetches catalog sources **unauthenticated**, and this repo is private,
so `raw.githubusercontent.com` URLs on the repo return 404 (verified
2026-07-31). The public gist hosts only `catalog.json`; the install source
inside it still goes through git, which carries the tester's credentials —
hence the `git ls-remote` prerequisite in
[docs/TESTER_SETUP_0.2.md](docs/TESTER_SETUP_0.2.md).

**When the repo goes public:** retire the gist in favor of the repo's raw
`catalog.json` URL (update README, TESTER_SETUP, and this file), and drop the
git-token prerequisite from the tester docs. Tracked in the launch notes in
[docs/v1.1-ideas.md](docs/v1.1-ideas.md).
