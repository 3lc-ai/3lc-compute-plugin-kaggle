"""Import card backend: competition dataset -> three 3LC tables + validation.

Import mechanism (decided empirically against tlc 2.22.3.1 on 2026-07-20;
re-verified against tlc 3.1.0 in the Phase-1 port spike, 2026-07-31):

* train / val: ``tlc.Table.from_yolo_url`` on each split's images directory
  (3.x removed ``from_yolo``; the yaml parsing this module already does now
  feeds images_url + categories directly), dataset names ``exdark_train`` /
  ``exdark_val``.

* test: the competition test split is images-only BY DESIGN (hidden GT).
  Probed behavior that drives the mechanism choice (re-proven on 3.1.0):
    - ``from_yolo_url`` on a genuinely labels-less split works fine: one row
      per image, zero instances, same schema as train/val. So on a
      participant machine (no test labels) it IS the primary path.
    - BUT ``from_yolo_url`` auto-discovers label files by the YOLO path
      convention (images/... -> labels/...). If test label files exist
      locally — the organizer machine has them; a participant might have
      strays — the hidden GT would silently leak into the test table.
  Therefore: if the test split has NO label files on disk, use from_yolo_url
  (primary). If label files ARE present, skip it entirely and build the table
  with ``tlc.TableWriter`` from the sorted image list — an images-only table
  by construction (fallback). Either way a post-import guard fails the job if
  the test table contains any boxes.

* collisions: ``from_yolo_url(if_exists="reuse")`` (the SDK default) returns
  the existing table for an identical (project, dataset, table) triple —
  verified on 3.1.0: the second call returns the same URL, no duplicate
  revision. We detect "existed before" via a constructed table URL's
  ``.exists()`` (3.x removed ``Url.create_table_url``; ``_table_url`` below
  rebuilds the deterministic layout from the configured project root). Reuse
  can serve a STALE table if the data on disk changed after the first import,
  so validation always runs on the returned table.

* 3.x row shape: boxes live at ``bbs.instances[*].bbs_2d`` (absolute XYXY)
  with labels in the parallel ``bbs.instances_additional_data.label`` list —
  the 2.x ``bbs.bb_list`` is gone. Box counting and the value-map path below
  follow the new shape.

All heavy imports are inside functions: keeps plugin import cheap and makes
worker restarts pick up changes (handlers resolve this module lazily).
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

from tlc_plugin_kaggle.constants import DATASET_PREFIX  # single definition site

PARTICIPANT_FIX = (
    "Your local copy does not match the competition dataset. "
    "Re-download the starter kit and point Import at its dataset.yaml."
)

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def parse_dataset_yaml(yaml_path: str) -> dict[str, Any]:
    """Parse the YOLO dataset.yaml and resolve per-split image directories."""
    import yaml

    # Path ergonomics: tolerate Windows "Copy as path" quoting, trailing
    # separators, and a path to the FOLDER containing dataset.yaml.
    cleaned = yaml_path.strip().strip('"').strip("'").strip()
    p = Path(cleaned.rstrip("\\/")) if cleaned else Path(cleaned)
    if p.is_dir() and (p / "dataset.yaml").is_file():
        p = p / "dataset.yaml"
    if not p.is_file():
        raise FileNotFoundError(f"No dataset.yaml found at: {p} — the yaml file or the folder containing it both work")
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
                images = _list_images(d)
                entry["found"] = len(images)
                # Stat-level readability check (no decoding — keeps preflight
                # fast): zero-byte or unstatable files flag a half-extracted
                # starter kit before it becomes a confusing training error.
                unreadable = 0
                for f in images:
                    try:
                        if f.stat().st_size == 0:
                            unreadable += 1
                    except OSError:
                        unreadable += 1
                entry["unreadable"] = unreadable
                entry["ok"] = entry["found"] == EXPECTED_ROWS[split] and unreadable == 0
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
        "plugin_version": _plugin_version(),
    }


def _plugin_version() -> str:
    """Cheap version identifier for the Copy-diagnostics block."""
    try:
        from tlc_plugin_kaggle import KagglePlugin

        return str(__import__("tlc_plugin_kaggle").__version__)
    except Exception:
        return "unknown"


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


def _project_root_url() -> str:
    """The configured 3LC project root (explicit config value, else default).

    3.x note: there is no public names->URL builder (Url.create_table_url is
    gone) and ROOT_URL's config default is computed lazily, so this falls back
    to tlcconfig's private default helper. Flagged upstream — swap to the
    public accessor when one exists.
    """
    import tlcconfig.options as tlc_options
    import tlcconfig.store as tlc_store

    val = tlc_store.ConfigStore.instance().get(tlc_options.ROOT_URL)
    if val:
        return str(val)
    return str(tlc_options._get_default_root_url())


def _table_url(table_name: str, dataset_name: str, project: str) -> Any:
    """Deterministic table URL (the 2.x Url.create_table_url layout), 3.x-built.

    Same argument order as the removed helper so call sites read unchanged:
    ``.../projects/<project>/datasets/<dataset>/tables/<table>``.
    """
    import tlc

    return tlc.Url(_project_root_url()) / project / "datasets" / dataset_name / "tables" / table_name


def _categories(info: dict[str, Any]) -> dict[int, str]:
    """from_yolo_url's categories mapping from the parsed yaml class list."""
    return {i: name for i, name in enumerate(info["class_names"])}


