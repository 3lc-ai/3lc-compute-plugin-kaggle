"""Import card backend: competition dataset -> three 3LC tables + validation.

Import mechanism (decided empirically against tlc 2.22.3.1, 2026-07-20):

* train / val: ``tlc.Table.from_yolo`` on the participant's dataset.yaml, one
  call per split, dataset names ``exdark_train`` / ``exdark_val``.

* test: the competition test split is images-only BY DESIGN (hidden GT).
  Probed behavior that drives the mechanism choice:
    - ``from_yolo`` on a genuinely labels-less split works fine: 715 rows,
      one per image, empty ``bb_list``, same schema as train/val. So on a
      participant machine (no test labels) from_yolo IS the primary path —
      no fallback needed.
    - BUT both ``from_yolo`` and ``from_yolo_url`` (folder or images.txt
      input) auto-discover label files by the YOLO path convention
      (images/... -> labels/...). If test label files exist locally — the
      organizer machine has them; a participant might have strays — the
      hidden GT would silently leak into the test table.
  Therefore: if the test split has NO label files on disk, use from_yolo
  (primary). If label files ARE present, skip the from_yolo* family entirely
  and build the table with ``tlc.TableWriter`` from the sorted image list —
  an images-only table by construction (fallback). Either way a post-import
  guard fails the job if the test table contains any boxes.

* collisions: ``from_yolo(if_exists="reuse")`` (the SDK default) returns the
  existing table for an identical (project, dataset, table) triple — verified:
  the second call returns the same URL, no duplicate revision. We detect
  "existed before" via ``Url.create_table_url(...).exists()`` and report
  "reused" instead of "created". Reuse can serve a STALE table if the data on
  disk changed after the first import, so validation always runs on the
  returned table — a stale table that no longer matches the competition
  counts fails the job rather than passing silently.

All heavy imports are inside functions: keeps plugin import cheap and makes
hot reload pick up changes (handlers resolve this module lazily).
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

# Competition ground truth: the Import card refuses anything that isn't the
# official starter-kit dataset.
EXPECTED_ROWS = {"train": 5910, "val": 733, "test": 715}
CANONICAL_CLASSES = [
    "Bicycle", "Boat", "Bottle", "Bus", "Car", "Cat",
    "Chair", "Cup", "Dog", "Motorbike", "People", "Table",
]
SPLITS = ("train", "val", "test")
DATASET_PREFIX = "exdark"

PARTICIPANT_FIX = (
    "Your local copy does not match the competition dataset. "
    "Re-download the starter kit and point Import at its dataset.yaml."
)

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def parse_dataset_yaml(yaml_path: str) -> dict[str, Any]:
    """Parse the YOLO dataset.yaml and resolve per-split image directories."""
    import yaml

    p = Path(yaml_path.strip().strip('"'))
    if not p.is_file():
        raise FileNotFoundError(f"dataset.yaml not found: {p}")
    with open(p, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if not isinstance(cfg, dict):
        raise ValueError(f"Not a YOLO dataset.yaml: {p}")

    root = Path(str(cfg.get("path", "") or "."))
    if not root.is_absolute():
        root = p.parent / root

    splits: dict[str, Path] = {}
    for split in SPLITS:
        rel = cfg.get(split)
        if not rel:
            continue
        d = Path(str(rel))
        if not d.is_absolute():
            d = root / d
        splits[split] = d.resolve()

    names = cfg.get("names", {})
    if isinstance(names, dict):
        class_names = [str(names[k]) for k in sorted(names, key=int)]
    else:
        class_names = [str(n) for n in names]

    return {
        "yaml_path": str(p.resolve()),
        "root": str(root.resolve()),
        "splits": splits,
        "nc": int(cfg.get("nc", len(class_names))),
        "class_names": class_names,
    }


def preflight(yaml_path: str) -> dict[str, Any]:
    """Read-only dry run: parse the yaml and diff it against the competition
    dataset. No table creation, no writes — cheap enough to call from a
    debounced input handler.

    Mirrors (but does not replace) the real checks in run_import: the same
    EXPECTED_ROWS / CANONICAL_CLASSES constants drive both, so preflight
    green means the pre-import and row-count checks will pass.
    """
    info = parse_dataset_yaml(yaml_path)  # raises on missing/unparsable yaml

    splits: dict[str, dict[str, Any]] = {}
    for split in SPLITS:
        entry: dict[str, Any] = {"expected": EXPECTED_ROWS[split], "found": None, "ok": False}
        d = info["splits"].get(split)
        if d is None:
            entry["error"] = "split not declared in dataset.yaml"
        else:
            entry["dir"] = str(d)
            try:
                entry["found"] = len(_list_images(d))
                entry["ok"] = entry["found"] == EXPECTED_ROWS[split]
            except FileNotFoundError:
                entry["error"] = "image directory not found"
        splits[split] = entry

    classes = {
        "count": info["nc"],
        "names": info["class_names"],
        "canonical": info["nc"] == 12 and info["class_names"] == CANONICAL_CLASSES,
    }

    # Informational, never gates all_ok: on the organizer machine (or a
    # participant with stray label files) the import will route test through
    # the TableWriter images-only path. Surfacing it here makes the GT-leak
    # guard visible BEFORE import instead of silent magic.
    test_dir = info["splits"].get("test")
    test_labels_on_disk = bool(test_dir is not None and _split_has_label_files(test_dir))

    return {
        "yaml_path": info["yaml_path"],
        "root": info["root"],
        "splits": splits,
        "classes": classes,
        "test_labels_on_disk": test_labels_on_disk,
        "all_ok": classes["canonical"] and all(s["ok"] for s in splits.values()),
    }


def _labels_dir_for(images_dir: Path) -> Path:
    """YOLO convention: swap the last 'images' path component for 'labels'."""
    parts = list(images_dir.parts)
    for i in range(len(parts) - 1, -1, -1):
        if parts[i].lower() == "images":
            parts[i] = "labels"
            return Path(*parts)
    return images_dir.parent / "labels" / images_dir.name


def _split_has_label_files(images_dir: Path) -> bool:
    labels_dir = _labels_dir_for(images_dir)
    if not labels_dir.is_dir():
        return False
    return any(f.suffix.lower() == ".txt" for f in labels_dir.iterdir() if f.is_file())


def _list_images(images_dir: Path) -> list[Path]:
    if not images_dir.is_dir():
        raise FileNotFoundError(f"Split image directory not found: {images_dir}")
    return sorted(
        (f for f in images_dir.iterdir() if f.is_file() and f.suffix.lower() in _IMAGE_EXTS),
        key=lambda f: f.name,
    )


def _value_map_labels(table: Any) -> list[str]:
    """Class names from a table's bbs value map, in index order."""
    vm = table.get_value_map("bbs.bb_list.label") or {}
    out: list[str] = []
    for key in sorted(vm, key=float):
        v = vm[key]
        out.append(getattr(v, "internal_name", None) or str(v))
    return out


