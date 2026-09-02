# W5 empirical verification — 2026-09-02

Isolated throwaway env; the probe tree itself has been deleted. Raw logs and
the probe A reproducer stayed in the workspace, next to the other probe
artifacts: `../3lc-hub-next/w5_verification_logs/` (workspace, unversioned).
Ledger entries for W5 and W7 are in `../3lc-hub-next/PORT_PLAN.md`
(2026-09-02 addendum); W5's definition is in `CONTEXT.md`.

- venv: system Python 3.12.3 (W2 rule), `.venv/`
- home: `home/` via `USERPROFILE` / `LOCALAPPDATA` / `APPDATA` / `HOME`
- project root: 25 MB copy of `3lc-hub-next/home/AppData/Local/3LC/3LC/projects`
  (read-only source; the real 1.7 GB root was never touched)
- API key: byte-copied from the same isolated home, verified with `cmp -s`, never printed
- port: 5023 (`:5015` / `:5020` / `:5021` untouched)

## Probe A — library level, 3lc 3.3.0 (`../3lc-hub-next/w5_verification_logs/probe_a.log`)

| call | 3lc 3.1.0 | 3lc 3.3.0 |
|---|---|---|
| `TableIndexingTable.add_scan_url(object_type='table')` | accepted | ACCEPTED |
| `RunIndexingTable.add_scan_url(object_type='run')` | accepted | ACCEPTED |
| `ConfigIndexingTable.add_scan_url(object_type='configfile')` | **ValueError** | **ACCEPTED** |
| `ConfigIndexingTable.add_scan_url(object_type='config')` | accepted | ValueError |

**W5 is fixed in 3lc 3.3.0.** Mechanism (readable source — 3.3.0 is not
pyarmor-obfuscated, 3.1.0 was): `indexing_table.py::_upgrade_scan_url` compares
`scan_url["object_type"]` against `self.constrain_to_type.lower()`.
`ConfigIndexingTable.constrain_to_type` was renamed `Config` -> `ConfigFile`,
so `'configfile'` — exactly what tlc_compute 0.2.1 already sends — now matches.
The polarity simply inverted; `'config'` is now the rejected spelling.

Answers the Paul carry-forward: W5 was the **pinned pairing**, not the
public-examples bucket.

## Probe B — the 0.2.1 + 3.3.0 pairing (`probe_b1_unshimmed.err.log`, `probe_b2_shimmed.err.log` in the same folder)

Does not boot. Two structural breaks on tlc_compute 0.2.1's boot path, both
unrelated to W5:

1. `ModuleNotFoundError: No module named '_tlcsaas'` — `app.py:275` (and 269).
   3lc 3.1.0 shipped `_tlcsaas/` inside its own wheel (confirmed in
   `3lc-3.1.0.dist-info/RECORD`); 3.3.0 does not, in either the public PyPI
   build or the pypi.3lc.ai build.
2. After shimming (1): `ImportError: cannot import name
   'ActivateJwtOnApiKeyMiddleware' from 'tlc._service.authentication'` —
   `app.py:319`. 3.3.0's authentication module exports
   `BearerAuthMiddleware` / `BearerTokenAuthenticationMiddleware`; both
   `ActivateJwtOnApiKeyMiddleware` and `JwtAuthenticationMiddleware` are gone.

Stopped there (CLAUDE.md A2 circuit-breaker) rather than stubbing middleware —
past this point the observation would be an artifact of the shims, not evidence.

**The shim, for the record:** `_tlcsaas/` in the probe venv's site-packages, with
`ensure_key_activated()` -> None and `is_api_key()` -> True, both labelled as
probe stubs in-file. It exists only to reach `_on_startup`; it proves nothing
about compatibility. The startup never reached `_on_startup`, so the W5 line
itself was never exercised under a running 0.2.1 service.

## Consequence

The W5 fix is real but unreachable on our pinned stack. It arrives only with a
compute service built against 3lc 3.x-post-auth-refactor — `3lc-compute 0.3.0`
exists on `pypi.3lc.ai/public/repositories/prereleases-public/` and is the
obvious next probe (not run: outside the approved A+B scope).
