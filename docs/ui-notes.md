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
`state3`, `state4`, `state5`, `state6`. Buttons in forced states are live —
don't demo-click destructively. New tabs add their own values.

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
  elapsed · measured ETA) + determinate per-epoch bar (indeterminate
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
  checks ("From-scratch provenance recorded" / group head "Provenance
  verified") the moment the record carries them; cascade on live
  arrival only. Screenshot target for the README.

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

## 11. Known deferred items

- **File-browse endpoint** (server-side directory picker for the YAML path)
- **Recent-paths dropdown** on the YAML field
- **Stepper glyph pass** (✓/●/○ in the shared tab bar are still typographic)
- **Submit/Status emoji + type/motion/copy retrofit** — apply this
  playbook (Train done 2026-07-21)
- **`.kg-tab` header transition** still a literal `all .15s` — tokenize
  during the tabs' motion pass
- Post-launch: `gh:github.com:Isha2605` credential removal was recommended
  after the 2026-07-21 history rewrite (user's call)

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

The dev dispatch runs at the END of the fragment script so forced states
apply after every tab's vars and handlers exist; fixtures re-apply after
the async config load, and the metric curve is deterministic (no
randomness — identical screenshots every load).

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
