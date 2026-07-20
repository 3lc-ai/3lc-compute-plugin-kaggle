"""Predict + Submit card backend: weights -> inference -> submission.csv -> Kaggle.

Submission schema (must match competition_exdark/metric/metric_exdark.py):
    columns: id, image_id, prediction_string
    id: 0..714 aligned to image_id sorted ascending
    prediction_string: groups of 6 values "class conf xc yc w h" (YOLO
    normalized, all in [0,1], class an integer 0-11), or literally "no box".

The pre-flight validator below re-implements the metric parser's STRICT rules
with the same participant-facing message style, so a format error can never
burn a real Kaggle submission — it fails the job locally instead.

Kaggle credentials: read by the kaggle package from ~/.kaggle/kaggle.json
ONLY — the plugin never stores or forwards credentials. NOTE: kaggle 2.x
authenticates AT IMPORT TIME and raises without credentials, so the import
lives inside the submit step and its failure is treated as "credentials
missing": steps 1-4 (inference, CSV, validation, save) still complete so the
CSV exists for manual upload.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

EXPECTED_TEST_ROWS = 715
NUM_CLASSES = 12
SUBMISSION_COLUMNS = ["id", "image_id", "prediction_string"]
DEFAULT_SAVE_ROOT = r"C:\Users\Owner\Desktop\3LC Kaggle Competitions\runs\kaggle-plugin"

# Host-machine convenience only: when the competition metric and solution file
# exist locally (the organizer machine), each submission is also scored
# locally and the mAP shown next to the CSV. Participant machines don't have
# these files, so the whole step silently no-ops there.
LOCAL_METRIC_PY = r"C:\Users\Owner\Desktop\3LC Kaggle Competitions\competition_exdark\metric\metric_exdark.py"
LOCAL_SOLUTION_CSV = r"C:\Users\Owner\Desktop\3LC Kaggle Competitions\competition_exdark\kaggle_upload\solution.csv"

CREDENTIALS_HELP = (
    "Kaggle credentials not found. Create an API token on kaggle.com "
    "(Settings -> API -> Create New Token) and save it as "
    "~/.kaggle/access_token (new KGAT_... tokens; Windows: "
    "C:\\Users\\<you>\\.kaggle\\access_token, plain text, no BOM) — or set the "
    "KAGGLE_API_TOKEN environment variable. Legacy ~/.kaggle/kaggle.json "
    "also works. The generated submission.csv is saved locally — you can "
    "always upload it manually on the competition's Submit page."
)


def kaggle_credentials_present() -> bool:
    """Any of the auth sources the kaggle client reads (new KGAT access
    token, env var, or legacy kaggle.json)."""
    import os

    kaggle_dir = Path.home() / ".kaggle"
    return (
        (kaggle_dir / "access_token").is_file()
        or (kaggle_dir / "kaggle.json").is_file()
        or bool(os.environ.get("KAGGLE_API_TOKEN"))
        or bool(os.environ.get("KAGGLE_USERNAME") and os.environ.get("KAGGLE_KEY"))
    )


# ── Step 1: inference ────────────────────────────────────────────────────


def _test_items(table: Any) -> list[tuple[str, str]]:
    """(image_id, image_path) per row — image_id is the filename stem."""
    items = []
    for i in range(table.row_count):
        path = str(table.table_rows[i]["image"])
        items.append((Path(path).stem, path))
    return items


def run_inference(
    weights: str,
    items: list[tuple[str, str]],
    conf: float,
    device: Any,
    ctx: Any,
) -> dict[str, str]:
    """YOLO inference -> {image_id: prediction_string}. Locked imgsz=640."""
    from ultralytics import YOLO

    model = YOLO(weights)
    pred_map: dict[str, str] = {}
    total = len(items)
    results = model.predict(
        source=[p for _, p in items],
        imgsz=640,
        conf=conf,
        device=device,
        max_det=300,
        stream=True,
        verbose=False,
        # note: no dataloader workers in predict's streaming path — the
        # Windows workers=0 rule is inherently satisfied here
    )
    for n, (item, result) in enumerate(zip(items, results), start=1):
        image_id = item[0]
        parts: list[str] = []
        boxes = result.boxes
        if boxes is not None and len(boxes):
            cls = boxes.cls.tolist()
            confs = boxes.conf.tolist()
            xywhn = boxes.xywhn.tolist()
            for c, cf, (xc, yc, w, h) in zip(cls, confs, xywhn):
                c = int(c)
                if not 0 <= c < NUM_CLASSES:
                    continue  # defensive: never emit an out-of-range class
                clamp = lambda v: min(1.0, max(0.0, float(v)))  # noqa: E731
                parts.append(
                    f"{c} {clamp(cf):.6f} {clamp(xc):.6f} {clamp(yc):.6f} {clamp(w):.6f} {clamp(h):.6f}"
                )
        pred_map[image_id] = " ".join(parts) if parts else "no box"
        if n % 50 == 0 or n == total:
            ctx.set_progress({"images": n, "total_images": total})
    return pred_map


# ── Step 2: submission dataframe ─────────────────────────────────────────


def build_submission_df(pred_map: dict[str, str]) -> Any:
    import pandas as pd

    image_ids = sorted(pred_map)
    return pd.DataFrame(
        {
            "id": range(len(image_ids)),
            "image_id": image_ids,
            "prediction_string": [pred_map[i] for i in image_ids],
        }
    )


# ── Step 3: pre-flight validation (mirrors metric_exdark.py exactly) ────


def _validate_prediction_string(pred_str: str, image_id: str) -> None:
    """The metric parser's strict rules, same messages, ValueError instead."""
    s = str(pred_str).strip()
    if s == "" or s.lower() == "no box":
        return
    where = f" (image_id {image_id!r})"
    try:
        values = list(map(float, s.split()))
    except ValueError:
        raise ValueError(f"prediction_string contains non-numeric values{where}.")
    if len(values) % 6 != 0:
        raise ValueError(
            "prediction_string must contain groups of 6 values "
            f"(class_id confidence x_center y_center width height); "
            f"got {len(values)} values{where}."
        )
    for i in range(0, len(values), 6):
        class_id, conf, xc, yc, w, h = values[i : i + 6]
        coords_ok = 0 <= xc <= 1 and 0 <= yc <= 1 and 0 <= w <= 1 and 0 <= h <= 1
        class_ok = float(class_id).is_integer() and 0 <= class_id <= 11
        conf_ok = 0 <= conf <= 1
        if not (coords_ok and class_ok and conf_ok):
            raise ValueError(
                "Invalid box values: class_id must be an integer in 0-11, "
                "confidence and coordinates must be in [0, 1]; got "
                f"'{' '.join(f'{v:g}' for v in values[i : i + 6])}'{where}."
            )


