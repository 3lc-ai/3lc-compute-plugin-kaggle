# v1.2.8 pre-tag checklist

Scope: the SDK-pin blocker fix (contract 0.1 → 0.3) + the `result()` call
shape + the bridge test layer. Rules: RELEASING.md order (tag → repo
catalog.json → gist mirror), never retag, `pytest` last thing before tagging.

**Epistemic status of the diagnosis (read before quoting it):** the root
cause was established by **source analysis and targeted experiments**, and
the fix verified by **live provisioning on a real PyPI-installed 3lc-compute
1.0.1 host** plus a **live SDK-0.3.2 worker smoke**. The reporter's own
failure was **NOT reproduced**: he runs the compute service from source on
main (newer than the published 1.0.1), was stopped by a pre-flight contract
warning, and never ran the plugin. Open info item for him below.

## Verified at review (2026-08-31, dev machine + scratch venvs)

- [x] **Contract map:** published hosts 3lc-compute 0.2.x → SDK contract
      0.1 · 0.4/0.5 → 0.2 · 0.6/1.0.x → 0.3 (`plugin-sdk>=0.3.1,<0.4`).
      The SDK repo's **main IS 0.3.2** (== tag v0.3.2, HEAD 27c1dc0); **no
      0.4 exists** as tag, branch, or on any index — so `>=0.3.1,<0.4.0`
      also covers a from-source main host, and a wider window would cross
      a breaking MAJOR.MINOR boundary by definition (the CI item in
      v1.1-ideas.md guards the day 0.4 appears).
- [x] **Why the stale pin kept "working":** uv (0.11.7) honors a **git
      source's own `[tool.uv]` indexes** — watched with `--no-cache`,
      PyPI-only CLI index: the v1.2.7 git requirement resolved SDK 0.1.1
      from the retired prereleases index baked into its pyproject. A real
      1.0.1 host **successfully provisioned v1.2.7** this way (SDK 0.1.1
      in the venv) — the stale contract shipped invisibly. As a
      bare/index/wheel requirement the old pin **fails** on PyPI-only
      hosts ("only 3lc-compute-plugin-sdk[shared]>=0.2.2 is available") —
      the planned wheel-source catalog would have hit this as a hard
      install failure.
- [x] **Positive, watched on the real 1.0.1 host:** `install_plugin` of
      the fixed tree (redirected home, `persist=False`) provisioned and
      registered `{id: kaggle-exdark, version: 1.2.8}` with **SDK 0.3.2
      in the venv**. (Worker boot from that exact venv hit a Windows
      path-length DLL artifact — the scratch home is ~170 chars deep,
      msgspec's DLL won't load past MAX_PATH; the standard
      `%USERPROFILE%\.3lc-compute\...` path is ~70 chars and unaffected.
      The worker surface itself is separately live-proven, next item.)
- [x] **Live worker smoke, SDK 0.3.2 serving this plugin** (scratch venv):
      `/health` = `{ok, plugin, sdk_version: 0.3.2}` (the exact handshake
      a 0.3-contract host wants), `/ui` (fragment intact + idempotent
      PluginJobs injection), `/config` 200, `/runs` 200, `/validate/train`
      400 with the participant-facing message.
- [x] **result() regression pinned by tests:** SDK 0.3.x renamed
      keyword-only `run_url=` → positional `url`; the bridge's try/except
      swallowed the TypeError (silent loss of the Queue panel's Open-run
      link — kgSwapText/F1 class). `tests/test_jobs_bridge.py` asserts
      events are RECEIVED by fakes carrying the real 0.3.x signatures;
      verified the suite **fails on the pre-fix jobs.py** (stash
      round-trip) and passes on the fix. Suite: **86 passed**.
- [x] **0.2.1 back-compat (dev machines):** the 0.2.1 host never reads
      `sdk_version` (zero occurrences), spawn CLI / dispatch NDJSON /
      cancel shapes are byte-identical across SDK 0.1.1 ↔ 0.3.2, and
      0.2.1 provisioning keeps PyPI primary — SDK 0.3.2 resolves.
