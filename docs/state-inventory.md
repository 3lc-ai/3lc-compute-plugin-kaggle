# State inventory — kaggle-exdark plugin (audit session 2026-08-13, v1.2.5 @ 54af3a5)

One row per piece of state the plugin holds. Companion docs:
[divergence-paths.md](divergence-paths.md) (the paths this table predicts) and
[state-audit-verdict.md](state-audit-verdict.md) (DP-01 root cause, fix scope, coverage gaps).

**Initial sizing: ~85 rows. Final count: 78 rows** (+ the literal census appendix).
Within the 2x circuit-breaker.

## Legend

- Files: `ui` = src/tlc_plugin_kaggle/ui.html · `cs` = config_store.py · `rt` = routes.py ·
  `im` = importer.py · `tr` = trainer.py · `pr` = predictor.py · `jb` = jobs.py
- Storage: **cfg** = `~/.3lc-kaggle-plugin/ui_config.json` · **job** = job record
  (`~/.3lc-kaggle-plugin/jobs/<id>.json` + memory) · **mem** = JS in-memory ·
  **DOM** = lives only in a form element · **drv** = derived-only, never stored ·
  **run** = tlc.Run record on disk
- Shared write/read path tokens (used to keep cells readable; every token is exact):
  - **[T-save]** — whole-form Train snapshot to cfg `train.*`: run-start `ui:4074` + kgSyncFieldToProject side-effect `ui:1826`
  - **[S-save]** — whole-form Submit snapshot to cfg `submit.*`: predict click `ui:4716`, submit click `ui:4962`, sync side-effect `ui:1827`
  - **[I-save]** — whole-form Import snapshot to cfg `import.*`: settle (debounce 600 ms + blur) `ui:2213-2235`, import start `ui:2608`
  - **[C-load]** — cfg → DOM restore, once per page load: `applyConfig ui:1885-1896` (skips missing/null and `''` values, `ui:1891-1893`; **no validation**)
  - **[T-body]** — Train start collects DOM → job params `ui:4075-4104`
  - **[P-body]** — Predict start collects DOM → job params `ui:4717-4723`
- Flags: **🔴** = more than one default source OR the same logical fact stored under
  more than one key (divergence candidate) · **🟡** = more than one write path only
  (dual-write via the sync side-effect or multi-copy write; lower risk on its own)

Note: because kgSyncFieldToProject re-persists whole tabs (`ui:1826-1827`), **every**
persisted Train/Submit field has ≥2 write paths. That shared 🟡 is stated here once;
rows below carry 🔴 only for the stronger condition.

---

## A. Import tab — form inputs

| Name | Meaning | Canonical owner | Storage | Write paths | Read paths | Default source | Validated on read? | Schema version | Tabs projecting it |
|---|---|---|---|---|---|---|---|---|---|
| `kg-yaml` → cfg `import.dataset_yaml` 🔴 | Path to starter-kit dataset.yaml | Import form | DOM + cfg | typing; path-clean rewrite `ui:2143`; server-resolved folder→file rewrite `ui:2157-2161`; [I-save]; [C-load] | preflight `ui:2142`; import start `ui:2599`; diagnostics `ui:1480` | none (placeholder only, `ui:643`) | Yes — preflight parses it (`im:68-111`) | none | Import |
| `kg-project` → cfg `import.project_name` 🔴 | 3LC project the tables are imported into; de-facto "current project" for the whole plugin | Import form (per CONTEXT.md "single source of truth") | DOM + cfg | typing; [I-save]; [C-load] | `kgCurrentProject() ui:1790-1793` (read by pickers `ui:1743`, sync `ui:1807`, gate copy `ui:3852`, `ui:4417`, defaults prefill `ui:3435`, `ui:4512`); import start `ui:2601` | hardcoded literal `value="exdark-competition"` `ui:651`; backend re-default `rt:119`, `im:379` | No | none | Import (edits); Train + Predict (consume via kgCurrentProject) |
| `kg-table` → cfg `import.table_name` 🔴 | Revision/table name for the imported tables | Import form | DOM + cfg | typing; [I-save]; [C-load] | import start `ui:2602` | hardcoded `value="initial"` `ui:655`; backend re-default `rt:120`, `im:380`; **independently hardcoded** in defaults derivation `rt:164` (no caller passes `table`) | No | none | Import only — Train/Predict defaults ignore it (DP-02) |
| `force_splits` | Splits to overwrite on re-import | Re-import confirm flow | transient (request param) | Re-import buttons `ui:2513`, `ui:2651` | `im:383` | `[]` | Yes — filtered to known splits `rt:121` | n/a | Import |
| Splits-to-import display | "All three splits mandatory" locked row | derived | drv | — | rendered `ui:1985-1997` | fixed | n/a | n/a | Import |

