# Forced-changes log — port/0.2.x (v1.2.0)

Everything the 0.2.x host / SDK / tlc 3.x FORCED us to change, and nothing
else. The four-tab UI, playbook, icons, motion, and copy are unchanged except
where listed. Reference: 3lc-hub-next/spike/PHASE1_VERDICT.md (tlc 3.x API
deltas, all empirically verified on 3.1.0.28).

## Forced by tlc 3.x (Phase-1 SLOW list)

| Change | Where |
|---|---|
| `Table.from_yolo(dataset_yaml_file=, split=)` → `Table.from_yolo_url(images_url, categories=)`; yaml parsing (already ours) now feeds it directly | importer.py `_import_labeled_split`, `_import_test_split` |
| `Url.create_table_url` removed → `_table_url()` rebuilds the layout from the configured project root (uses tlcconfig's **private** `_get_default_root_url` as fallback — upstream asked for a public builder) | importer.py (+ routes.py `table_defaults`) |
| `tlc.ImagePath("image")` → `tlc.schemas.ImageSchema()`; TableWriter kwarg `column_schemas=` → `schema=` | importer.py test-split GT-leak-guard path |
| `latest(wait_for_rescan=False)` → `latest()` | importer.py (`list_project_tables`, `table_revisions`) |
| Detection row shape `bbs.bb_list[*]` → `bbs.instances[*]` (+ labels in `bbs.instances_additional_data.label`; boxes absolute XYXY) | importer.py `_count_boxes`, `_value_map_labels` |
| Value-map path `bbs.bb_list.label` → `bbs.instances_additional_data.label` | importer.py `_value_map_labels` |

NOT forced (verified compatible, unchanged): `Table.from_url`, `Run.from_url`
(present on 3.x despite not appearing in `dir()`), `run.constants`
parameter readback, `tlc_ultralytics` `YOLO`/`Settings`/`model.train(tables=…)`
surface, `input_tables` lineage walk, `get_value_map` mechanism, trainer.py
and predictor.py in their entirety, config_store.py (stable home
`~/.3lc-kaggle-plugin/` kept).

## Forced by the 0.2.x host / SDK

| Change | Why |
|---|---|
| Manifest: class attributes → in-package `plugin.toml` (bare schema); `register()` side-effect deleted; base class `tlc_compute.plugins.base.ComputePlugin` → `tlc_plugin_sdk.ComputePlugin`; `_ICON_SVG` helper inlined | 0.2.x discovery is entry-point + manifest; the old base module no longer exists |
| Packaging: hatchling build + `packages = ["src/tlc_plugin_kaggle"]` (ships ui.html + plugin.toml); real deps declared (`[kaggle]` extra per `runtime.provision_extra`) | setuptools src-layout shipped only .py; deps must live in the plugin's own provisioned venv |
| routes.py: controller path absolute → **relative** ("" — host proxies `/api/plugins/kaggle/<subpath>` → `/<subpath>`); custom `/ui` re-expose deleted (host serves it); custom `POST /jobs/{id}/cancel` deleted (collides with the SDK worker's reserved route) | worker-app route model |
| Job starts: custom start routes → `/validate/<kind>` (fail-fast form UX kept) + host `POST /api/plugins/kaggle/run` dispatch (`kgStartJob` in ui.html — the ONLY ui.html behavior change, plus the cancel URL moving to the host route). Jobs bridge to the SDK JobContext (`jobs.run_dispatch`): Queue-panel progress, host cancel, worker keep-alive | host owns `/run` + `/jobs/...`; supervisor idle-reap (designed, not yet scheduled in 0.2.1) would kill custom-route-started long jobs |
| Legacy `POST /predict_submit` route deleted (kind still runs via dispatch for old records) | two-step UI never called it; one less start path to maintain |
| `KagglePlugin.version` / `.repository_url` class attrs → module `__version__` / `REPOSITORY_URL` (used by `_meta`) | SDK base class carries no manifest attrs |

## Deliberate deviation from the "copy yolo-0.1.3 verbatim" instruction

- torch index **cu128**, not yolo's cu126: cu126 wheels do not support
  Blackwell GPUs (sm_120 — the RTX 5070 Ti this is developed and smoke-tested
  on); cu128 runs older architectures too. Everything else about the
  dependency pattern (SDK-floor base deps, heavy stack behind the extra,
  `[[tool.uv.index]]` + `[tool.uv.sources]` with linux/win32 markers) is
  copied as instructed.

## Known consequence (accepted, documented)

- The catalog/`uv pip install` path does NOT read `[tool.uv.index]` from our
  pyproject (that config drives folder-source `uv sync` provisioning only) —
  a catalog install resolves plain `torch` from PyPI = **CPU-only on
  Windows**. Mitigation for testers: `TLC_COMPUTE_PLUGIN_INDEX_URLS=https://download.pytorch.org/whl/cu128`
  on the service (passed to installs as `--extra-index-url`). Verified in
  Phase 4; also raised as a shop-mechanism gap (stock yolo/timm have the same
  problem). *Update (2026-08-10):* superseded by `UV_TORCH_BACKEND=auto` in the
  service env — the shop's `uv pip install` subprocess inherits the service
  environment, and uv's torch-backend selector picks the right CUDA index per
  driver (no-op on non-NVIDIA hosts). Verified on uv 0.11.7 with the
  provisioning flag shape (`--extra-index-url` ×2 + `--index-strategy`):
  resolved `torch==2.13.0+cu130` on the RTX 5070 Ti box.