def _count_boxes(table: Any) -> int:
    total = 0
    for i in range(table.row_count):
        total += len(table.table_rows[i]["bbs"]["bb_list"])
    return total


def _stems(table: Any) -> list[str]:
    return [Path(str(table.table_rows[i]["image"])).stem for i in range(table.row_count)]


def _import_labeled_split(
    info: dict[str, Any], split: str, project: str, table_name: str, force: bool = False
) -> tuple[Any, bool]:
    """from_yolo import for train/val. Returns (table, reused).

    ``force`` re-imports from disk over an existing table
    (``if_exists="overwrite"``) — destructive to revisions derived from it,
    so the UI confirms first (see table_revisions).
    """
    import tlc

    url = tlc.Url.create_table_url(table_name, f"{DATASET_PREFIX}_{split}", project)
    reused = url.exists() and not force
    table = tlc.Table.from_yolo(
        dataset_yaml_file=info["yaml_path"],
        split=split,
        task="detect",
        project_name=project,
        dataset_name=f"{DATASET_PREFIX}_{split}",
        table_name=table_name,
        if_exists="overwrite" if force else "reuse",
    )
    return table, reused


def _import_test_split(
    info: dict[str, Any], project: str, table_name: str, log: Callable[[str], None], force: bool = False
) -> tuple[Any, bool, str]:
    """Images-only test import. Returns (table, reused, mechanism)."""
    import tlc

    dataset_name = f"{DATASET_PREFIX}_test"
    url = tlc.Url.create_table_url(table_name, dataset_name, project)
    if url.exists() and not force:
        # Reuse — validation (row count, zero boxes, unique stems) still runs
        # on the reused table, so a stale or GT-leaked table cannot pass.
        return tlc.Table.from_url(url), True, "reuse-existing"

    images_dir = info["splits"]["test"]
    if not _split_has_label_files(images_dir):
        # Primary path (the participant reality): from_yolo tolerates a
        # labels-less split — 715 rows, empty bb_list, schema-consistent
        # with train/val. Verified empirically on tlc 2.22.3.1.
        log("test: no label files on disk — importing via Table.from_yolo (primary path)")
        table = tlc.Table.from_yolo(
            dataset_yaml_file=info["yaml_path"],
            split="test",
            task="detect",
            project_name=project,
            dataset_name=dataset_name,
            table_name=table_name,
            if_exists="overwrite" if force else "reuse",
        )
        return table, False, "from_yolo-labelless"

    # Fallback: label files exist for test (organizer machine / strays).
    # from_yolo AND from_yolo_url would auto-discover them (verified) and leak
    # hidden GT into the table, so build images-only with TableWriter instead.
    log("test: label files detected on disk — building images-only table via TableWriter (GT-leak guard)")
    images = _list_images(images_dir)
    writer = tlc.TableWriter(
        project_name=project,
        dataset_name=dataset_name,
        table_name=table_name,
        description="Competition test split (images only — hidden ground truth).",
        column_schemas={"image": tlc.ImagePath("image")},
        # Non-force: url.exists() was False above, anything else is a race.
        if_exists="overwrite" if force else "raise",
    )
    for img in images:
        writer.add_row({"image": str(img)})
    table = writer.finalize()
    return table, False, "tablewriter-images-only"