## B. Train tab — form inputs

All rows: Storage = DOM + cfg `train.*`, write paths = typing + [T-save] + [C-load]
(exceptions noted), read paths = [T-body] + the listed extras. CFG_FIELDS map: `ui:1850-1863`.

| Name | Meaning | Canonical owner | Extra write paths | Extra read paths | Default source | Validated on read? | Schema version | Tabs projecting it |
|---|---|---|---|---|---|---|---|---|
| `tr-train-url` → `train_table_url` 🔴 | Train table URL | should be derived from (project, table, split); today the field owns it | picker `ui:1763`; blank-prefill `ui:3439`; sync overwrite `ui:1822` | gate `ui:3862`; fix-labels deep-link `ui:3447` | derivation `/tables/defaults` `rt:164-172` with hardcoded `table='initial'` | gate re-verifies exists-on-disk on entry/edit (`ui:3861-3911`) but **not** at [C-load] time | none | Train |
| `tr-val-url` → `val_table_url` 🔴 | Val table URL | same as above | picker `ui:1763`; prefill `ui:3440`; sync `ui:1822` | gate `ui:3863` | same derivation | same | none | Train |
| `tr-latest` → `use_latest` | Resolve `.latest()` at job start | Train form | picker unchecks `ui:3989`, `ui:3993` | gate copy `ui:3839-3841`; `tr:391` | checked (markup `ui:759`) | n/a (bool) | none | Train |
| `tr-epochs` → `epochs` 🟡 | Epochs | Train form | — | duration hint `ui:3921`; bounds `ui:4005` | hardcoded 20 `ui:769` = server default `tr:128` | on blur only (`ui:4054`); server re-validates `tr:225` | none | Train |
| `tr-batch` → `batch` 🟡 | Batch size | Train form | — | bounds `ui:4006` | 16 `ui:778` = `tr:129` | blur; server | none | Train |
| `tr-lr0` → `lr0` 🟡 | Initial LR | Train form | — | bounds `ui:4007` | 0.01 `ui:785` = `tr:130` | blur; server | none | Train |
| `tr-lrf` → `lrf` 🟡 | Final LR fraction | Train form | — | bounds `ui:4008` | 0.01 `ui:792` = `tr:131` | blur; server | none | Train |
| `tr-optimizer` → `optimizer` 🟡 | Optimizer | Train form | — | — | 'auto' `ui:801` = `tr:132` | server membership `tr:213-217` | none | Train |
| `tr-patience` → `patience` 🟡 | Early-stop patience | Train form | — | bounds `ui:4009` | 100 `ui:813` = `tr:133` | blur; server | none | Train |
| `tr-device` → `train.device` 🔴 | Compute device (train) — **same logical fact as `submit.device`, stored twice** | should be one machine-level fact | — | disclosure-reopen probe `ui:3456`; worker resolve `tr:385`→`pr:262-285` | blank=auto `ui:830` = `tr:137` | No client check; worker resolves | **the only migrated key**: `device_blank_default` rewrites saved `'0'`→`''` once, both copies `cs:42-52` | Train |
| `tr-workers` → `workers` 🟡 | Dataloader workers | Train form | — | disclosure probe `ui:3456`; bounds `ui:4010` | 0 `ui:837` = `tr:138` | blur; server | none | Train |
| `tr-extra` → `extra_args` 🟡 | Free-text ultralytics args | Train form | — | disclosure probe `ui:3457` | empty | server lock/bounds guard `tr:176-198` | none | Train |
| `tr-project` → `train.project_name` 🔴 **DP-01** | 3LC project the **Run** is created in | should be the session project (= kg-project) | — (never synced; never follows kg-project) | [T-body] `ui:4088` → `tr:272` → Run location | hardcoded literal `value="exdark-competition"` `ui:859`; server re-default `tr:272` | No — nothing compares it to kgCurrentProject | none | Train (the field); Status/Dashboard links consume its consequence |
| `tr-runname` | Run name (blank → timestamped) | derived server-side | **not persisted** (absent from CFG_FIELDS) | [T-body] `ui:4089`; generated `tr:273` | derived `kaggle_run_<ts>` `tr:273` | n/a | n/a | Train; Predict/Status display the generated result |
| `tr-conf` → `conf_thres` 🟡 | Collection confidence threshold (3LC settings — distinct fact from `ps-conf`) | Train form | — | bounds `ui:4011` | 0.1 `ui:868` = `tr:274` | blur; server `tr:274` | none | Train |
| `tr-maxdet` → `max_det` 🟡 | Max detections (collection) | Train form | — | bounds `ui:4012` | 300 `ui:874` = `tr:275` | blur; server | none | Train |
| `tr-embdim` → `image_embeddings_dim` 🟡 | Image embeddings 0/2/3 | Train form | — | disclosure probe `ui:3462` | '0' `ui:891` = `tr:277` | server membership `tr:265-267` | none | Train |
| `tr-embreducer` → `image_embeddings_reducer` 🟡 | Reducer | Train form | — | disclosure probe `ui:3462` | 'pacmap' `ui:900` = `tr:278` | server membership `tr:268` | none | Train |
| `tr-instdim` → `instance_embeddings_dim` 🟡 | Instance embeddings | Train form | — | disclosure probe `ui:3463` | '0' `ui:909` = `tr:279` | server | none | Train |
| `tr-colstart` → `collection_epoch_start` 🟡 | First collection epoch | Train form | — | bounds `ui:4013` (blank allowed) | blank `ui:918` = None `tr:286` | blur; server | none | Train |
| `tr-colint` → `collection_epoch_interval` 🟡 | Collection interval | Train form | — | bounds `ui:4014` | 1 `ui:922` = `tr:287` | blur; server | none | Train |
| `tr-collectloss` → `collect_loss` 🟡 | Collect loss | Train form | — | disclosure probe `ui:3460-3465` | unchecked = `tr:276` | n/a | none | Train |
| `tr-gtinst` → `ground_truth_instance_embeddings` 🟡 | GT instance embeddings | Train form | — | disclosure probe | unchecked = `tr:280` | n/a | none | Train |
| `tr-valonly` → `collection_val_only` 🟡 | Collect val only | Train form | — | disclosure probe | unchecked = `tr:284` | n/a | none | Train |
| `tr-exclzero-col` → `exclude_zero_weight_collection` 🟡 | Exclude 0-weight (collection) | Train form | — | disclosure probe | unchecked = `tr:283` | n/a | none | Train |
| `tr-coldisable` → `collection_disable` 🟡 | Disable collection | Train form | — | disclosure probe | unchecked = `tr:285` | n/a | none | Train |
| `tr-sampling` → `sampling_weights` 🟡 | Sampling weights | Train form | — | disclosure probe | unchecked = `tr:281` | n/a | none | Train |
| `tr-exclzero-train` → `exclude_zero_weight_training` 🟡 | Exclude 0-weight (training) | Train form | — | disclosure probe | unchecked = `tr:282` | n/a | none | Train |

