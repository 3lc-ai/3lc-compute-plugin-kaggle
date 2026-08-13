# UI playbook — Kaggle Competition plugin

The Import tab (frozen 2026-07-21) is the v1 gold standard. This document is
the **replication playbook**: a Train/Submit/Status tab session starts with
"apply the playbook" — the decisions below are settled, not re-litigated.
The stock **Import plugin** remains the interaction reference; it is a Hub
built-in (`3lc-hub\.venv\Lib\site-packages\tlc_compute\plugins\importer\`),
not a separate repo.

---

## 1. State-machine pattern

Every tab is a six-state machine:

| State | Trigger | Renders |
|---|---|---|
| 1 Empty | No verified snapshot, no saved inputs | Locked-constraint banner, form, placeholder panels, guide-pulse on the first required field, primary CTA disabled |
| 2 Preflight / gate | Debounced input (500 ms + blur/paste/Enter) → cheap read-only endpoint | Green summary + locked options, OR amber mismatch callout (per-problem remediation + Copy diagnostics), OR red parse error. Form never cleared; CTA enables only on green |
| 3 In progress | POST → poll job | Per-stage rows with QUEUED/RUNNING/COMPLETED badges, elapsed, indeterminate bar; "safe to navigate away" (honest: jobs are disk-persisted, UI reconnects on load, restart orphans come back `stale` via the pid check) |
| 4 Success | Job completed | Green `alert-success` banner (next-step primary action + deep links), verdict + grouped checks, summary rows, collapsed log accordion |
| 5 Failure | Job failed | Red `alert-error` banner + Copy diagnostics, failed checks with remediation, CTA becomes "Re-run …", form stays populated |
| 6 Revisit | Tab open with verified snapshot | Straight into State 4 (form hidden, Start over in the banner) |

**Tab-open resolution order**: running job (reconnect → State 3) → verified
snapshot (State 6→4) → form (State 1, saved inputs prefill and re-gate).
The stepper checkmark and the tab's revisit view must share one backend
source of truth so they can never disagree.

**Dev affordance**: `?kgdev=<state>` renders each state from static fixtures
— no fetches, no job side effects; fixtures re-apply after the async config
load. Import values: `state1`, `state2`, `state2-mismatch`, `state2-error`,
`state3`, `state4`, `state5`, `state6`. New tabs add their own values.
Since v1.1.1 fixture pages cannot start real work: the four job-firing
buttons (Import / Start Training / Run inference / Submit) render disabled
with a "demo state — actions disabled" note, the ready-recalc functions OR
in `kgDevMode` so no refetch re-enables them, and their click handlers (plus
Cancel) return early under `?kgdev` as the hard backstop.

## 2. Motion

House-style anchors: the stock plugin's `plugin-badge-in` entrance and
`guide-pulse` — fast, subtle, ease-out. If an animation would be noticed as
"an animation" on the third use, it's too much.

**Tokens** — defined once on `.plugin-page-narrow`; every animated rule
references them (no literal durations; exceptions: the stock-copied
guide-pulse 2s cadence, and JS *hold* durations like the 1200 ms Copied swap
and the 2 s Reconnected hold, which are UX timing, not animation):

```css
--kgl-motion-fast: 120ms;   /* button/hover feedback, badge swaps */
--kgl-motion-base: 180ms;   /* content entrances */
--kgl-motion-slow: 300ms;   /* accordion, checkmark draw */
--kgl-stagger: 30ms;        /* per-item cascade offset */
--kgl-ease-out: cubic-bezier(0.16, 1, 0.3, 1);
--kgl-ease-inout: cubic-bezier(0.65, 0, 0.35, 1);
```

**The four rules:**

1. **Motion is information** — announce a state change, acknowledge an
   action, or direct attention. Nothing ambient, decorative, or page-level.
2. **No exit animations** — removals/replacements are instant; only arrivals
   animate. (One sanctioned exception: the connection guard's "Reconnected"
   banner fades out after its hold — transient status, not content.)
3. **No replay on revisit** — entrances, cascades, and the checkmark draw
   play only on live state changes. Revisit and `?kgdev` render static/
   pre-drawn. Same-type re-renders (debounce cycles, poll ticks) never
   re-trigger an entrance: animate on state-type *transitions*, tracked in
   JS (`kgPreflightKind`, `kgPrevStageStatus`).
4. **Reduced-motion parity** — every animated rule lives inside one
   `@media (prefers-reduced-motion: no-preference)` block; under `reduce`
   everything is instant with zero functional difference. JS that waits on
   `transitionend`/`animationend` must check `kgMotionOK()` first (a gated
   transition never fires its end event).

**Performance**: animate `opacity`/`transform` only; the accordion's
`grid-template-rows` is the sole exception. Cleanup rides end-events, never
timers; the single `offsetWidth` read in `kglEnter` is the standard
animation restart, not a loop.

## 3. Icons

**No emoji, ever** (deliberate upgrade over stock). Inline monochrome SVGs:
16px viewBox grid, 1.5px stroke, `stroke="currentColor"`, round caps/joins,
lucide-style. Tint via the cascade or Hub CSS variables — never hardcoded
hex, never multicolor. No shared sprite exists in the Hub (verified), so the
set lives in the fragment: `KG_ICONS` + `kgIcon(name, cls)` for JS-rendered
markup, literal `<svg>` for static markup.

- **Sizes**: `.kgi` 14px inline default · `.kgi-16` CTA/banner · `.kgi-12`
  micro (chips, locks, caret, trailing arrows in small buttons, separators)
  · `.kgi-20` header identity. Small buttons carry 14/12px icons — optical
  fit overrides the scale rule there.
- **Alignment**: flex containers (`.kgi-btn`, flex callouts/checks), not
  baseline hacks.
- **Lock semantics**: muted gray always — locked is a calm fact, not a
  warning.
- **Set**: lock, check, x, check-circle, x-circle, alert-triangle, info,
  copy, arrow-right, upload, flag, refresh-cw, chevron-right, external-link.

## 4. Copy tone

**Inform, don't instruct.** Help text states facts and conventions
("`initial` is the convention for a first import"), not commands. Exceptions:
remediation hints under failed checks are deliberately imperative —
instructions are their job — and error chips may name the blocking fact.
Sentence case for labels/buttons/callouts; terminal periods on full
sentences, none on fragments. "Import & Validate" keeps its capitalization
as an established CTA name.

**No em dashes in UI copy** (en dashes included). Rewrite the sentence
instead: period + new sentence, a comma, or parentheses — whichever reads
naturally case by case, never a blind character swap. Numeric ranges read
"1 to 300", not "1–300". Scope is rendered copy (labels, help, callouts,
titles, banners, state chips); log OUTPUT and the diagnostics fence keep
their log formatting.

## 5. Checks / results presentation

- **Verdict line first**: muted headline over the columns — check-circle
  "9/9 checks passed" or x-circle "7/9 checks passed — 2 failed".
- **Two-column grouped grid** with uppercase micro-label group heads;
  columns cascade in parallel on live completion only.
- **Compress on pass**: drop parentheticals that merely echo the assertion
  ("row count == 5910 (got 5910)" → "train row count · 5,910"); keep details
  that add information (class sample, example stem, schema note).
- **Expand on fail**: full expected-vs-got plus a one-line italic remediation
  hint (`KG_REMEDIES`, matched by label).
- **Thousands separators everywhere** (`fmtCount`), matching the Dashboard.
- **Raw log** lives in a collapsed "Show log" accordion (button + region,
  `aria-expanded` + `hidden`) — the only monospace anywhere, collapsed by
  default in every state.
- **Guard notes** (e.g. GT-leak) surface as info callouts in the results,
  never buried in the log.

## 6. Button vocabulary

- **Primary CTA**: `btn btn-primary btn-lg kgi-btn` with a 16px leading icon
  (upload for Import; refresh-cw when the label flips to "Re-run …").
- **Banner primary**: `btn btn-primary btn-sm kgi-btn` with trailing
  arrow-right (the "advance the stepper" action).
- **Secondary**: `btn btn-secondary btn-sm` (Explore links, Copy
  diagnostics).
- **Ghost/quiet**: `btn btn-ghost btn-sm` (icon-only Copy — needs
  `aria-label`; Start over).
- **Destructive-ish**: ghost + `.kg-btn-danger-hover` (danger tint on hover
  only; e.g. Re-import fresh) — never equal visual weight with navigation.
- Transient acknowledgment: `kgSwapHtml(btn, icon+label)` → hold → swap
  back. Fixed-width action slots keep columns aligned when an action is
  conditionally absent.

## 7. Shared utilities inventory (all in ui.html)

| Utility | One-line usage |
|---|---|
| `kgMotionOK()` | Live `prefers-reduced-motion` check; gate any JS that waits on animation/transition end-events |
| `kglEnter(elm)` | Re-triggerable entrance for a persistent element (fresh innerHTML embeds `kgl-enter` in markup instead) |
| `kgSwapHtml(elm, html)` | Fading label swap on buttons (instant under reduce); relies on the gated opacity transition |
| `kgSwapText(elm, text)` | Fading text swap for stat values; no-op when unchanged, so poll ticks never blink. Needs a gated opacity transition on the element |
| `kgConn.fail(err, resume?)` | Connection guard: returns true iff network-level (TypeError); shows retrying banner in EVERY finished tab's `*-conn-banner` slot (one guard, one state), backoff 2/5/10/15s pings, fires `resume` on reconnect (resume polls/preflights/gates — never imports/trains/submits) |
| `kgBuildDiagnosticsCore(sections)` | Fenced ```3lc-kaggle-diagnostics``` block: version/OS/time header + caller sections (falsy sections skipped — no placeholders). Per-tab builders compose it: `kgBuildDiagnostics` (Import: yaml, preflight JSON, checks, log tail), `trBuildDiagnostics` (Train: job id, HP set, provenance, log tail) |
| `kgChecksSection(title, checks)` / `kgLogTailSection(logEl)` | Reusable diagnostics sections (PASS/FAIL lines; last-40-lines log tail) |
| `kgDiagBtn()` / `kgBindDiag(el, build?)` | Copy-diagnostics button on every failure surface; `build` picks the tab's builder (default Import's) |
| `kgBindAccordion(toggleId, panelId)` | Button + region accordion (aria-expanded / hidden, animated grid-rows); serves log accordions AND advanced disclosures |
| `kgAccOpenInstant(toggleId, panelId)` | Open a disclosure with zero motion (page furniture on load) |
| `kgSparkline(values, w?, h?)` | Tiny inline SVG polyline, no axes/library; one point renders as a dot, flat series renders mid-height |
| `kgBindTablePicker(inputId, popId, btnId, onPick)` | Revision-picker popover on a table-URL field (fresh `/tables/list` per open, Escape/outside-click close, focus back to the button); `onPick(url, isLatest)` re-runs the field's gate |
| `kgTableRef(url)` | `dataset/revision` display name parsed from a table URL |
| `kgScrollTo(elm)` | Attention scroll: only when out of view, only on live events, smooth/instant per motion |
| `kgCleanYamlPath(v)` | Copy-as-path quote/trailing-separator tolerance; field rewritten so what runs is what's shown (folder→file resolution is server-side) |
| `kgIcon(name, cls)` | Inline SVG from the icon set |
| `kgClassTint(i)` | Class-index tint (background + border) from the Hub `--chart-N` palette |
| `esc(s)` / `fmtCount(n)` / `midTrunc(s, max)` / `fmtDur(s)` | Escaping, thousands separators, middle truncation, elapsed formatting |
| `kgBindCopy(el)` | data-copy buttons with transient Copied state and prompt() fallback |

## 8. Layout rules

- **Two-column balance**: form fields left, options/at-a-glance right; the
  right column must earn its height (e.g. "Dataset at a glance" after a
  green gate — stats chips + quiet tags + relocated guard note).
- **Narrow widths** (≤720px): form and checks collapse to one column; table
  rows wrap with the path on its own line; actions keep right alignment.
- **Callout geometry**: one internal shape everywhere — icon column + text,
  `padding: 9px 12px`, `radius-lg`, flex `gap: 8px`.
- **Class-tag palette**: the Hub frontend's categorical CSS variables
  `--chart-1` … `--chart-12` (the set stock run_insights colors from), class
  index → slot, rendered as a quiet tint (`rgba(hue, .10)` background,
  `.35` border, text unchanged). Fallback hexes are the stock plugin's own.
  Chosen over a local palette (decided 2026-07-21): it's the only
  deterministic Hub-shared assignment reachable from a fragment — tlc value
  maps support `display_color` but the imported tables carry none, and the
  Dashboard's bounding-box palette lives in its own bundle, so exact
  Dashboard-overlay parity is plausible-but-unverified.
- **Overflow**: cards never exceed their container — `min-width: 0`,
  `word-break: break-all` on paths/`pre`; full paths only in the log/Copy.
- Nothing within 4px of a container edge that isn't deliberately flush.

## 9. Train-tab additions to the vocabulary (2026-07-21)

Patterns the Train session added; Submit/Status sessions inherit them.

- **Locked-contract banner + locked rows**: constraints render as the
  format-banner geometry (lock icon, one-line contract, enforcement
  sentence) with read-only `.kg-locked-row`s under it — never
  fake-editable disabled inputs. Locks are calm facts: muted gray.
- **Staged sections**: `.kg-sec-head` uppercase micro-heads + `divider`s
  replace any wall-of-fields; core fields prominent, everything most
  users keep on defaults goes into a collapsed **advanced disclosure**
  (`kgBindAccordion`, same mechanics as the log accordion). A saved
  config with non-default advanced values reopens its disclosure on load
  (instant — page furniture never animates).
- **Gate pattern**: cheap read-only existence checks (reuse
  `/import/revisions`) gate the primary CTA; green is a quiet
  `.kg-preflight-ok` line, missing is an amber callout with per-item
  problems and a cross-tab remediation action ("Go to Import"). Kind
  transitions animate; same-outcome re-checks don't.
- **Inline bounds**: client mirrors of server bounds render red under
  the field on blur (`.kg-field-err` in a `.kg-field-slot`), same
  message shape as the server; fixing clears on input; CTA disabled
  while any field is invalid.
- **In-run view**: header row (run name · status badge · Epoch n/N ·
  elapsed · remaining, recomputed every poll per the ETA recompute rule
  in CONTEXT.md) + determinate per-epoch bar (indeterminate
  only during epoch 0) + **metrics strip** (stat chips + `kgSparkline`,
  values via `kgSwapText`). Structure builds once; values swap in place —
  nothing re-enters on poll ticks. Cancel confirms (cooperative) and
  stays in the action row: one destructive control, not duplicated in
  the header.
- **In-run reconnect**: tab-open resolution fetches `jobs?kind=<tab>`;
  a running record reconnects straight into the in-run view (pid check
  makes restart orphans arrive `stale`, never `running`); newest
  terminal record renders its static summary (completed hides the form
  behind "Start new run"; failed/stale keep the form + Re-run CTA;
  cancelled keeps the form + info callout); else the form. Mid-run
  disconnects show "Connection lost. Training continues on the host."
  and the guard resumes polling on reconnect — never restarts anything.
- **Provenance panel**: the run-record assertions render as verdict +
  checks ("Verified provenance recorded" / group head "Provenance
  verified") the moment the record carries them; cascade on live
  arrival only. Four assertions since the 2026-07-22 contract change
  (model / imgsz / pretrained / checkpoint sha256). Screenshot target
  for the README — the hash line is the new centerpiece.

## 10. Predict + Submit additions to the vocabulary (2026-07-21)

- **Two-step gated flow**: when one card mixes a free, repeatable action
  with a costly one, split it into stages gated left to right. Step 1's
  results panel is the *decision surface* (verdict + checks, sanity
  card, hero stat, artifact row); Step 2 stays `.kg-step-muted` (plus
  real `disabled` attributes — the muting is visual, the gate is real)
  until a validated artifact exists, and names its **basis** explicitly
  ("Submitting: <run> · predicted 3m ago · local mAP 0.64"), with
  "(from a previous session)" when it came from the snapshot. Costly
  actions get a lightweight confirm that states the price ("This spends
  1 of your 3 daily submissions."). Budgets render in the connection
  card ("2 of 3 submissions left today"); an exhausted budget disables
  the action with the friendly reset note while the free artifacts
  (Download CSV) stay reachable. This structure superseded the
  "Generate CSV only" checkbox: the CSV exists after step 1 by
  construction, so an option to *not* do step 2 is no longer a mode —
  it's just not clicking step 2.
- **Segmented either/or**: two mutually exclusive input sources render
  as a `.kg-seg` toggle showing exactly one input; switching sides
  clears the other. No more two-fields-side-by-side ambiguity.
- **Hero stat**: one number the user came for (`.kg-hero`), large
  numeral + micro-label + muted scope note ("Host-only preview, not the
  leaderboard"). Render it only when the number exists — absence is the
  participant-machine behavior, not an empty state.
- **Revision picker**: table-URL fields carry a trailing layers-icon
  button opening a `.kg-pop` popover of the project's tables and their
  lineage-ordered revision chains (rows + LATEST badge + row counts,
  from `/tables/list`). Picking writes the URL and re-runs the gate;
  raw URL entry stays the escape hatch. Interplay with "Use latest
  revision": picking a non-latest revision unchecks it, re-checking
  re-implies latest, and the gate's green line echoes the resolution
  ("trains on the latest revision of each" vs "trains on these exact
  revisions"). This is the fix-labels-then-retrain loop made tangible.
- **Batch-determinate training bar**: overall fraction =
  (epochs_done + batch_i/batch_n) / total_epochs from the trainer's
  throttled batch counter; indeterminate only for the brief moment
  before the first batch progress lands.

## 11. Status-tab + v1-final additions to the vocabulary (2026-07-21)

- **Hero strip**: a status surface answers three questions at a glance
  (how good is my best · what happened last · what can I do now) as
  `.kg-hero` blocks — headline number 4dp with its source beneath,
  relative time + badge for latest activity, budget, and a "Live now"
  block that is OMITTED when nothing runs (never an empty placeholder).
- **Outcome vocabulary**: history rows speak participant language, not
  job states — "Submitted · #ref" (quiet mono id), "CSV generated (not
  submitted / daily limit reached / not joined)", "Validation failed";
  raw reasons ride the row's title attribute. Δ is visual (tinted ▲/▼,
  muted – for flat/first) and measured against the previous SCORED row.
  Paths never render in tables; icon actions (copy, download) carry
  them. The ▲/▼/– data glyphs are spec'd markers, exempt from the
  no-dash prose rule.
- **Friendly degradation for third-party API failures**: a known
  limitation renders as a quiet info callout naming the limitation and
  the working alternative (external link), with the raw error behind a
  collapsed "Show details" accordion — never an error tone for
  something that isn't the participant's fault. The code path keeps
  trying the API, so the success path self-heals at public launch.
- **Freshness rules**: every tab refetches its backing data on
  activation, silently (the stepper re-renders on every switch); a
  poll's terminal branch directly refreshes any list it invalidates
  (stale-on-terminal, plain function calls — no event bus); surfaces
  that watch a moving target poll while visible (Status: 15s, ticks
  skip when `document.hidden`, immediate refresh on visibility return,
  stopped on tab switch) with an "Updated Ns ago" line; manual refresh
  is a ghost refresh-cw icon button spinning on `--kgl-motion-spin`
  while in flight. Popovers that fetch per open (revision picker) are
  fresh by construction.
- **Tooltip pattern**: native `title` attributes (the Hub exposes no
  shared tooltip component to fragments). Every lock icon carries its
  one-line "why locked" reason; every truncated path carries its full
  value; relative times carry the absolute timestamp (`kgWhenSpan`).
- **Duration-hint pattern**: when prior completed runs exist, a muted
  help line under the cost-driving field states the median historical
  rate and the projected total, recomputed live as the field changes;
  omitted entirely without history.
- **aria-live rule**: announce meaningful transitions, not poll ticks —
  the epoch counter is a polite region (it only changes at epoch
  boundaries), fast counters get a visually-hidden announcer throttled
  to quartiles, and terminal banners announce via the existing focus
  move. State chips are polite regions.
- **Version footer**: every tab ends with one muted 11px line — plugin
  name + version (from `/config` `_meta`) + GitHub/Docs links
  (git-branch glyph; the stroke set carries no brand marks).
- **Document-title nudge**: "⟳ N% — <title>" while a job runs,
  non-fighting (prefix added only when absent; only our own prefix
  stripped on terminal).
- **Load order**: the initial `showTab` and all tab-open resolutions
  run in the end-of-script dispatch, after every section's state
  exists — tab-enter hooks must never run mid-eval.

### Deferred-ledger disposition (v1 close-out)

- Stepper glyph pass — DONE (icon-set SVGs; the filled active dot is
  the one sanctioned `fill`, like the sparkline point).
- Train/Submit/Status emoji + type/motion/copy retrofit — DONE.
- `.kg-tab` transition tokenization — DONE (inside the motion gate).
- File-browse endpoint, recent-paths dropdown — deferred to
  `docs/v1.1-ideas.md` with reasoning.

## 12. v1 definition of done

Every tab guarantees: a full six-state machine (empty → gated →
in-progress → terminal → revisit-first) resolved at tab-open from
disk-persisted, pid-checked job records, with `?kgdev` fixtures for
every state; motion that only informs (tokenized durations, entrances
on state-type transitions only, no exit animations, no replay on
revisit, full reduced-motion parity); one monochrome 16px stroke icon
set with zero emoji in rendered UI; copy that informs rather than
instructs, in participant language, with no em dashes outside logs and
diagnostics fences; keyboard reachability with visible focus, labeled
icon buttons, and throttled aria-live progress; and resilience — a
connection guard that owns network failures and resumes polling without
ever auto-restarting work, Copy-diagnostics on every failure surface
(version-stamped), friendly degradation for third-party API failures,
and data that refreshes on tab activation so the UI never needs a
manual reload to tell the truth. That is the bar for anything that
ships after v1.

## 13. Contract repositioning (2026-07-22)

The from-scratch rule is retired. The locked contract is now **YOLOv11n
from the official COCO-pretrained checkpoint (plugin-managed,
sha256-pinned) at 640px** — identical starting weights for every
participant; the recorded hash is the proof. Rationale: a ~0.005
epoch-10 start demoralizes; a ~0.70 start with room to climb keeps the
competition approachable, and fairness is preserved by pinning the
init. Provenance now proves "trained through the verified pipeline
under the locked contract", not "random init". All playbook rules
stand unchanged.

UI consequences: header chip "YOLOv11n · COCO-pretrained · 640px";
Train stepper subtitle "YOLOv11n, pinned init"; contract panel gains an
Init row (yolo11n.pt · sha256 prefix); Epochs default 20 with
pretrained-calibrated help (~0.70 by epoch 10; productive range 10 to
50); the in-run `tr-run-note` slot now renders the backend's
checkpoint-fetch stage note at epoch 0 instead of the retired near-zero
expectation line; provenance panel has four assertions.

The **host-only pattern** (render only when the local-scoring file
check passes, absence is the participant behavior) now also covers the
Weights-file source: participants get a single Plugin-run source with
no toggle, and the server rejects direct weights paths from
non-host machines, so the gate is real, not visual. Legacy
from-scratch runs render truthfully everywhere ("from-scratch ·
legacy") and remain predictable/submittable — no data migration.

## 14. Session projections (v1.2.6)

One canonical **session object** (`kgSession`, persisted as the `session`
key in `ui_config.json`) owns every fact tabs share: project name, table
name, dataset yaml, device, the slug decision, and explicit per-field
table-URL overrides. The rules, settled like everything else here:

- **Tabs render projections; no tab owns a default.** The fragment holds
  ZERO default literals — `GET /config` always serves a populated session
  (server fills from `constants.py`, the single definition site), plus
  `_meta.default_slug`. The Import form is the session's *editor*, not a
  store; Train renders the project as a read-only locked-row fact.
- **Derive, don't store.** Table-URL fields render from
  `kgApplyDerivedUrls` (override verbatim, else the canonical derivation
  for the session project + table). Derived values are never persisted. A
  settled user edit or revision pick IS an explicit per-field override; an
  emptied field returns to derivation; a settled project/table change
  clears all overrides and re-runs the gates. Anything else rendered from
  session values (e.g. the Loop's fix-labels href) re-renders inside the
  same funnel — a session-derived value with its own render moment is the
  bug class this section exists to prevent.
- **Sequence the load.** Tab-entry hooks and the initial tab-open
  resolutions await `configLoaded`; `showTab` paints immediately
  (stateless). `configLoaded` always resolves and is never silent: network
  failures retry through the connection guard, non-network failures render
  an explicit "saved settings could not be loaded" callout.
- **Config writers are user-action-initiated ONLY.** The sole read-path
  write in the plugin is the marker-guarded one-shot migration in
  `config_store.load()`. Current complete writer list (v1.2.6):
  `kgSetUrlOverride` (URL edit/pick), `kgImportCfgSettled` (Import form
  settle + import start), the device blur handler, the slug blur handler,
  and the three whole-tab action saves (train start, predict click, submit
  click). **A `saveTabConfig`/`kgSessionSave` call reachable from a
  render, sync, poll, or tab-enter path is a regression of the v1.2.5
  cross-project-mixture class** — the store rejects retired keys (400) but
  cannot reject a bad moment; this rule is the guard for that.

---

## Appendix — Import-tab reference

### ?kgdev fixture map

| Value | Renders |
|---|---|
| `state1` | Empty form (YAML cleared) |
| `state2` | Green preflight (5,910/733/715, canonical) + glance card |
| `state2-mismatch` | Amber callout (val 731≠733) + GT-note demo beat + Copy diagnostics |
| `state2-error` | Red FileNotFoundError |
| `state3` | Mid-import: train COMPLETED, val RUNNING, rest QUEUED |
| `state4` | Success: val CREATED + train/test REUSED, GT-guard note, grouped checks, log |
| `state5` | Failure: val count + GT-leak failed, remediation, Re-run CTA, Copy diagnostics |
| `state6` | Revisit (form hidden, Start over) |

### ?kgdev fixture map — Train tab

| Value | Renders |
|---|---|
| `train-state1` | Empty form (URLs cleared), gate hint, Start disabled |
| `train-state2` | Gate green ("Tables verified: exdark_train · exdark_val"), Start enabled |
| `train-state2-missing` | Amber gate (val table missing) + Go to Import, Start disabled |
| `train-state2-invalid` | Gate green + epochs 999 inline bounds error, Start disabled |
| `train-state3` | In-run: epoch 12/50, determinate bar, metrics strip + sparklines (12-point deterministic curve), ETA, Cancel enabled |
| `train-state4` | Live success: banner (pre-drawn check), weights + copy, Continue to Submit, provenance panel, form visible |
| `train-state5` | Failure: CUDA-OOM banner + Copy diagnostics, epoch 7/50 static, Re-run CTA, form visible |
| `train-state6` | Revisit summary: form hidden, static strip + provenance, Start new run |

### ?kgdev fixture map — Status tab

| Value | Renders |
|---|---|
| `status-empty` | Hero degrades ("no scores yet" / "no activity yet"), empty-state callout + Go to Train, not-connected Kaggle callout |
| `status-history` | Rich mixed history: submitted/#ref, limit-reached, validation-failed, csv-only smoke row; Δ both directions + unscored row |
| `status-live-running` | "Live now · Training · Epoch 12/50" hero block with Open-tab link |
| `status-kaggle-live` | Simulated API success: submissions table with public scores, best public, rank |
| `status-kaggle-403` | Friendly-degradation callout + View leaderboard link + Show details accordion with the raw 403s |

### ?kgdev fixture map — Predict + Submit tab

| Value | Renders |
|---|---|
| `submit-state1` | Empty: no runs, no table, gate hint, both steps locked |
| `submit-gated` | Runs + table verified, Run inference enabled, step 2 muted |
| `submit-inference` | In-progress: determinate 312/715 bar, elapsed, state chip |
| `submit-results` | Healthy results panel: 5/5 checks, sanity card + tinted tags, hero 0.6402, CSV row; step 2 unlocked (2 of 3 left) |
| `submit-results-low` | Same, but degenerate output: amber low-boxes callout, hero 0.0512 |
| `submit-checks-fail` | Predict failed at validation: 1/2 checks, failure banner + diagnostics, Re-run CTA |
| `submit-nokaggle` | Results + not-joined connection (amber, join link), submit disabled |
| `submit-limit` | Results + 0 of 3 left: friendly reset note, submit disabled, Download stays |
| `submit-success` | Submitted banner (pre-drawn check, ref 54861736, View on Kaggle, Continue to Status) |
| `submit-fail` | Submission rejected: red banner + Copy diagnostics |
| `submit-revisit` | Revisit-first: static results summary + submitted callout + New prediction |
| `submit-participant` | Participant view: no Weights-file toggle (host=false), single Plugin-run source, gated-ready |
| `predict-legacy-run` | A pre-repositioning from-scratch run selected: "from-scratch · legacy" summary tag + legacy note, still submittable |

The dev dispatch runs at the END of the fragment script so forced states
apply after every tab's vars and handlers exist; fixtures re-apply after
the async config load, and the metric curve is deterministic (no
randomness — identical screenshots every load).

**Fixtures always render the participant experience** (2026-07-24). While
`?kgdev` is active, host-only affordances stay hidden regardless of the
live `_meta.host` flag — no fixture opts into host rendering today. Four
enforcement points in the fragment: the config-load reveal of
`ps-src-seg` requires `!kgDevMode` (the markup default is `hidden`, so
nothing can reveal it in a fixture); `psSetSource` coerces `'weights'` to
`'run'` under `?kgdev`, so the external-weights field and its amber
callout can never render in a fixture; the eager `psLoadRuns()` is
skipped under `?kgdev`, so the live host's real runs never race a
fixture's dev runs into the selector; and the page-load live fetches —
the Kaggle connection probe and the two table-URL derivation chains —
are `kgDevMode`-guarded (v1.2.6, the H1 fix), because their responses
land AFTER the fixture's post-config re-apply and would overwrite fixture
state with live state (the connection one rendered the real account
handle over the fixture's `participant`). Fixtures never write config
(`kgSessionSave`/`saveTabConfig` guard on `kgDevMode` / fire only on
action-button clicks), and a plain load without the param takes none of
these paths — the host view and saved config come back untouched.

Two page-load fetches stay deliberately live under `?kgdev`: `GET
/config` (fixtures re-apply after it; it carries the `_meta` version the
footer and diagnostics stamp) and the stepper's `/pipeline` render riding
`showTab` (long-standing; read-only; means a fixture page's stepper shows
the machine's real progress — flagged to the Phase C runtime check to
decide). Interaction-driven read-only fetches (typing into a gate field,
opening the revision picker) are outside the render-purity rule; the
job-firing backstops still hold.

### Intentional improvements over the stock Import plugin

- **Pid-stamped stale-job detection**: running records from a dead process
  are proof-of-orphan (hot reloads keep the pid), marked `stale` on read
  with the decision logged — no timing heuristics, no slow-disk
  misclassification.
- **Single staged job** instead of stock's three-per-split: the 9 checks are
  cross-split and stay in one job; `run_import` reports stages, the UI
  renders the same four-row presentation.
- **Explicit preflight feedback** (stock silently ignores errors), including
  stat-level unreadable-file counts (half-extracted-kit detection) and
  folder/quote path tolerance.
- **Continue to Train** actually advances the stepper — no stock analogue.
- **GT-leak guard visibility** pre-import (preflight flag) and post-import
  (info callout).
- **Force re-import with a revision guard**: lineage-walk count in the
  confirm dialog; unknown count always confirms; provably-zero skips.
- **Connection guard + Copy diagnostics** (stock has neither).
- **No Insights deep-links**: neither insights plugin reads URL params
  (verified) — skipped rather than faked.

### Design-fidelity notes (token audit, 2026-07-21)

The Hub's shared CSS lives in the hosted frontend; the fragment-visible
contract is CSS custom properties + shared class names. No `font-family`
anywhere in the fragment (matches stock; monospace only via the log `pre`).
No shared font-size tokens exist — stock hardcodes px (10–14); we use its
values. Color/radius tokens referenced wherever one exists; fallback
literals match stock's own hardcodes (`#d97706`, `#ef4444`, the rgba
tints). Shared classes relied on: `card*`, `form-*`, `btn*`, `alert*`,
`badge badge-status-*`, `plugin-progress-*`, `spinner`, `divider`,
`plugin-section-number`. Copied component CSS (not importable from stock's
fragment): `.format-selected-banner` geometry, `guide-pulse` keyframes.