def validate_submission_df(df: Any, expected_rows: int = EXPECTED_TEST_ROWS) -> list[dict[str, Any]]:
    """Raise ValueError (participant-facing) on the first violation."""
    checks: list[dict[str, Any]] = []

    def check(label: str, ok: bool, detail: str, message: str) -> None:
        checks.append({"label": label, "ok": bool(ok), "detail": detail})
        if not ok:
            raise ValueError(message)

    check(
        "columns are id, image_id, prediction_string",
        list(df.columns) == SUBMISSION_COLUMNS,
        f"got {list(df.columns)}",
        f"Submission must have exactly the columns {SUBMISSION_COLUMNS}.",
    )
    check(
        f"exactly {expected_rows} rows (one per test image)",
        len(df) == expected_rows,
        f"got {len(df)}",
        f"Submission must contain exactly {expected_rows} rows; got {len(df)}. "
        "Re-run Import to rebuild the test table, then predict again.",
    )
    dup = df["image_id"].astype(str).duplicated()
    check(
        "no duplicated image_id rows",
        not dup.any(),
        f"{int(dup.sum())} duplicates",
        f"Submission contains {int(dup.sum())} duplicated image_id row(s); "
        "submit exactly one row per test image.",
    )
    ids_ok = list(df["id"]) == list(range(len(df)))
    sorted_ok = list(df["image_id"]) == sorted(df["image_id"].astype(str))
    check(
        "id column is 0..N-1 aligned to sorted image_id",
        ids_ok and sorted_ok,
        "aligned" if ids_ok and sorted_ok else "misaligned",
        "Submission ids must be 0..714 aligned to image_id sorted ascending.",
    )
    for _, row in df.iterrows():
        _validate_prediction_string(row["prediction_string"], str(row["image_id"]))
    n_boxes = sum(
        0 if str(p).strip().lower() in ("", "no box") else len(str(p).split()) // 6
        for p in df["prediction_string"]
    )
    checks.append(
        {"label": "all prediction_strings parse under the metric's strict rules",
         "ok": True, "detail": f"{n_boxes} boxes total"}
    )
    return checks