def run_import(params: dict[str, Any], ctx: Any) -> dict[str, Any]:
    """The Import job. Raises with a participant-facing message on failure.

    ``ctx`` is a jobs.JobCtx (log / set_checks); a bare function with those
    two attributes works too (used by the verification harness).
    """
    log = ctx.log
    set_checks = ctx.set_checks
    # Optional on ctx: the verification harness only guarantees log/set_checks.
    set_progress = getattr(ctx, "set_progress", lambda p: None)
    checks: list[dict[str, Any]] = []

    # Staged progress: ONE job drives the four per-split UI rows (train / val
    # / test / validate). Kept as a single job on purpose — the 9 checks are
    # cross-split and must stay together; only the reporting is staged.
    STAGES = ["train", "val", "test", "validate"]
    _stage_state: dict[str, Any] = {"current": None, "done": [], "started_at": {}, "finished_at": {}}

    def stage(name: str | None) -> None:
        now = time.time()
        cur = _stage_state["current"]
        if cur is not None:
            _stage_state["done"] = _stage_state["done"] + [cur]
            _stage_state["finished_at"] = {**_stage_state["finished_at"], cur: now}
        _stage_state["current"] = name
        if name is not None:
            _stage_state["started_at"] = {**_stage_state["started_at"], name: now}
        set_progress({"stages": STAGES, **_stage_state})

    def check(label: str, ok: bool, detail: str = "") -> bool:
        checks.append({"label": label, "ok": bool(ok), "detail": detail})
        set_checks(checks)
        log(("PASS " if ok else "FAIL ") + label + (f" — {detail}" if detail else ""))
        return ok

    yaml_path = str(params.get("dataset_yaml", "")).strip()
    project = str(params.get("project_name") or "exdark-competition").strip()
    table_name = str(params.get("table_name") or "initial").strip()
    # Splits to forcibly re-import from disk (overwrite instead of reuse).
    # The UI confirms revision loss before sending this (table_revisions).
    force_splits = {s for s in (params.get("force_splits") or []) if s in SPLITS}
    if force_splits:
        log(f"Force re-import requested for: {', '.join(sorted(force_splits))}")

    log(f"Parsing {yaml_path}")
    info = parse_dataset_yaml(yaml_path)

    # ── Pre-import checks on the yaml itself ────────────────────────────
    ok = check(
        "dataset.yaml declares train/val/test",
        all(s in info["splits"] for s in SPLITS),
        f"found: {sorted(info['splits'])}",
    )
    ok &= check(
        "12 classes in canonical order",
        info["nc"] == 12 and info["class_names"] == CANONICAL_CLASSES,
        f"nc={info['nc']}, names={info['class_names'][:3]}...",
    )
    if not ok:
        raise RuntimeError(PARTICIPANT_FIX)

    # ── Imports ─────────────────────────────────────────────────────────
    tables: dict[str, dict[str, Any]] = {}
    mechanisms: dict[str, str] = {}

    for split in ("train", "val"):
        stage(split)
        log(f"{split}: importing via Table.from_yolo ...")
        table, reused = _import_labeled_split(info, split, project, table_name, force=split in force_splits)
        tables[split] = {"url": str(table.url), "rows": table.row_count, "reused": reused, "_table": table}
        mechanisms[split] = "from_yolo" + (
            " (forced re-import)" if split in force_splits else " (reused existing)" if reused else ""
        )
        log(f"{split}: {'reused' if reused else 'created'} {table.url} ({table.row_count} rows)")

    stage("test")
    table, reused, mechanism = _import_test_split(info, project, table_name, log, force="test" in force_splits)
    tables["test"] = {"url": str(table.url), "rows": table.row_count, "reused": reused, "_table": table}
    mechanisms["test"] = mechanism + (
        " (forced re-import)" if "test" in force_splits else " (reused existing)" if reused else ""
    )
    log(f"test: {'reused' if reused else 'created'} {table.url} ({table.row_count} rows)")

    # ── Post-import validation ──────────────────────────────────────────
    stage("validate")
    ok = True
    for split in SPLITS:
        ok &= check(
            f"{split} row count == {EXPECTED_ROWS[split]}",
            tables[split]["rows"] == EXPECTED_ROWS[split],
            f"got {tables[split]['rows']}",
        )

    for split in ("train", "val"):
        labels = _value_map_labels(tables[split]["_table"])
        ok &= check(
            f"{split} value map is the canonical 12 classes",
            labels == CANONICAL_CLASSES,
            f"got {len(labels)} classes",
        )

    stems = _stems(tables["test"]["_table"])
    ok &= check(
        "test stems unique (one image_id per image)",
        len(set(stems)) == len(stems) == EXPECTED_ROWS["test"],
        f"{len(set(stems))} unique / {len(stems)} rows; e.g. {stems[0] if stems else '-'}",
    )

    test_table = tables["test"]["_table"]
    if "bbs" in test_table.table_rows[0]:
        n_boxes = _count_boxes(test_table)
        ok &= check("test table carries no ground-truth boxes", n_boxes == 0, f"{n_boxes} boxes found")
    else:
        check("test table carries no ground-truth boxes", True, "images-only schema (no bbs column)")

    if not ok:
        raise RuntimeError(PARTICIPANT_FIX)
    stage(None)  # closes "validate" with a finished_at timestamp

    for t in tables.values():
        t.pop("_table", None)

    result = {
        "project": project,
        "tables": tables,
        "mechanisms": mechanisms,
        "checks": checks,
    }

    # Persist the revisit snapshot (State 6). Table existence — re-verified
    # by verified_import_state on every read — is the source of truth; the
    # job_id is optional garnish that may outlive its pruned job record.
    try:
        from tlc_plugin_kaggle import config_store

        config_store.save(
            {
                "import_state": {
                    **result,
                    "table_name": table_name,
                    "dataset_yaml": yaml_path,
                    "job_id": getattr(ctx, "job_id", ""),
                    "finished_at": time.time(),
                }
            }
        )
    except Exception as exc:
        log(f"WARNING: could not persist the import-state snapshot ({exc}) — revisit view will start blank.")

    return result