---

## 0.2.x worker model — what replaces the reload loop (port/0.2.x)

The v1.1.x dev loop was: edit -> POST /api/admin/plugins/kaggle/reload (JWT'd,
so via the Hub page) -> hard-refresh; NEW ROUTES needed a full service
restart. On the 0.2.x host the plugin runs OUT-OF-PROCESS: the host spawns
`<plugin venv>\python -m tlc_plugin_sdk.worker --entry tlc_plugin_kaggle:KagglePlugin`
and reverse-proxies /api/plugins/kaggle-exdark/* to it (reserved paths /ui /compute
/run /jobs/{id}/run /jobs/{id}/cancel are host-owned and match first).

The new loop:

1. Edit code under src/tlc_plugin_kaggle/ (folder-source registration points
   at the source tree; the provisioned venv imports it from there).
2. POST /api/admin/plugins/kaggle/reload (Hub Plugins page reload button) —
   on 0.2.x this KILLS THE WORKER; the next request respawns it against the
   current source. Routes live in OUR worker app now, so **new/renamed routes
   need only this worker restart — never a service restart** (the host
   catch-all proxies any subpath).
3. Hard-refresh the Hub page for ui.html changes (fragment still cached by
   the browser, same as before).

Notes:
- A worker restart wipes in-memory job state; the disk store
  (~/.3lc-kaggle-plugin/jobs) + the pid stamp mark interrupted jobs stale on
  next read — same semantics as a service restart used to have. Don't reload
  mid-train.
- ui.html is read once per worker process (get_ui_fragment caches); a worker
  restart also picks up fragment edits.
- Dependency changes (pyproject [kaggle] extra) need a re-provision of the
  plugin venv: Plugins page -> the plugin's venv panel -> Rebuild (or
  POST /api/plugins/kaggle-exdark/provision?force=true), then reload.

## Job start contract change (0.2.x)

Starts go through TWO calls now (see kgStartJob in ui.html): our
/validate/<kind> (keeps the fail-fast 400 + participant-facing message —
the host /run is fire-and-return and reports param problems only as failed
jobs) then the host's /api/plugins/kaggle-exdark/run with {kind, ...params}. The
/run job_id IS our store's record id, so all status polling, reconnect,
freshness, and Status-tab history logic is unchanged. Cancel goes to the
host: POST /api/plugins/jobs/{job_id}/cancel (our old custom cancel route
collides with the SDK worker's reserved path and was removed); host cancel
sets ctx.cancelled, which our JobCtx.is_cancelled() unions with the on-disk
flag, so pre-port records started under v1.1.x still cancel from disk.