## C. Predict + Submit tab — form inputs

| Name | Meaning | Canonical owner | Storage | Write paths | Read paths | Default source | Validated on read? | Schema version | Tabs projecting it |
|---|---|---|---|---|---|---|---|---|---|
| `ps-run` (selection) | Selected train job for prediction | run selector | DOM only (not persisted) | psLoadRuns rebuild `ui:4339-4357` (keeps prior selection if still usable, else first usable) | [P-body] `ui:4718`; diagnostics `ui:4249` | first usable run `ui:4355-4357` | Yes — `/runs` marks unusable with reason `rt:224-233` | n/a | Predict |
| `ps-weights` | Direct weights path (host-only) | host affordance | DOM only | typing; cleared on source switch `ui:4277` | [P-body] `ui:4719` | empty | server host-gate `rt:41-48` | n/a | Predict (host) |
| `psSource` ('run'/'weights') | Which weights source is active | seg control | mem `ui:4199` | `psSetSource ui:4267-4280` (coerced to 'run' under ?kgdev) | [P-body] `ui:4718-4719` | 'run' | n/a | n/a | Predict |
| `ps-test-url` → cfg `submit.test_table_url` 🔴 | Test table URL | should be derived from (project, table, 'test') | DOM + cfg | typing; picker `ui:4476`; blank-prefill `ui:4516`; sync overwrite `ui:1822`; [S-save]; [C-load] | gate `ui:4426`; [P-body] `ui:4720` | derivation `rt:164-172`, hardcoded `table='initial'` | gate re-verifies on entry/edit `ui:4425-4460`; not at load | none | Predict |
| `ps-conf` → `submit.conf` 🟡 | Inference confidence | Predict form | DOM + cfg | typing; [S-save]; [C-load] | [P-body] `ui:4721`; bounds `ui:4481-4493` | 0.25 `ui:1043` = `pr:697` | blur only; server clamps `pr:697` | none | Predict |
| `ps-device` → `submit.device` 🔴 | Compute device (predict) — second copy of the device fact | should be one fact | DOM + cfg | typing; [S-save]; [C-load] | [P-body] `ui:4722` | blank=auto `ui:1048`; worker `pr:262-285` | No | `device_blank_default` migration `cs:47` | Predict |
| `ps-slug` → `submit.competition_slug` 🔴 | Kaggle competition slug | should be server constant unless deliberately overridden | DOM + cfg | connection default-fill when empty `ui:4817-4819`; typing; [S-save]; [C-load] | connection probe `ui:4801`; submit params `ui:4971`; Status live fetch `ui:5347`; leaderboard URL `ui:5326` | server constant `COMPETITION_SLUG pr:33` via `default_slug` | **No** — a stale persisted slug wins over a new shipped constant forever (DP-04); `'[SLUG]'` band-aid `pr:550,614` is the existing symptom patch | none | Predict + Status |
| `ps-message` | Kaggle submission message | derived server-side | DOM only (not persisted) | typing | submit params `ui:4970`; derived `pr:812` | derived `"<run_name> via 3LC plugin"` `pr:812` | n/a | n/a | Predict |