def verified_import_state() -> dict[str, Any]:
    """The persisted last-successful-import snapshot, re-verified against disk.

    The Import tab's revisit view (State 6 -> State 4) and the stepper
    checkmark render from this. Verification order matters: table existence
    on disk decides, the snapshot only supplies the details — a snapshot
    whose tables were deleted reports state="empty" (fall back to the form),
    and a pruned job record downgrades gracefully (job_available=False).
    """
    import tlc

    from tlc_plugin_kaggle import config_store, jobs

    cfg = config_store.load() or {}
    snapshot = cfg.get("import_state") or {}
    tables = snapshot.get("tables")
    if not isinstance(tables, dict):
        # Pre-snapshot imports (older plugin versions): synthesize from the
        # canonical table URLs so the revisit view and the stepper agree.
        import_cfg = cfg.get("import") or {}
        project = str(import_cfg.get("project_name") or "exdark-competition").strip()
        table_name = str(import_cfg.get("table_name") or "initial").strip()
        urls = {s: tlc.Url.create_table_url(table_name, f"{DATASET_PREFIX}_{s}", project) for s in SPLITS}
        try:
            if all(u.exists() for u in urls.values()):
                return {
                    "state": "success",
                    "synthesized": True,  # no stored checks/rows — UI degrades gracefully
                    "snapshot": {
                        "project": project,
                        "table_name": table_name,
                        "tables": {s: {"url": str(u)} for s, u in urls.items()},
                    },
                    "verified": {s: True for s in SPLITS},
                    "job_available": False,
                }
        except Exception:
            pass
        return {"state": "empty"}

    verified: dict[str, bool] = {}
    for split in SPLITS:
        url = str((tables.get(split) or {}).get("url", ""))
        try:
            verified[split] = bool(url) and tlc.Url(url).exists()
        except Exception:
            verified[split] = False
    if not all(verified.values()):
        return {"state": "empty", "reason": "snapshot tables missing on disk", "verified": verified}

    job_id = str(snapshot.get("job_id") or "")
    return {
        "state": "success",
        "snapshot": snapshot,
        "verified": verified,
        "job_available": bool(job_id and jobs.get_job(job_id) is not None),
    }


