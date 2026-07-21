# UI notes — Kaggle Competition plugin

Written 2026-07-21 during the Import-tab rebuild (v0.2.x, sessions 7+). The
stock **Import plugin** is the design and interaction reference: it is a Hub
built-in (`3lc-hub\.venv\Lib\site-packages\tlc_compute\plugins\importer\`),
not a separate repo — cite it from the installed source.

## Import tab — the six states

| State | Trigger | What renders |
|---|---|---|
| 1 Empty | No verified snapshot, no saved YAML path | Locked-format banner, form, splits placeholder, guide-pulse on the YAML field, button disabled |
| 2 Preflight | YAML input (500 ms debounce + blur/paste) → `GET /import/preflight` | Green "Detected …" line + locked split checkboxes, OR amber mismatch callout (per-problem remediation), OR red parse/path error. Form never cleared; button enables only on green |
| 3 In progress | `POST /import` → poll `GET /jobs/{id}` | Four stock-style rows (Import train/val/test, Validate (9 checks)) with QUEUED/RUNNING/COMPLETED badges, per-stage elapsed, indeterminate bar; "safe to navigate away" chip |
| 4 Success | Job completed | Green `alert-success` banner (Continue to Train →, Explore train/val/test, Start over), grouped checks, table summary rows, collapsed log accordion |
| 5 Failure | Job failed | Red `alert-error` banner, failed checks with ✕ + remediation hints, button becomes "Re-run Import & Validate", form stays populated |
| 6 Revisit | Tab open with verified snapshot | Straight into State 4 from `GET /import/state` (form hidden, Start over returns to State 1) |

Tab-open resolution order: **running import (reconnect) → verified snapshot
(revisit) → form**. The stepper checkmark and the revisit view share one
backend source of truth (`verified_import_state()`, also behind `/pipeline`),
so they can never disagree.

## Dev affordance — forcing states for screenshots

Append `?kgdev=<value>` to the plugin page URL (e.g.
`/plugin/kaggle?kgdev=state4`). Static fixtures render with **no fetches and
no job side effects**; the fixture re-applies after the async config load so
saved form values can't overwrite it. Remove the param (or use an unknown
value) to return to normal state resolution.

| Value | Renders |
|---|---|
| `state1` | Empty form (YAML cleared) |
| `state2` | Green preflight (5,910/733/715, canonical) |
| `state2-mismatch` | Amber callout (val 731≠733) **plus** the test-labels-on-disk GT-guard info note |
| `state2-error` | Red FileNotFoundError |
| `state3` | Mid-import: train COMPLETED, val RUNNING, test/validate QUEUED |
| `state4` | Success: val CREATED + train/test REUSED (shows Re-import fresh + slot alignment), GT-guard note, grouped checks, log |
| `state5` | Failure: val count 731 + GT-leak check failed, remediation hints, Re-run button |
| `state6` | Revisit view (form hidden, Start over) |

Caveat: the buttons in forced states are live — clicking "Import & Validate"
in `state2` would really POST (the backend re-validates, so it 400s or runs a
real import). Fine for an organizer machine; don't demo-click destructively.

## Intentional improvements over the stock Import plugin

- **Deterministic stale-job detection.** The stock plugin (and our earlier
  sessions) could poll a `running` record forever after a service restart.
  Every job record now carries its owning service **pid**; hot reloads keep
  the pid (worker threads survive them), only a restart changes it, so a
  running record with a foreign pid is *proof* of orphanhood — no timing
  window, no slow-disk misclassification. Detected on read, persisted once as
  `status: "stale"` with the decision appended to the job's own log
  (`jobs._mark_if_orphaned`).
- **Reconnect-on-load** (stock parity, but ours filters stale records): the
  "safe to navigate away" claim is backed by the disk-persisted job store at
  `~\.3lc-kaggle-plugin\jobs\`.
- **Single staged job** instead of the stock's three-jobs-per-split: the 9
  validation checks are cross-split and stay in one job; `run_import` reports
  stages (train/val/test/validate with timestamps) and the UI renders the
  same four-row presentation. Validation semantics untouched.
- **Explicit preflight feedback**: the stock auto-detect silently ignores
  errors; ours renders mismatch/error callouts with remediation copy.
- **Continue to Train →** actually advances the stepper — no stock analogue.
- **GT-leak guard visibility**: surfaced pre-import (preflight
  `test_labels_on_disk` note) and post-import (info note when the test table
  was built via the images-only TableWriter path) — never buried in the log.
- **Force re-import with a revision guard**: `force_splits` +
  `GET /import/revisions` lineage walk; the confirm dialog names the revision
  count, always confirms when the count is unknown, and skips the dialog only
  when provably zero.

## Design-fidelity notes (font/token audit, 2026-07-21)

Audited against the stock Import plugin fragment. The Hub's shared CSS
(main.css / plugin-common.css) lives in the **hosted frontend**, not on this
machine — the fragment-visible contract is CSS custom properties + shared
class names.

- **No `font-family` anywhere in our fragment** (matches stock). Body text
  inherits the Hub stack; monospace appears only via the log `<pre>`. Table
  paths render as plain muted text like the stock details strip.
- **No shared font-size/weight tokens exist** — the stock fragment hardcodes
  px sizes (10/11/12/13/14) and weights (500/600/700). We use the same
  values; a future Hub *font-size* theme change will not carry through for
  either plugin. This is the stock convention, not our invention.
- **Color/radius tokens used everywhere available**: `--text`,
  `--text-secondary`, `--text-muted`, `--border`, `--border-light`,
  `--accent`, `--accent-light`, `--success`, `--warning`, `--danger`,
  `--bg-card`, `--bg-secondary`, `--radius-lg`. Fallback literals match the
  stock plugin's own hardcodes: `#d97706` (warning), `#ef4444` (danger),
  `rgba(5,150,105,…)` (success tint), `rgba(239,68,68,…)` (danger tint),
  `rgba(217,119,6,…)` (warning tint), `rgba(42,74,97,…)` (accent tint).
- **Copied component CSS** (not importable — defined inside the stock
  fragment, not shared): `.format-selected-banner` (our locked banner; entry
  animation reimplemented as `kg-banner-in` since the stock `plugin-badge-in`
  keyframes live in shared CSS we can't verify) and the `guide-pulse`
  keyframes (verbatim).
- **Shared classes relied on**: `card`/`card-header`/`card-title`/
  `card-subtitle`/`card-body`, `form-group`/`form-label`/`form-control`/
  `form-help`, `btn` + `btn-primary`/`btn-secondary`/`btn-ghost` +
  `btn-sm`/`btn-lg`, `alert`/`alert-success`/`alert-error`/`alert-icon`,
  `badge badge-status-{queued,running,completed,failed}`,
  `plugin-progress-wrap`/`plugin-progress-bar indeterminate`, `spinner`,
  `divider`, `plugin-section-number`.
- **No Insights deep-links**: verified that neither `table_insights` nor
  `run_insights` reads any URL/query parameter — there is no clean deep-link
  scheme, so no Insights action is offered (per "skip rather than fake").

## Small-button vocabulary (row actions)

Matches the stock details strip: `btn btn-secondary btn-sm` for primary-ish
row links (Explore), `btn btn-ghost btn-sm` for quiet actions (Copy ⧉ with a
transient "Copied ✓"), and `kg-btn-danger-hover` (ghost + danger tint on
hover) for destructive-ish actions (Re-import fresh). The Re-import column is
a fixed-width slot so Copy/Explore stay aligned on rows without it —
CREATED rows deliberately carry no force action (a fresh import has nothing
to discard).