## D. ui_config.json — backend-written snapshot keys (`cs:30` allowlist)

| Name | Meaning | Canonical owner | Storage | Write paths | Read paths | Default source | Validated on read? | Schema version | Tabs projecting it |
|---|---|---|---|---|---|---|---|---|---|
| `import_state.project` / `.table_name` / `.dataset_yaml` 🔴 | Second copy of the three Import form facts, frozen at last success | should not exist separately | cfg | `im:476-490` (import success only) | `verified_import_state im:509-517`; revisit `ui:2683-2687`; re-import-from-revisit `ui:2594-2597` | copied from job params; fallback literals `ui:2685-2686`, `im:515-516` | tables re-verified on disk `im:535-543`; the strings themselves not | none | Import (revisit), stepper (all tabs) |
| `import_state.tables{split:{url,rows,reused}}` | Last import's outputs | import job | cfg | `im:478-488` | revisit render `ui:2689-2696`; verification `im:536-541` | job result | Yes — `.exists()` per split | none | Import, stepper |
| `import_state.mechanisms` / `.checks` | GT-leak mechanism + 9 checks | import job | cfg | `im:478-488` | revisit `ui:2689,2697` | job result | No (display) | none | Import |
| `import_state.job_id` 🟡 | Log-accordion garnish | import job | cfg | `im:484` | `im:545-550`; `ui:2683,2707` | — | Yes — `job_available` downgrade `im:550` | none | Import |
| `predict_state.job_id` 🔴 | Basis for revisit-submit + CSV download | predict job | cfg | `pr:762-781` | `predict_submit_state pr:855-867`; basis `ui:5050-5056`; submit param `ui:4969`; download `ui:5033` | — | **CSV existence checked (`pr:858-860`) but job-record existence is NOT** → DP-08 vs 50-record prune `jb:36` | none | Predict, Status |
| `predict_state.{run_name,weights,csv_path,conf,local_score,sanity,checks,finished_at}` 🟡 | Copies of the predict job's facts | predict job facts | cfg | `pr:762-781` | revisit render `ui:5010-5031` | job facts | csv_path yes; rest no | none | Predict |
| `submit_state.{status,ref,reason}` 🔴 | Third copy of the submission outcome (also on submit-job facts and predict-job facts) | should be one store | cfg | `pr:821-838` | pairing + revisit `pr:862-866`, `ui:5038-5047` | job outcome | paired by `predict_job_id` only | none | Predict |
| `submit_state.{job_id,predict_job_id,run_name,message,slug,finished_at}` 🟡 | Submit context copies; `.slug` is a third slug store (never read back) | submit job | cfg | `pr:824-834` | `pr:862-866` | `slug or COMPETITION_SLUG` `pr:832` | No | none | Predict |
| `_migrations` | One-shot migration markers | config store | cfg | `cs:51`, stamped on save `cs:79` | `cs:44-46` | `{}` | n/a | this IS the versioning; covers only `device_blank_default` | — |