def try_local_score(csv_path: str, ctx: Any) -> float | None:
    """Score the CSV with the real competition metric when it exists on disk.

    Returns None (silently) when metric/solution files are absent — the
    normal case on participant machines. Errors while the files ARE present
    get one log line and still return None: local scoring is a convenience
    and must never fail the job.
    """
    try:
        metric_py = Path(LOCAL_METRIC_PY)
        solution_csv = Path(LOCAL_SOLUTION_CSV)
        if not (metric_py.is_file() and solution_csv.is_file()):
            return None
        import importlib.util

        import pandas as pd

        spec = importlib.util.spec_from_file_location("metric_exdark", metric_py)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        score = float(module.score(pd.read_csv(solution_csv), pd.read_csv(csv_path), "id"))
        ctx.log(f"Local metric score (mAP@0.5): {score:.6f}")
        return score
    except Exception as exc:
        ctx.log(f"Local scoring skipped ({type(exc).__name__}: {exc})")
        return None


# ── Step 5: Kaggle submit ────────────────────────────────────────────────


def submit_to_kaggle(csv_path: str, message: str, slug: str, ctx: Any) -> dict[str, Any]:
    """Submit via the kaggle package. Credentials from ~/.kaggle/kaggle.json ONLY."""
    if not slug or slug.strip() in ("", "[SLUG]"):
        return {
            "status": "skipped",
            "reason": "No competition slug configured — set it on the card once the competition is live.",
        }
    if not kaggle_credentials_present():
        return {"status": "skipped", "reason": CREDENTIALS_HELP}
    try:
        # kaggle 2.x authenticates at import time — keep the import in here.
        from kaggle.api.kaggle_api_extended import KaggleApi

        api = KaggleApi()
        api.authenticate()
    except Exception as exc:
        return {"status": "skipped", "reason": f"{CREDENTIALS_HELP} (auth error: {exc})"}
    try:
        response = api.competition_submit(file_name=csv_path, message=message, competition=slug.strip())
        ref = getattr(response, "ref", None) or str(response)
        ctx.log(f"Kaggle accepted the submission: {ref}")
        return {"status": "submitted", "response": str(response), "ref": str(ref)}
    except Exception as exc:
        return {"status": "failed", "reason": f"Kaggle rejected the submission: {exc}"}


def kaggle_live_status(slug: str) -> dict[str, Any]:
    """Live Kaggle state for the Status card. Sync, no job; every API call is
    individually fenced so partial data still renders. Graceful states:
    connected=False (no kaggle.json) and configured=False (no slug)."""
    if not kaggle_credentials_present():
        return {
            "connected": False,
            "reason": "Connect your Kaggle account: create an API token on kaggle.com "
            "(Settings -> API -> Create New Token) and save it as ~/.kaggle/access_token "
            "(or set KAGGLE_API_TOKEN; legacy ~/.kaggle/kaggle.json also works).",
        }
    slug = (slug or "").strip()
    if not slug or slug == "[SLUG]":
        return {
            "connected": True,
            "configured": False,
            "reason": "Set the competition slug (card 3) once the competition is live.",
        }
    out: dict[str, Any] = {"connected": True, "configured": True, "slug": slug}
    try:
        from kaggle.api.kaggle_api_extended import KaggleApi  # import-time auth: keep in here

        api = KaggleApi()
        api.authenticate()
    except Exception as exc:
        return {"connected": False, "reason": f"Kaggle authentication failed: {exc}"}

    try:
        subs = api.competition_submissions(slug)
        rows = []
        best = None
        for s in subs[:10]:
            public = getattr(s, "public_score", None) or getattr(s, "publicScore", None)
            try:
                public_f = float(public)
            except (TypeError, ValueError):
                public_f = None
            if public_f is not None:
                best = public_f if best is None else max(best, public_f)
            rows.append(
                {
                    "date": str(getattr(s, "date", "") or ""),
                    "message": str(getattr(s, "description", "") or ""),
                    "status": str(getattr(s, "status", "") or ""),
                    "public_score": public,
                }
            )
        out["submissions"] = rows
        out["best_public_score"] = best
    except Exception as exc:
        out["submissions_error"] = str(exc)

    try:
        import json as _json

        username = ""
        try:
            creds = _json.loads((Path.home() / ".kaggle" / "kaggle.json").read_text(encoding="utf-8"))
            username = str(creds.get("username", ""))
        except Exception:
            pass
        board = api.competition_leaderboard_view(slug)
        top = []
        rank = None
        for i, entry in enumerate(board[:50], start=1):
            team = str(getattr(entry, "team_name", "") or getattr(entry, "teamName", "") or "")
            score = getattr(entry, "score", None)
            if i <= 5:
                top.append({"rank": i, "team": team, "score": str(score)})
            if username and team.lower() == username.lower():
                rank = {"rank": i, "team": team, "score": str(score)}
        out["leaderboard_top"] = top
        out["my_rank"] = rank  # best-effort: only when team name == username
    except Exception as exc:
        out["leaderboard_error"] = str(exc)
    return out