- [x] Version bump 1.2.7 → 1.2.8 across pyproject (×2), plugin.toml,
      setup script `$PLUGIN_VER`, W1 path pins in TESTER_SETUP_0.2 /
      README, SMOKE_TEST footer expectation. Remaining `1.2.7` hits are
      historical feature tags only (verified by grep).

- [x] **Queue-panel Open-run link — VERIFIED through emit → host
      consume → host serve; frontend rendering is the one unverified
      hop (2026-08-31 smoke finding).** The full chain, each hop
      evidenced: the bridged `result()` fires (the smoke train job's
      record carries `facts.run_url`; call shape pinned by unit tests
      against the real 0.3.x signature) → the 0.2.1 host consumes the
      event (`job_manager.py:421-422`) → the host SERVES it (confirmed
      live on the dev Hub: the Queue API response carries
      `"run_url": "C:/Users/.../runs/kaggle_run_20260831_152527"` on
      job c8bd1d9a — while run-insights' entry in the same response has
      `run_url: null`; we are the ONLY plugin on this stack populating
      the field, which is why the render path had never been exercised).
      The remaining hop — the SaaS Hub frontend turning that value into
      a link — did not render, plausibly because the queue panel only
      links http(s) values and ours is a raw local run URL (the SDK
      contract's documented shape: "a run or a table URL"); see the CC1
      entry in v1.2-ideas.md for whether the shape or the frontend is
      the bug. NOT a regression vs v1.2.7 (the kwarg TypeError meant
      the event never reached the host at all). Post-tag tick: rendering
      on a 0.3-contract host.

## Open pre-tag items

- [ ] **Dev-Hub smoke (Rishikesh):** reload → Import revisit → short
      train → predict on the 0.2.1 dev Hub, installed from a local-clone
      catalog with the version's `source` pointed at the fix commit sha
      (the documented pre-tag pattern). This is the named residual risk:
      the 0.3.2 worker has not yet run under a live 0.2.1 supervisor.
      Fragment impact of this release: **venv re-provision** (dependency
      change) — a plain worker reload is NOT enough; uninstall/reinstall
      (or fresh install) so the venv re-resolves, then repoint the W1 env
      var to `...\kaggle-exdark\1.2.8\...` and hard-refresh the page.
      NOTE: a missing Open-run link on the Queue panel is NOT a smoke
      failure on this stack — see the stated gap above.
- [ ] **Info from the reporter (non-blocking, relayed by Rishikesh):**
      exact 3lc-compute main commit/version he runs, and the verbatim
      pre-flight warning text — to confirm main's gate reads the
      dependency pin (his phrasing suggests so; published 1.0.1 can only
      read a worker's /health `sdk_version`, which SDK 0.1.1 never sent).
- [ ] `pytest` green on the tag-candidate commit (86 as of the fix; rerun
      last thing).

## Post-tag verification (tick-only below this line; everything above is frozen at the tag)

- [ ] Tag `v1.2.8` pushed; repo catalog.json gains the 1.2.8 entry
      (manifest matches plugin.toml verbatim; source pins `@v1.2.8`);
      gist mirrored by Rishikesh; incognito-fetch the gist raw URL after
      the CDN lag.
- [ ] CONTEXT.md "Current release" sentence → v1.2.8 in the catalog
      commit (a statement about tags — it rides the post-tag catalog
      bump per RELEASING, not the pre-tag sweep).
- [ ] Footer reads v1.2.8 after a REAL catalog install; W1 env var
      repointed to the `1.2.8` venv path; hard refresh done.
- [ ] Config, job history, runs, checkpoints survive the update pass
      intact (spot-read ui_config.json + a jobs/ record).
- [ ] Reporter (from-source main host) installs v1.2.8 from the catalog:
      pre-flight warning gone, worker healthy, Import tab opens.
- [ ] Queue panel on the reporter's 0.3-contract host renders the
      Open-run link after a train job — the frontend-rendering half the
      0.2.1 stack cannot verify (see the stated gap above).
