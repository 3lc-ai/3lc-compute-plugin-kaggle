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

## Motion vocabulary (applies to all four tabs)

Piloted on the Import tab (2026-07-21). Future tab work references this
section instead of re-deciding. House-style anchors: the stock plugin's
`plugin-badge-in` entrance and `guide-pulse` — fast, subtle, ease-out. If an
animation would be noticed as "an animation" on the third use, it's too much.

**Tokens** — defined once on `.plugin-page-narrow`; every animated rule
references them (no literal durations except the stock-copied guide-pulse
2s cadence, which is house style outside the token scale):

```css
--kgl-motion-fast: 120ms;   /* button/hover feedback, badge swaps */
--kgl-motion-base: 180ms;   /* content entrances */
--kgl-motion-slow: 300ms;   /* accordion, checkmark draw */
--kgl-stagger: 30ms;        /* per-item cascade offset */
--kgl-ease-out: cubic-bezier(0.16, 1, 0.3, 1);
--kgl-ease-inout: cubic-bezier(0.65, 0, 0.35, 1);
```

**Rules:**

- **Motion is information.** Every animation announces a state change,
  acknowledges a user action, or directs attention to the next step. Nothing
  ambient, decorative, or page-level.
- **No exit animations.** Removals and replacements are instant; only
  arrivals animate. (Animating removals makes debounced re-checks feel
  laggy.)
- **No replay on revisit.** Entrances, cascades, and the checkmark draw play
  only when the state change happens live in the session. State 6 revisit
  and `?kgdev` forced states render everything static/pre-drawn. Same-type
  re-renders (debounce cycles, poll ticks) never re-trigger an entrance —
  animate on state-type *transitions*, tracked in JS.
- **Reduced motion.** Every animated rule lives inside a single
  `@media (prefers-reduced-motion: no-preference)` block; under `reduce`,
  all states change instantly with zero functional difference. JS that waits
  on `transitionend`/`animationend` must check `kgMotionOK()` first (a gated
  transition never fires its end event).
- **Performance.** Animate `opacity`/`transform` only; the accordion's
  `grid-template-rows` is the sole exception. JS cleanup rides
  `transitionend`/`animationend`, never timers; the one `offsetWidth` read
  in `kglEnter` is the standard single-shot animation restart, not a loop.

**Reusable pieces** (all in ui.html): `.kgl-enter` (entrance: fade +
4px slide-up), `.kgl-badge-in` (fast badge fade), `.kg-checks-grid.kgl-cascade`
+ per-item `--kgl-i` (parallel-column stagger), `kgCheckIcon(animate)` +
`.kgl-draw` (SVG stroke draw, success-only celebration beat, delayed one
fast beat after its banner), `.kgl-acc`/`.kgl-acc-summary` (button+region
accordion: `aria-expanded` + `hidden`, grid-rows expand, caret rotate),
`kglEnter(elm)` (re-triggerable entrance for persistent elements),
`kgSwapText(elm, text)` (fading label swap), `kgMotionOK()`.

Known out-of-scope literal: the shared `.kg-tab` header transition
(`all .15s`) predates the pass — tokenize it when the other tabs get their
motion treatment.

## Icons (applies to all four tabs)

Piloted on the Import tab + header (2026-07-21). **Deliberate deviation from
the stock plugin**: stock UIs use emoji (OS emoji font — colorful,
inconsistently sized, outside the color system); we replace every emoji and
typographic-symbol-as-icon with inline monochrome SVGs. No shared sprite
exists in the Hub (verified — stock plugins inline their own SVGs), so the
set lives in `ui.html` (`KG_ICONS` + `kgIcon(name, cls)` for JS-rendered
markup; literal `<svg>` for static markup).

- **Geometry**: 16px viewBox grid, 1.5px stroke, `stroke="currentColor"`,
  round caps/joins, lucide/feather-style. Never multicolor, never hardcoded
  hex — tint via the cascade or Hub CSS variables.
- **Sizes**: `.kgi` 14px inline-with-text default · `.kgi-16` CTA
  buttons/banner icons · `.kgi-12` micro contexts (chips, splits locks,
  accordion caret, trailing arrows inside small buttons, Loop separators) ·
  `.kgi-20` header identity. Note: small (`btn-sm`) buttons carry 14px/12px
  icons, not 16px — optical fit overrides the one-size-per-context rule
  there.
- **Alignment**: flex containers (`.kgi-btn` for buttons, flex callouts/
  checks/verdict rows), not baseline hacks.
- **Lock semantics**: the lock is muted gray (`--text-muted`) everywhere —
  locked is a calm fact, not a warning.
- **Set**: lock, check, x, check-circle, x-circle, alert-triangle, info,
  copy, arrow-right, upload, flag, refresh-cw, chevron-right, external-link.
- **Still emoji (pending their own passes)**: Train/Submit/Status tab
  internals (🔒 locked fields, ⚠, status emoji), the stepper's ✓/●/○ state
  glyphs (shared `renderPipeline`), and the sidebar manifest icon
  (host-rendered `icon_svg` already; the emoji `icon` is only a fallback).

## Copy tone (applies to all four tabs)

**Inform, don't instruct.** Help text and notes state facts and conventions
("`initial` is the convention for a first import") rather than commands
("leave as initial unless told otherwise"). Exceptions: remediation hints
under failed checks are deliberately imperative — instructions are their
job — and error chips may name the blocking fact ("the YAML path above
hasn't validated yet"). Sentence case for labels/buttons/callouts; terminal
periods on full sentences, none on fragments. "Import & Validate" keeps its
capitalization as an established CTA name.

## Small-button vocabulary (row actions)

Matches the stock details strip: `btn btn-secondary btn-sm` for primary-ish
row links (Explore), `btn btn-ghost btn-sm` for quiet actions (Copy ⧉ with a
transient "Copied ✓"), and `kg-btn-danger-hover` (ghost + danger tint on
hover) for destructive-ish actions (Re-import fresh). The Re-import column is
a fixed-width slot so Copy/Explore stay aligned on rows without it —
CREATED rows deliberately carry no force action (a fresh import has nothing
to discard).