## E. Job records (disk + memory, `jb:109-127` / `jb:231-246`)

| Name | Meaning | Canonical owner | Storage | Write paths | Read paths | Default source | Validated on read? | Schema version | Tabs projecting it |
|---|---|---|---|---|---|---|---|---|---|
| `id` | Host job id (= poll key) | host dispatch | job | `jb:230` | all polling/routes | host `sdk_ctx.job_id` | n/a | none | all |
| `kind` | import/train/predict/kaggle_submit/predict_submit | dispatch | job | `jb:232` | list filters `jb:404`; pipeline `rt:414-426` | caller | n/a | legacy `predict_submit` handled `rt:424` | all |
| `status` 🟡 | running/completed/failed/cancelled/stale — **4 writers**: runner terminal `jb:257-269`, cancel `jb:302-325`, orphan-mark `jb:328-351`, normalize `jb:354-362` | job store | job | see left | everything | 'running' | Yes — pid check + cancel-clobber normalization are validate-on-read healers | implicit (pid stamp; `scripts/migrate_job_records.py`) | all |
| `pid` | Owning worker process | job store | job | `jb:235` | `_mark_if_orphaned jb:339` | `os.getpid()` | is the validator | stamp added session-2 | — |
| `created_at` / `finished_at` | Timestamps | job store | job | `jb:236-237`, `jb:273` | ETA `ui:3555-3567`; history sort `ui:5382`; adopt-fresh `ui:1193` | `time.time()` | No | none | all |
| `cancelled` 🟡 | Cooperative-cancel flag — dual memory/disk write, merged before terminal flush `jb:256-259` | job store | job | `jb:302-325`; `jb:258` | `is_cancelled jb:71-78` (reads DISK first) | False | disk-first read is the healer | normalize covers pre-fix records | Train |
| `params` | Job inputs snapshot (incl. `project_name`, `epochs`, `run_name`) | job start | job | `jb:239` | epoch clamp `rt:237-243`; diagnostics `ui:3705`; history `ui:5245` | caller body | epochs display-clamped `rt:240-242` | none | Train, Status |
| `log` / `checks` / `progress` | Live job telemetry | JobCtx | job | `jb:49-63` | polls; diagnostics | `[]`/`{}` | No | none | owning tab |
| `result` | Terminal payload (train: `run_url,run_name,weights,weights_exists,cancelled,epochs_completed,provenance,locked,checkpoint_sha256` `tr:547-557`) | job target | job | `jb:260` | `/runs rt:215-277`; terminal render | — | epochs clamped on read `rt:237-243` | none | Train, Predict, Status |
| `error` | Failure message | runner | job | `jb:266` | fail banners; outcome vocab `ui:5122-5126` | None | No | none | all |

## F. Job facts (durable per-kind facts, written via `ctx.set_field`)