def table_revisions(table_url: str) -> dict[str, Any]:
    """Best-effort revision info for the force-reimport confirmation guard.

    A forced overwrite of a base table orphans every revision derived from it
    — and label-edit-then-retrain is the whole Loop — so the UI must warn
    with a count when it can. ``revisions`` is the number of lineage steps
    from the latest revision back to this table, or None when the walk fails;
    the UI falls back to a generic always-confirm dialog then.
    """
    import tlc

    url = tlc.Url(table_url)
    if not url.exists():
        return {"exists": False, "has_revisions": False, "revisions": 0}
    base = tlc.Table.from_url(url)
    try:
        latest = base.latest(wait_for_rescan=False)
    except Exception:
        return {"exists": True, "has_revisions": None, "revisions": None}
    if str(latest.url) == str(base.url):
        return {"exists": True, "has_revisions": False, "revisions": 0, "latest_url": str(latest.url)}

    out: dict[str, Any] = {"exists": True, "has_revisions": True, "latest_url": str(latest.url)}
    try:
        # Walk latest -> base along the first-input lineage, counting steps.
        count, cur = 0, latest
        while str(cur.url) != str(base.url) and count < 200:
            inputs = list(getattr(cur, "input_tables", None) or [])
            if not inputs:
                break
            count += 1
            cur = tlc.Table.from_url(inputs[0])
        out["revisions"] = count if str(cur.url) == str(base.url) else None
    except Exception:
        out["revisions"] = None
    return out