def _value_map_labels(table: Any) -> list[str]:
    """Class names from a table's bbs value map, in index order (3.x path)."""
    vm = table.get_value_map("bbs.instances_additional_data.label") or {}
    out: list[str] = []
    for key in sorted(vm, key=float):
        v = vm[key]
        name = v.get("internal_name") if isinstance(v, dict) else getattr(v, "internal_name", None)
        out.append(name or str(v))
    return out


def _count_boxes(table: Any) -> int:
    """Instance count across the table (3.x: one instance = one box)."""
    total = 0
    for i in range(table.row_count):
        total += len(table.table_rows[i]["bbs"]["instances"])
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

    url = _table_url(table_name, f"{DATASET_PREFIX}_{split}", project)
    reused = url.exists() and not force
    table = tlc.Table.from_yolo_url(
        info["splits"][split].as_posix(),
        categories=_categories(info),
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
    url = _table_url(table_name, dataset_name, project)
    if url.exists() and not force:
        # Reuse — validation (row count, zero boxes, unique stems) still runs
        # on the reused table, so a stale or GT-leaked table cannot pass.
        return tlc.Table.from_url(url), True, "reuse-existing"

    images_dir = info["splits"]["test"]
    if not _split_has_label_files(images_dir):
        # Primary path (the participant reality): from_yolo_url tolerates a
        # labels-less split — one row per image, zero instances,
        # schema-consistent with train/val. Verified on tlc 2.22.3.1 AND 3.1.0.
        log("test: no label files on disk — importing via Table.from_yolo_url (primary path)")
        table = tlc.Table.from_yolo_url(
            images_dir.as_posix(),
            categories=_categories(info),
            task="detect",
            project_name=project,
            dataset_name=dataset_name,
            table_name=table_name,
            if_exists="overwrite" if force else "reuse",
        )
        return table, False, "from_yolo_url-labelless"

    # Fallback: label files exist for test (organizer machine / strays).
    # from_yolo_url would auto-discover them (verified on 3.1.0 too) and leak
    # hidden GT into the table, so build images-only with TableWriter instead.
    log("test: label files detected on disk — building images-only table via TableWriter (GT-leak guard)")
    images = _list_images(images_dir)
    writer = tlc.TableWriter(
        project_name=project,
        dataset_name=dataset_name,
        table_name=table_name,
        description="Competition test split (images only — hidden ground truth).",
        schema={"image": tlc.schemas.ImageSchema()},
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
        log(f"{split}: importing via Table.from_yolo_url ...")
        table, reused = _import_labeled_split(info, split, project, table_name, force=split in force_splits)
        tables[split] = {"url": str(table.url), "rows": table.row_count, "reused": reused, "_table": table}
        mechanisms[split] = "from_yolo_url" + (
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
    # The snapshot keeps only what is not derivable (tables/mechanisms/
    # checks/job_id): project/table_name/dataset_yaml live in the session,
    # and a second copy here is the divergence class session_v1 retired.
    try:
        from tlc_plugin_kaggle import config_store

        config_store.save(
            {
                "import_state": {
                    **{k: v for k, v in result.items() if k != "project"},
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
        # The session (populated by the session_v1 migration at load) is the
        # one store of the project/table facts.
        from tlc_plugin_kaggle import constants

        sess = cfg.get("session") or {}
        project = str(sess.get("project_name") or constants.DEFAULT_PROJECT).strip()
        table_name = str(sess.get("table_name") or constants.DEFAULT_TABLE).strip()
        urls = {s: _table_url(table_name, f"{DATASET_PREFIX}_{s}", project) for s in SPLITS}
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


def list_project_tables(project: str) -> dict[str, Any]:
    """Datasets and their revision chains for the revision picker.

    Layout-derived: _table_url rebuilds the deterministic
    ``.../projects/<project>/datasets/<dataset>/tables/<table>`` shape, so
    the datasets root is walked directly (verified live, 2026-07-21; table
    loads are milliseconds at this project's scale). Chain order is lineage
    (parent = first input_tables entry inside the same dataset), root first,
    following the newest child at each step; off-chain branches append in
    mtime order. The ``latest`` flag comes from tlc's own latest() on the
    chain root — the same resolution ``use_latest`` training follows.
    """
    import tlc

    probe = _table_url("initial", "__probe__", project)
    datasets_root = Path(str(probe)).parent.parent.parent
    out: dict[str, Any] = {"project": project, "datasets": []}
    if not datasets_root.is_dir():
        return out

    for ds_dir in sorted(p for p in datasets_root.iterdir() if p.is_dir()):
        tables_dir = ds_dir / "tables"
        if not tables_dir.is_dir():
            continue
        entries: dict[str, dict[str, Any]] = {}
        for tdir in tables_dir.iterdir():
            if not tdir.is_dir():
                continue
            try:
                table = tlc.Table.from_url(tlc.Url(tdir.as_posix()))
                entries[str(table.url)] = {
                    "name": tdir.name,
                    "url": str(table.url),
                    "rows": table.row_count,
                    "_inputs": [str(u) for u in (getattr(table, "input_tables", None) or [])],
                    "_mtime": tdir.stat().st_mtime,
                }
            except Exception:
                continue  # unreadable table folder: skip, never fail the listing
        if not entries:
            continue

        children: dict[str, list[str]] = {}
        roots: list[str] = []
        for url, e in entries.items():
            parent = next((i for i in e["_inputs"] if i in entries), None)
            if parent:
                children.setdefault(parent, []).append(url)
            else:
                roots.append(url)

        ordered: list[dict[str, Any]] = []
        seen: set[str] = set()
        for root in sorted(roots, key=lambda u: entries[u]["_mtime"]):
            cur: str | None = root
            while cur and cur not in seen:
                seen.add(cur)
                ordered.append(entries[cur])
                kids = sorted(children.get(cur, []), key=lambda u: entries[u]["_mtime"])
                cur = kids[-1] if kids else None
        for url, e in sorted(entries.items(), key=lambda kv: kv[1]["_mtime"]):
            if url not in seen:
                ordered.append(e)

        latest_url = ""
        try:
            base = tlc.Table.from_url(tlc.Url(ordered[0]["url"]))
            latest_url = str(base.latest().url)
        except Exception:
            latest_url = ordered[-1]["url"]  # lineage tail as fallback
        rows = [
            {"name": e["name"], "url": e["url"], "rows": e["rows"], "latest": e["url"] == latest_url}
            for e in ordered
        ]
        out["datasets"].append({"name": ds_dir.name, "tables": rows, "latest_url": latest_url})
    return out


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
        latest = base.latest()
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
