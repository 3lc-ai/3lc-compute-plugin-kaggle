# v1.2.7 pre-tag checklist

Nothing tags until every pre-tag line is ticked. Rules: RELEASING.md order
(tag → repo catalog.json → gist mirror), never retag, and the footer-version
heuristic is trustworthy this cycle from the bump commit on (dev wheels carry
1.2.7 metadata since the pin sweep). Run `pytest` last thing before tagging
(80 tests, both real-world migration fixtures).

**Freeze rule (RELEASING.md, codified this cycle):** everything above the
"Post-tag verification" section FREEZES at the tag. Post-tag, tick that
section only — never edit above the line.

## Verified at the review gates (2026-08-27, dev machine + dev Hub)

All observed by the reviewer against working-tree/committed builds during
the phase gates; commits named per item.

- [x] Kit scripts + CDN staging: deterministic shards regenerate
      byte-identically; all 11 objects live; Ranges honored (206);
      manifest round-trips byte-identically (sha `7bf1fd73…`); ETags
      confirmed multipart markers, NOT content MD5s. Full CDN pull:
      10/10 shards sha256 OK, extract, parity 14,004/14,004. (c33570a +
      staging session.)
- [x] Download job, live: fresh download / cancel / resume-via-206
      ("resuming at byte 4,194,304") / idempotent skip ("already on
      disk, sha256 verified — skipped") / disk precheck / tamper
      detection / recovery. keep_archives=false confirmed (dir holds
      only manifest.json + starter_kit/). (9aded53, d969d1f.)
- [x] S1 progress label through all phases: "Downloading shard 5/10 ·
      354 of 625 MB" → "Verifying files". (d969d1f.)
- [x] A5 auto-fill → green preflight with zero keystrokes → Import &
      Validate 9/9, tables created. (d969d1f; dev machine had prior
      config — the FRESH-session variant is a rehearsal item.)
- [x] T1 Verify action: corrupted image caught with count + exact path
      + remedy; Download button returns; re-download restores. A kit
      that passed the old one-file stat failed correctly. (5bc95c0.)
- [x] U1: cancelled state no longer shows the stale red not-found for
      the kit's own path (gate idles while the section owns the
      narrative). (5bc95c0.)
- [x] Feature 2 live: Open Run in Projects lands on the project's Runs
      tab; job-scoped confirmed (session project changed, button still
      targets the run's own project). (5bc95c0.)
- [x] V1: train-state4/6 fixtures show all three banner actions;
      train-state4-noproject shows two, no broken link, no gap.
      (530aa07.)
- [x] All ?kgdev fixtures (7 dl-* + classic states) render with "demo
      state — actions disabled", participant paths only; config hash
      identical before/after the full fixture walk (H1 held).
      (d969d1f gate.)
- [x] P1: TLC_KAGGLE_HOST_DIR default/override/blank pinned by tests;
      0-LOC copy verified live (local mAP 0.4308 renders); organizer
      appendix documents both. (530aa07.)
- [x] D4 preflight branch logic exercised against synthetic version
      dirs: fresh / missing-pin / stale-but-existing / ok-newest all
      correct. (8d4ecb6; never yet run for real on a fresh machine —
      rehearsal item.)

## Dress rehearsal — fresh 3070 Ti, Paul-parity (THE open pre-tag exercise)

Paul runs the full competition end to end on his own machine with no prior
context; that exact path has never been walked by anyone without context.
Rules of the rehearsal: use ONLY README + TESTER_SETUP_0.2.md + the Kaggle
page itself — no memory shortcuts, no dev-machine files. Record timings as
you go; the observations become this section's evidence.

**The one deviation from Paul's path** (unavoidable pre-tag): the catalog
source. No v1.2.7 tag exists yet, so install from a local clone's
catalog.json with the version's `source` temporarily pointed at the bump
commit sha on `port/0.2.x` (the documented pre-tag pattern, TESTER_SETUP
macOS appendix — works the same on Windows). Everything downstream of the
Install click is identical. Do NOT publish this catalog edit.

Markers: **[NEVER]** = first execution ever on a machine without prior
context · **[RECONFIRM]** = walked by round-1/2 testers, re-confirming on
this build.

- [x] **0. Zero-state audit** (~5 min): no `~\.3lc-compute`, no
      `~\.3lc-kaggle-plugin`, no `C:\3lc-hub-next`, fresh browser profile
      for the Hub. Paul-parity requires genuinely empty state.
- [x] **1. Prerequisites** per TESTER_SETUP §0 (~10–15 min). [RECONFIRM]
- [x] **2. setup-0.2-tester.ps1** (~5–10 min + interactive login).
      Expect the D4 preflight's fresh-machine branch: "No plugin venv on
      disk yet - normal on a fresh machine." [preflight: NEVER — this
      script version has never executed for real; rest: RECONFIRM]