| Name | Meaning | Canonical owner | Storage | Write paths | Read paths | Default source | Validated on read? | Schema version | Tabs projecting it |
|---|---|---|---|---|---|---|---|---|---|
| `facts.run_name` 🟡 | Run name — also in `result.run_name` and `params.run_name`; 3-way fallback chains at `rt:259-262`, `ui:5114-5117`, `pr:807` | trainer | job | train `tr:389`; predict `pr:685`; submit `pr:808` | run selector, history, basis | generated `tr:273` | No | none | Train, Predict, Status |
| `facts.weights` | best.pt path | trainer | job | `tr:511` | `/runs rt:221-232`; predict resolve `rt:52-54` | — | Yes — `is_file()` on read `rt:222`, `rt:57` | none | Predict |
| `facts.run_url` | tlc Run URL | trainer | job | `tr:510` | dashboard links `ui:3652`, `ui:5246-5248`; queue panel `jb:424` | — | No | none | Train, Status |
| `facts.checkpoint_sha256` | Pinned-init hash | trainer | job | `tr:403` | `/runs rt:271-273`; diagnostics `ui:4252` | verified download `tr:72-115` | provenance asserts it from the **Run record**, not from here `tr:344-374` | none | Train, Predict |
| `facts.csv_path` 🟡 | Submission CSV path — copies in predict facts `pr:727`, predict_state `pr:771`, submit facts `pr:809` | predict job | job | see left | validate_submit `rt:311`; download `rt:364`; submit `pr:801` | — | Yes — `is_file()` at every consumer | none | Predict, Status |
| `facts.sanity` / `facts.local_score` / `facts.conf` | Sanity summary, host-only score, conf used | predict job | job | `pr:732`, `pr:742`, `pr:698` | results panel `ui:4623-4634`; hero/history `ui:5155-5157`, `ui:5233-5235` | — | No | none | Predict, Status |
| `facts.submission` 🔴 | Submission outcome — **three stores**: submit-job facts `pr:816`, cross-written onto predict-job facts `pr:817` (best-effort, silent failure `jb:277-299`), and `submit_state` `pr:821-838` | should be one store | job ×2 + cfg | see left | history outcome `ui:5121-5148`; revisit `ui:5038-5047`; pipeline `rt:421-425` | — | No — copies can diverge (DP-07) | none | Predict, Status |
| `facts.predict_job_id` | Submit→predict back-pointer | submit job | job | `pr:810` | pairing `pr:863` | — | No | none | Status |

## G. tlc Run record

| Name | Meaning | Canonical owner | Storage | Write paths | Read paths | Default source | Validated on read? | Schema version | Tabs projecting it |
|---|---|---|---|---|---|---|---|---|---|
| `Run.parameters` (all YOLO args + 3LC settings + `checkpoint_sha256`) | **Canonical provenance** — the locked contract's proof | tlc Run | run | 3lc-ultralytics trainer param log + `tr:518` | `check_provenance tr:344-374` | training call | Yes — the 4 assertions ARE the validation | none | Train (provenance panel), Predict (run summary) |
| Run's project location | Which 3LC project holds the Run | consequence of `train.project_name` | run (path) | Settings(project_name) `tr:272` at run creation | Dashboard; `facts.run_url` | `tr-project` field → DP-01 | No | n/a | Dashboard, Status links |

## H. Frontend in-memory workflow state (per page load)