# ── The job ──────────────────────────────────────────────────────────────


def run_predict_submit(params: dict[str, Any], ctx: Any) -> dict[str, Any]:
    import tlc

    weights = str(params.get("weights_path", "")).strip().strip('"')
    if not weights or not Path(weights).is_file():
        raise ValueError(f"Weights file not found: {weights or '(empty)'}")
    run_name = str(params.get("run_name") or Path(weights).parent.parent.name)

    table = tlc.Table.from_url(tlc.Url(str(params["test_table_url"]).strip().strip('"')))
    items = _test_items(table)
    ctx.log(f"Test table: {table.url} ({len(items)} images)")
    if len(items) != EXPECTED_TEST_ROWS:
        raise ValueError(
            f"Test table has {len(items)} rows; the competition test split has "
            f"{EXPECTED_TEST_ROWS}. Re-run Import against the starter kit's dataset.yaml."
        )

    conf = float(params.get("conf", 0.25) or 0.25)
    device = params.get("device", "0")
    if str(device).strip().isdigit():
        device = int(str(device).strip())

    ctx.log(f"Running inference: {Path(weights).name}, imgsz=640 (locked), conf={conf}, device={device}")
    pred_map = run_inference(weights, items, conf, device, ctx)

    df = build_submission_df(pred_map)

    # Pre-flight BEFORE any upload. On failure the CSV is still written with
    # an .INVALID marker for debugging, then the job fails participant-facing.
    out_dir = Path(str(params.get("save_root") or DEFAULT_SAVE_ROOT)) / run_name / "submissions"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    try:
        checks = validate_submission_df(df)
        ctx.set_checks(checks)
        for c in checks:
            ctx.log(("PASS " if c["ok"] else "FAIL ") + c["label"] + f" — {c['detail']}")
    except ValueError:
        bad_path = out_dir / f"submission_{stamp}.INVALID.csv"
        df.to_csv(bad_path, index=False)
        ctx.log(f"Pre-flight failed; unvalidated CSV kept for debugging: {bad_path}")
        raise

    csv_path = out_dir / f"submission_{stamp}.csv"
    df.to_csv(csv_path, index=False)
    ctx.set_field("csv_path", str(csv_path))
    ctx.log(f"submission.csv written: {csv_path}")

    local_score = try_local_score(str(csv_path), ctx)
    if local_score is not None:
        ctx.set_field("local_score", local_score)

    message = str(params.get("message") or f"{run_name} via 3LC plugin")
    slug = str(params.get("competition_slug", "")).strip()
    if bool(params.get("csv_only", False)):
        submission = {"status": "skipped", "reason": "CSV-only mode — no upload requested."}
    else:
        submission = submit_to_kaggle(str(csv_path), message, slug, ctx)
    ctx.set_field("submission", submission)
    if submission["status"] != "submitted":
        ctx.log(f"Submit step: {submission['status']} — {submission.get('reason', '')}")

    n_boxes = sum(0 if p == "no box" else len(p.split()) // 6 for p in pred_map.values())
    return {
        "run_name": run_name,
        "weights": weights,
        "csv_path": str(csv_path),
        "rows": len(df),
        "total_boxes": n_boxes,
        "conf": conf,
        "local_score": local_score,
        "submission": submission,
    }