- [x] **3. Catalog add + Install** (provision ~5–20 min, CUDA torch is
      several GB — network-bound). [v1.2.7's first provisioning
      anywhere, and the first fresh install under the $PLUGIN_VER-derived
      W1 path: NEVER; shop UX: RECONFIRM]
- [x] **4. First page open**: cold-worker warmup on the first request
      (~30–60 s), then footer reads **v1.2.7**, stepper empty, Import
      tab in state 1. [RECONFIRM + the footer is the N7 evidence]
- [x] **5. Download starter kit** [NEVER — off-dev, and the true
      first-visit offer state has never rendered on a machine with no
      prior config]: the offer shows the destination fact; the header
      label carries phase + shard N/10 + MB throughout (S1); 625 MB, so
      ~1 min at 100 Mbps to ~10+ min on slow wifi — a slow link staying
      legible is itself a test objective. Optional but recommended:
      Cancel once mid-download, confirm the cancelled callout, Resume,
      and look for "resuming at byte N" / "skipped" lines in the log
      [NEVER on a second network].
- [x] **6. Auto-fill → Import** [NEVER as a chain on a fresh session]:
      yaml fills with zero keystrokes, preflight green, Import &
      Validate → 9/9 checks, three tables, glance card (~2–6 min). The
      import is fed by the CDN kit — rounds 1/2 always used the
      hand-unzipped zip [NEVER].
- [x] **7. Revisit + Verify** [NEVER off-dev]: reload the page → quiet
      "downloaded Nm ago (14,004 files verified then)" line; click
      Verify (~8 s) → "verified just now: 14,004 of 14,004".
- [x] **8. KGAT token + join the competition** per README §2 (~5 min,
      byte-exact save). [RECONFIRM]
- [x] **9. Train 2 epochs** from the session project. 2 epochs is
      load-bearing (live ETA, ≥2-point sparklines, epoch-2 band ≈0.55).
      Expect roughly 2.5–4 min/epoch on the 3070 Ti — never measured on
      this GPU; this run IS the measurement, write it down [timing:
      NEVER; mechanics + provenance 4/4 + sha `0ebbc80d4a76…`:
      RECONFIRM].
- [x] **10. Banner links**: Open Run in Dashboard [RECONFIRM] and Open
      Run in Projects → the project's Runs tab [NEVER on a second
      machine/Hub session — the URL scheme's independence from the dev
      browser is what this proves].
- [x] **11. Predict** 715 images (~1–3 min): 5/5 format checks, sanity
      card, CSV row — and NO local-score hero: absence is the
      participant behavior; do not place host files on this machine.
      [RECONFIRM]
- [x] **12. Submit** → accepted ref; Status tab history row speaks the
      outcome vocabulary; budget line sane. [RECONFIRM]
- [x] **13. Copy diagnostics** from any tab: block stamps v1.2.7.
      [RECONFIRM]
- [x] **14. Record observations here**: provision minutes, download
      throughput + label behavior, epoch minutes, predict minutes, and
      any friction a context-free reader hit in the docs.

### Step-14 record (written 2026-08-28)