| Name | Meaning | Canonical owner | Storage | Write paths | Read paths | Default source | Validated on read? | Schema version | Tabs projecting it |
|---|---|---|---|---|---|---|---|---|---|
| `kgCurrentProject()` | Derived: kg-project value or literal fallback | derived | drv | — | `ui:1790-1793` callers (pickers, sync, gates, prefills) | fallback literal `'exdark-competition'` `ui:1793` | n/a | n/a | all |
| `kgFollowedProject` | Baseline to detect a settled project change | sync machinery | mem | init after config load `ui:2225`; update on settle `ui:2217` | `ui:2216` | null | n/a | n/a | — |
| `kgRevisitSrc` 🔴 | Copy of {yaml, project, table} the revisit view re-imports from — can differ from the (hidden) form + cfg | should be derived from import_state directly | mem | `ui:2683-2687`; cleared `ui:2663`, `ui:2828` | re-import source `ui:2594-2597`; diagnostics `ui:1480` | snapshot ‖ literals `ui:2685-2686` | No | n/a | Import |
| `kgPreflight` / `kgLastPreflightYaml` / `kgPreflightSeq` | Last green preflight + debounce/stale guards | preflight flow | mem | `ui:2141-2179` | ready-check `ui:2136`; start guard `ui:2604` | null | server-produced | n/a | Import |
| `kgImporting` / `kgLastJobId` | In-flight flag + last job for diagnostics | import flow | mem | `ui:2614`, `ui:2632`, `ui:2732` | ready-check; diagnostics | false/'' | n/a | n/a | Import |
| `trGate` / `trLastGateKey` | Green-gate verdict + same-key no-op guard | gate flow | mem | `ui:3861-3911` | `trCheckReady ui:4022-4025`; start guard `ui:4070` | null | forced re-check on tab enter `ui:3956-3957` (the round-1 staleness fix) | n/a | Train |
| `trainJobId` / `trainTimer` / `trRunning` | Poll target + in-flight flag | train flow | mem | start `ui:4118`; reconnect `ui:4162` | poll `ui:3751`; cancel `ui:4143` | null | pid check server-side | n/a | Train |
| `trEpochSecs` | Median epoch seconds (duration hint + ETA seed) | derived from job history | mem | `ui:3931-3947` | hint `ui:3918-3929`; ETA seed `ui:3564-3565` | null (hint omitted) | n/a | n/a | Train |
| `trLastParams` / `trLastChecks` | Diagnostics context | train flow | mem | `ui:4105`, `ui:3705`; `ui:3607` | `trBuildDiagnostics ui:3407-3416` | null | n/a | n/a | Train |
| `trInvalid` / `psInvalid` | Client bounds-error map | bounds mirror | mem | `ui:4033`, `ui:4485` | ready checks | `{}` | n/a | n/a | Train, Predict |
| `psRuns` | Cached /runs list | backend | mem | `ui:4338` | selection lookup `ui:4308-4311`; diagnostics | `[]` | server marks usability | n/a | Predict |
| `psGate` / `psLastGateKey` | Test-table gate verdict | gate flow | mem | `ui:4425-4460` | `psCheckPredictReady ui:4503-4507` | null | forced re-check on tab enter `ui:4390` | n/a | Predict |
| `psBasis` 🔴 | What step 2 would submit {job_id, run_name, local_score, when, persisted} | should be derived from predict_state/job | mem | live `ui:4680-4685`; revisit `ui:5050-5056`; cleared `ui:4988`, `ui:5001` | submit params `ui:4969`; confirm text `ui:4960`; downloads `ui:4905` | null | job_id NOT validated against job store (DP-08) | n/a | Predict |
| `psConnState` | Last /kaggle/connection payload | backend | mem | `ui:4815`; fixtures `ui:3356-3361` | budget `ui:4775-4780`; submit gating `ui:4782-4796`; Status hero `ui:5180` | null | server-produced | n/a | Predict, Status |
| `psStep2Enabled` / `psPredicting` / `psSubmitting` | Step gating + in-flight flags | predict flow | mem | `ui:4753`, `ui:4724`, `ui:4963` | ready checks | false | n/a | n/a | Predict |
| `psPredictJobId` / `psSubmitJobId` | Poll targets | predict flow | mem | `ui:4734`, `ui:4975`; reconnect `ui:5071`, `ui:5081`; revisit `ui:5049` | polls | null | n/a | n/a | Predict |
| `psLastChecks` / `psLastSanity` / `psLastSubmission` | Diagnostics context | predict flow | mem | `ui:4626-4627`, `ui:4926`, `ui:5040` | `psBuildDiagnostics ui:4246-4264` | null | n/a | n/a | Predict |
| `stLastUpdated` / `stBusy` | Status freshness stamp + fetch lock | status flow | mem | `ui:5389`, `ui:5366` | updated-line `ui:5358-5361` | null | n/a | n/a | Status |
| `kgHost` | Organizer-machine flag | server `_meta.host` | mem | config load `ui:1931` | seg reveal `ui:1933`; also enforced server-side `rt:41-48` | false | server is enforcer | n/a | Predict |
| `kgPluginVersion` | Version for diagnostics/footer | server `_meta` | mem | `ui:1924`; preflight fallback `ui:2156` | diagnostics header `ui:1455` | '' | n/a | n/a | all |
| `kgDevMode` | ?kgdev fixture mode | URL | mem | `ui:3392` | gates everywhere (`ui:2136`, `ui:4024`, `ui:4506`…) | null | n/a | n/a | all |
| Render caches (grouped: `kgPreflightKind`, `trGateKind`, `psGateKind`, `kgPrevStageStatus`, `kgShownTab`, `trHadChecks`, `psResultsShown`) | Animation/replay suppression only — no workflow fact | render layer | mem | respective renderers | same | 'idle'/false | n/a | n/a | — |
| `localStorage['kg.activeTab']` | Last active tab | browser | localStorage | `ui:1276` | dispatch `ui:5445`, `ui:1300` | 'import' | membership-checked `ui:1249` | none | all (drives DP-06 entry path) |