Machine: fresh 3070 Ti, Windows, a non-administrator user profile, single
home, no home redirect. Install per the documented pre-tag deviation: local-clone
catalog with `source` pinned to the bump-commit sha (e702864); that
catalog file was never published and lives outside the repo.

- Outcome (attested by Rishikesh, 2026-08-28): all steps 0–13 walked
  end to end using only README + TESTER_SETUP_0.2 + the Kaggle page;
  everything worked, including an accepted Kaggle submit. No code
  defects found, so no re-gate needed.
- Per-phase timings (provision, download, import, train 2 epochs,
  predict): **NOT RECORDED** during the run. Download/train/predict
  remain recoverable after the fact from the rehearsal laptop's job
  records (`~\.3lc-kaggle-plugin\jobs\*.json`,
  created_at/finished_at); provisioning and the setup script leave no
  job record and their durations are gone.
- Clone-to-first-import wall clock: **NOT RECORDED**.
- Whether the optional mid-download cancel/resume (item 5) was
  exercised: **NOT RECORDED**.
- Friction points: **NOT RECORDED** — none were written down during
  the run; absence of notes is not evidence of absence.
- Doc defects: **NOT RECORDED** — none were written down during the
  run.
- Gap note for the next reader: the 3070 Ti epoch time (item 9's "this
  run IS the measurement") was not captured. The only measured epoch
  times remain the dev 5070 Ti gate runs of 2026-08-26 (2-epoch train
  jobs: 3.9 and 4.3 min total, ≈2 min/epoch).

Wall-clock estimate: ~1.5–2.5 h, of which ~45–60 min hands-on; the rest is
provisioning/downloads/training.

**KNOWN UNTESTED PATH — the "not joined" branch.** The rehearsal account
has already entered the test competition, so the not-joined connection
state, the join flow, and the first-submit-after-joining transition cannot
be exercised on EITHER of our machines. Paul will be the first person to
walk that branch — and Gudbrand's submit-500 was exactly that state. If
Paul reports a submit failure early on, check his entered state FIRST,
before treating it as a plugin defect. Mitigation shipped with his
prerequisites: joining the competition and accepting the rules is the
FIRST step in the setup he receives (TESTER_SETUP §0 leads with it).

## Last things before the tag

- [x] Rehearsal complete above; any code defect found = fix + re-gate
      BEFORE tagging (never-retag: Paul's run must not straddle versions).
      (2026-08-28: complete, no defects; timings NOT RECORDED — see the
      step-14 record.)
- [x] `pytest` green (80) on the tag candidate commit. (80 passed,
      2026-08-28, on this commit's tree.)
- [x] `git grep -n "1\.2\.6"` — remaining hits are history/audit docs
      only (divergence-paths, PRETAG_1.2.6, notes), no pins. (Verified
      2026-08-28: docs/history, "since v1.2.6" code comments, and the
      catalog's own 1.2.6 entry — no pins.)
- [x] CONTEXT.md "Current release" sentence updated to v1.2.7 in the
      catalog commit (a statement about tags — it rides the post-tag
      catalog bump per RELEASING, not the pre-tag sweep). (2026-08-28:
      drafted and committed locally alongside the catalog entry,
      awaiting the tag before push.)

## Post-tag verification (tick-only below this line; everything above is frozen at the tag)

- [ ] Tag `v1.2.7` pushed; repo catalog.json gains the 1.2.7 entry
      (manifest matches plugin.toml verbatim); gist mirrored by
      Rishikesh; incognito-fetch the gist raw URL after the CDN lag.
- [ ] Version bump verified in the tagged build: footer reads v1.2.7
      after a REAL catalog install. Note: the rehearsal machine
      installed 1.2.7 from the branch sha, so its shop won't offer an
      Update to the tagged build (same version string — the D2 analog);
      verify on the dev machine, or full-uninstall first.
- [ ] Config, job history, runs, checkpoints survive the update pass
      intact (spot-read ui_config.json + a jobs/ record).