## I. Derived-only display values (never stored — correct per the target design)

| Name | Meaning | Derived from | Rendered at |
|---|---|---|---|
| Stepper/pipeline checkmarks | Import/Train/Submit done | `/pipeline rt:403-427` (import delegates to verified_import_state; train/submit scan **all** jobs, project-blind) | `ui:1940-1963` |
| ETA "remaining" | recompute per poll | `avg_epoch_s` ‖ `trEpochSecs` seed | `ui:3564-3571` |
| Duration hint | median × epochs | `trEpochSecs` | `ui:3918-3929` |
| Budget "X of N left" | connection payload | `psBudget ui:4775-4780` | `ui:4839-4852`, `ui:5183-5187` |
| History Δ | vs previous scored row | records walk `ui:5229-5238` | `ui:5253-5265` |
| Glance card / basis line / verdict lines / outcome vocabulary | per-render | payloads | `ui:2004-2023`, `ui:4760-4773`, `ui:5119-5148` |
| `ps-message` effective value | `"<run_name> via 3LC plugin"` | `pr:812` | Kaggle history |
| `run_name` when blank | timestamp | `tr:273` | everywhere |

---

## Appendix — hardcoded-literal census (default sources that shadow canonical state)

- `'exdark-competition'`: `ui:651` (Import field markup), `ui:859` (**Train field markup — DP-01**),
  `ui:1793` (kgCurrentProject fallback), `ui:2685` (revisit fallback), `rt:119` (validate_import),
  `rt:164` (table_defaults), `rt:331` (tables_list), `rt:404` (pipeline), `im:379` (run_import),
  `im:515` (synthesized state), `tr:272` (validate_settings → **Run project**). 11 live sites.
- `'initial'`: `ui:655` (markup), `ui:2686`, `rt:120`, `rt:164` (**table_defaults — no caller
  passes `table`, DP-02**), `im:380`, `im:516`. 6 sites.
- Competition slug: `pr:33` (constant, "SWAP AT PUBLIC LAUNCH") + persisted copy in
  `submit.competition_slug` + dead copy in `submit_state.slug` (DP-04).
- `DEFAULT_SAVE_ROOT`: defined twice, `tr:120` and `pr:42`, "kept in sync by hand" (pr comment).
- Client bounds tables `TR_BOUNDS ui:4004-4015` mirror server `tr:126-139`/`tr:235-240` by hand.

## Summary of flagged rows

**🔴 (multi-default / multi-key — the divergence candidates):** project name (kg-project +
tr-project + import_state.project + 11 literals), table name (kg-table + import_state.table_name +
hardcoded 'initial' in the defaults derivation), device (train.device + submit.device),
competition slug (constant + submit.competition_slug + submit_state.slug), the three table-URL
fields (user/picker/prefill/sync writers × config/derivation defaults), dataset_yaml
(import.dataset_yaml + import_state.dataset_yaml + kgRevisitSrc), submission outcome (3 stores),
predict_state.job_id (unvalidated against prune), psBasis, kgRevisitSrc.

**🟡 (multi-write only):** every persisted Train/Submit field (sync side-effect saves the whole
form), job `status`/`cancelled` (multi-writer with read-time healers), run_name (3 copies,
1 writer), csv_path (3 copies, 1 writer), epochs_completed (display-clamped).
