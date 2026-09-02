# Copyright 2026 3LC Inc.
# SPDX-License-Identifier: AGPL-3.0-only
"""Predict + Submit card backend: weights -> inference -> submission.csv -> Kaggle.

Submission schema (must match competition_exdark/metric/metric_exdark.py):
    columns: id, image_id, prediction_string
    id: 0..714 aligned to image_id sorted ascending
    prediction_string: groups of 6 values "class conf xc yc w h" (YOLO
    normalized, all in [0,1], class an integer 0-11), or literally "no box".

The pre-flight validator below re-implements the metric parser's STRICT rules
with the same participant-facing message style, so a format error can never
burn a real Kaggle submission — it fails the job locally instead.

Kaggle credentials: read by the kaggle package from its own auth sources
(~/.kaggle/access_token KGAT token preferred, legacy ~/.kaggle/kaggle.json,
or the KAGGLE_* env vars — see kaggle_credentials_present) — the plugin
never stores or forwards credentials. NOTE: kaggle 2.x
authenticates AT IMPORT TIME and raises without credentials, so the import
lives inside the submit step and its failure is treated as "credentials
missing": steps 1-4 (inference, CSV, validation, save) still complete so the
CSV exists for manual upload.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

# ── SWAP AT PUBLIC LAUNCH ────────────────────────────────────────────────
# Single source for the Submit tab's slug default and the join link. This is
# the private test competition — the "comepetition" typo is real, it's in the
# Kaggle URL. Replace the value with the public competition slug at launch.
COMPETITION_SLUG = "the-3-lc-low-light-object-detection-comepetition-test"

EXPECTED_TEST_ROWS = 715
NUM_CLASSES = 12
SUBMISSION_COLUMNS = ["id", "image_id", "prediction_string"]
# Same portable-default rule as trainer.DEFAULT_SAVE_ROOT (kept in sync by
# hand): organizer machine keeps its historical location, everywhere else
# fall back to a per-user dir that mkdir can create without elevation.
_ORGANIZER_SAVE_ROOT = Path(r"C:\Users\Owner\Desktop\3LC Kaggle Competitions\runs\kaggle-plugin")
DEFAULT_SAVE_ROOT = str(
    _ORGANIZER_SAVE_ROOT
    if _ORGANIZER_SAVE_ROOT.parent.is_dir()
    else Path.home() / ".3lc-kaggle-plugin" / "runs"
)


def competition_url(slug: str) -> str:
    return f"https://www.kaggle.com/competitions/{slug.strip()}"

# Host-machine convenience only: when the competition metric and solution file
# exist locally (the organizer machine), each submission is also scored
# locally and the mAP shown next to the CSV. Participant machines don't have
# these files, so the whole step silently no-ops there.
LOCAL_METRIC_PY = r"C:\Users\Owner\Desktop\3LC Kaggle Competitions\competition_exdark\metric\metric_exdark.py"
LOCAL_SOLUTION_CSV = r"C:\Users\Owner\Desktop\3LC Kaggle Competitions\competition_exdark\kaggle_upload\solution.csv"


def is_host() -> bool:
    """Organizer-machine check — the same files that gate local scoring.
    Participants never have the metric + solution on disk, so this gates the
    host-only surfaces too: the direct weights-file source (predictions are
    plugin-run-only for participants) and the local score display."""
    return Path(LOCAL_METRIC_PY).is_file() and Path(LOCAL_SOLUTION_CSV).is_file()

CREDENTIALS_HELP = (
    "Kaggle credentials not found. Create an API token on kaggle.com "
    "(Settings -> API -> Create New Token; new tokens look like KGAT_...) "
    "and save it to ~/.kaggle/access_token. On Windows PowerShell "
    "(the kaggle.com dialog shows bash commands that will NOT work here): "
    'mkdir "$env:USERPROFILE\\.kaggle" -Force; '
    'Set-Content -Path "$env:USERPROFILE\\.kaggle\\access_token" '
    '-Value "KGAT_<your token>" -NoNewline -Encoding ascii '
    "(plain text, no BOM, no trailing newline). Alternatively set the "
    "KAGGLE_API_TOKEN environment variable; legacy ~/.kaggle/kaggle.json "
    "also works. The generated submission.csv is saved locally, so you can "
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


def _authenticated_api() -> tuple[Any, str]:
    """(api, "") on success, (None, reason) otherwise. kaggle 2.x
    authenticates at import time — keep the import in here."""
    if not kaggle_credentials_present():
        return None, CREDENTIALS_HELP
    try:
        from kaggle.api.kaggle_api_extended import KaggleApi

        api = KaggleApi()
        api.authenticate()
        return api, ""
    except Exception as exc:
        return None, f"Kaggle authentication failed: {exc}"


def _api_username(api: Any) -> str:
    """Username the client resolved during authenticate() — for KGAT access
    tokens it is introspected from the token, so no extra API call here."""
    try:
        return str(api.config_values.get("username", "") or "")
    except Exception:
        return ""


def get_competition_info(api: Any, slug: str) -> dict[str, Any]:
    """One cheap GetCompetition call: joined-state + daily limit.

    Verified against kaggle 2.2.3 / kagglesdk 0.1.34 (2026-07-20):
    user_has_entered=True + max_daily_submissions=3 on the test competition,
    user_has_entered=False on a not-joined competition.
    """
    from kagglesdk.competitions.types.competition_api_service import ApiGetCompetitionRequest

    with api.build_kaggle_client() as client:
        request = ApiGetCompetitionRequest()
        request.competition_name = slug.strip()
        comp = client.competitions.competition_api_client.get_competition(request)
    return {
        "user_has_entered": bool(comp.user_has_entered),
        "max_daily_submissions": int(comp.max_daily_submissions or 0),
        "title": str(comp.title or ""),
    }


def _submissions_used_today(api: Any, slug: str) -> int | None:
    """Proactive 'X of N used today' counter, fully defensive.

    LAUNCH-VERIFY: ListSubmissions 403s on the private test competition even
    for a joined user, so this returns None there and the counter simply
    doesn't render. Verify it comes alive on the public competition.
    Kaggle submission timestamps are UTC; the daily limit resets midnight UTC.
    """
    try:
        from datetime import datetime, timezone

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        subs = api.competition_submissions(slug)
        return sum(1 for s in subs if str(getattr(s, "date", "")).startswith(today))
    except Exception:
        return None


def kaggle_connection(slug: str = "") -> dict[str, Any]:
    """Three-state connection panel for the Submit tab, checked in order:
    no_credentials -> not_joined -> ready."""
    slug = (slug or COMPETITION_SLUG).strip()
    out: dict[str, Any] = {
        "default_slug": COMPETITION_SLUG,
        "slug": slug,
        "competition_url": competition_url(slug),
    }
    api, reason = _authenticated_api()
    if api is None:
        return {**out, "state": "no_credentials", "help": reason}
    out["username"] = _api_username(api)
    try:
        info = get_competition_info(api, slug)
    except Exception as exc:
        # Probe failed (bad slug, network, permission) — the credential itself
        # works, so stay usable and let the submit path report specifics.
        return {**out, "state": "ready", "probe_error": str(exc)}
    out["daily_limit"] = info["max_daily_submissions"]
    out["competition_title"] = info["title"]
    if not info["user_has_entered"]:
        return {**out, "state": "not_joined"}
    used = _submissions_used_today(api, slug)
    if used is not None:
        out["submissions_used_today"] = used
    return {**out, "state": "ready"}


def classify_kaggle_error(exc: Exception) -> str:
    """'daily_limit' | 'not_joined' | 'error' from a submit-call exception.

    kagglesdk surfaces Kaggle's own JSON 'message' verbatim as the HTTPError
    text, so substring matching on the participant-facing phrasing is the
    available signal. LAUNCH-VERIFY: exercise the daily-limit branch live on
    the public competition (the private test comp allows 3/day and burning
    them for a test isn't worth it).
    """
    low = str(exc).lower()
    if ("daily" in low and ("limit" in low or "submission" in low)) or "submission limit" in low or (
        "maximum" in low and ("per day" in low or "today" in low)
    ):
        return "daily_limit"
    if ("rules" in low and "accept" in low) or "must accept" in low or "not accepted" in low:
        return "not_joined"
    return "error"


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
    # Determinate progress from the first tick: total is known up front,
    # then per-image counts flushed at most ~1/s (each set_progress writes
    # the job JSON) plus a final exact count.
    ctx.set_progress({"images": 0, "total_images": total})
    last_flush = 0.0
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
        now = time.time()
        if n == total or now - last_flush >= 1.0:
            last_flush = now
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


def build_sanity_summary(pred_map: dict[str, str]) -> dict[str, Any]:
    """Pre-submit sanity numbers: totals, boxes/image, per-class counts, and
    a soft degenerate-output warning. Informational only — never blocks."""
    from tlc_plugin_kaggle.importer import CANONICAL_CLASSES

    per_class = {name: 0 for name in CANONICAL_CLASSES}
    total = 0
    empty_images = 0
    for pred in pred_map.values():
        s = str(pred).strip()
        if s == "" or s.lower() == "no box":
            empty_images += 1
            continue
        values = s.split()
        for i in range(0, len(values) - 5, 6):
            cls = int(float(values[i]))
            if 0 <= cls < len(CANONICAL_CLASSES):
                per_class[CANONICAL_CLASSES[cls]] += 1
                total += 1
    n_images = max(len(pred_map), 1)
    mean = total / n_images
    summary: dict[str, Any] = {
        "total_boxes": total,
        "images": len(pred_map),
        "empty_images": empty_images,
        "boxes_per_image_mean": round(mean, 2),
        "per_class": per_class,
    }
    if mean < 1.0:
        summary["warning"] = (
            f"{total} boxes across {len(pred_map)} images is unusually low. "
            "Are these fully-trained weights? (Submitting is still fine.)"
        )
    return summary


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
    """Submit via the kaggle package. Credentials are read by the kaggle
    client from its own sources only — the plugin never stores them.

    Non-fatal outcomes are friendly states, not failures: missing credentials
    and the daily submission limit both leave the validated CSV on disk for a
    later or manual upload.
    """
    slug = (slug or COMPETITION_SLUG).strip()
    if slug == "[SLUG]":
        slug = COMPETITION_SLUG
    api, reason = _authenticated_api()
    if api is None:
        return {"status": "skipped", "reason": reason}

    # Cheap pre-probe: a submit against a not-joined competition can't
    # succeed, so report the friendly state without burning the attempt.
    # Probe failure is not a verdict — fall through and let Kaggle answer.
    daily_limit = None
    try:
        info = get_competition_info(api, slug)
        daily_limit = info["max_daily_submissions"] or None
        if not info["user_has_entered"]:
            return {
                "status": "not_joined",
                "reason": (
                    "Join the competition on Kaggle first (accept the rules on the "
                    f"competition page), then submit again: {competition_url(slug)}"
                ),
            }
    except Exception:
        pass

    try:
        response = api.competition_submit(file_name=csv_path, message=message, competition=slug)
        ref = getattr(response, "ref", None) or str(response)
        ctx.log(f"Kaggle accepted the submission: {ref}")
        return {"status": "submitted", "response": str(response), "ref": str(ref)}
    except Exception as exc:
        kind = classify_kaggle_error(exc)
        if kind == "daily_limit":
            limit_txt = f" ({daily_limit}/day)" if daily_limit else ""
            return {
                "status": "limit_reached",
                "reason": (
                    f"Daily submission limit reached{limit_txt}, resets midnight UTC. "
                    "Your CSV is saved and validated. Submit it tomorrow from here, "
                    "or upload it manually on the competition's Submit page."
                ),
                "detail": str(exc),
            }
        if kind == "not_joined":
            return {
                "status": "not_joined",
                "reason": (
                    "Kaggle rejected the submission because the competition rules are "
                    f"not accepted yet. Join here, then submit again: {competition_url(slug)}"
                ),
                "detail": str(exc),
            }
        return {"status": "failed", "reason": f"Kaggle rejected the submission: {exc}"}


def kaggle_live_status(slug: str) -> dict[str, Any]:
    """Live Kaggle state for the Status card. Sync, no job; every API call is
    individually fenced so partial data still renders. Graceful states:
    connected=False (no kaggle.json) and configured=False (no slug)."""
    if not kaggle_credentials_present():
        return {
            "connected": False,
            "reason": "Connect your Kaggle account: create an API token on kaggle.com "
            "(Settings -> API -> Create New Token) and save it to ~/.kaggle/access_token. "
            "Windows PowerShell: "
            'Set-Content -Path "$env:USERPROFILE\\.kaggle\\access_token" '
            '-Value "KGAT_<your token>" -NoNewline -Encoding ascii. '
            "(Or set KAGGLE_API_TOKEN; legacy ~/.kaggle/kaggle.json also works.)",
        }
    slug = (slug or COMPETITION_SLUG).strip()
    if slug == "[SLUG]":
        slug = COMPETITION_SLUG
    out: dict[str, Any] = {"connected": True, "configured": True, "slug": slug}
    api, reason = _authenticated_api()
    if api is None:
        return {"connected": False, "reason": reason}

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
        username = _api_username(api)
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


# ── The jobs ─────────────────────────────────────────────────────────────
#
# Two-step model (2026-07-21): Predict (free, repeatable) and Submit
# (spends a daily Kaggle attempt) are separate jobs. run_predict is step 1:
# inference -> CSV -> strict validation -> sanity -> optional local score,
# plus the predict_state snapshot that backs the tab's revisit view.
# run_kaggle_submit is step 2: it uploads a prior predict job's CSV and
# writes the outcome back onto that predict record so the Status tab's
# one-row-per-prediction history stays true. The legacy single-job
# run_predict_submit remains for the old route.


def _predict_core(params: dict[str, Any], ctx: Any) -> dict[str, Any]:
    """Inference through local scoring; shared by both job shapes."""
    import tlc

    weights = str(params.get("weights_path", "")).strip().strip('"')
    if not weights or not Path(weights).is_file():
        raise ValueError(f"Weights file not found: {weights or '(empty)'}")
    run_name = str(params.get("run_name") or Path(weights).parent.parent.name)
    ctx.set_field("run_name", run_name)
    ctx.set_field("weights", weights)

    table = tlc.Table.from_url(tlc.Url(str(params["test_table_url"]).strip().strip('"')))
    items = _test_items(table)
    ctx.log(f"Test table: {table.url} ({len(items)} images)")
    if len(items) != EXPECTED_TEST_ROWS:
        raise ValueError(
            f"Test table has {len(items)} rows; the competition test split has "
            f"{EXPECTED_TEST_ROWS}. Re-run Import against the starter kit's dataset.yaml."
        )

    conf = float(params.get("conf", 0.25) or 0.25)
    ctx.set_field("conf", conf)
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

    # Pre-submit sanity summary — after validation, before any upload.
    sanity = build_sanity_summary(pred_map)
    ctx.set_field("sanity", sanity)
    ctx.log(
        f"Sanity: {sanity['total_boxes']} boxes over {sanity['images']} images "
        f"(mean {sanity['boxes_per_image_mean']}/image, {sanity['empty_images']} empty)"
    )
    if sanity.get("warning"):
        ctx.log(f"WARNING: {sanity['warning']}")

    local_score = try_local_score(str(csv_path), ctx)
    if local_score is not None:
        ctx.set_field("local_score", local_score)

    n_boxes = sum(0 if p == "no box" else len(p.split()) // 6 for p in pred_map.values())
    return {
        "run_name": run_name,
        "weights": weights,
        "csv_path": str(csv_path),
        "rows": len(df),
        "total_boxes": n_boxes,
        "sanity": sanity,
        "conf": conf,
        "local_score": local_score,
        "checks": checks,
    }


def run_predict(params: dict[str, Any], ctx: Any) -> dict[str, Any]:
    """Step-1 job: predict + validate + score; persists the revisit snapshot."""
    result = _predict_core(params, ctx)

    try:
        from tlc_plugin_kaggle import config_store

        config_store.save(
            {
                "predict_state": {
                    "job_id": getattr(ctx, "job_id", ""),
                    "run_name": result["run_name"],
                    "weights": result["weights"],
                    "csv_path": result["csv_path"],
                    "conf": result["conf"],
                    "local_score": result["local_score"],
                    "sanity": result["sanity"],
                    "checks": result["checks"],
                    "finished_at": time.time(),
                }
            }
        )
    except Exception as exc:
        ctx.log(f"WARNING: could not persist the predict-state snapshot ({exc}); revisit view starts blank.")
    return result


def run_kaggle_submit(params: dict[str, Any], ctx: Any) -> dict[str, Any]:
    """Step-2 job: upload a prior predict job's validated CSV to Kaggle.

    The outcome is written back onto the predict job record
    (facts.submission), so the Status tab's one-row-per-prediction history
    holds. A Kaggle *rejection* fails the job (failure banner + diagnostics);
    the friendly states (limit_reached / not_joined / skipped) complete with
    the state in facts — the CSV stays valid either way.
    """
    from tlc_plugin_kaggle import config_store, jobs

    predict_job_id = str(params.get("predict_job_id", "")).strip()
    pjob = jobs.get_job(predict_job_id) if predict_job_id else None
    if pjob is None:
        raise ValueError("No prediction found for this submission. Run inference first.")
    facts = pjob.get("facts") or {}
    csv_path = str(facts.get("csv_path", ""))
    if not csv_path or not Path(csv_path).is_file():
        raise ValueError(
            f"The prediction's CSV is missing on disk ({csv_path or 'no path recorded'}). "
            "Run inference again."
        )
    run_name = str(facts.get("run_name") or (pjob.get("result") or {}).get("run_name") or "run")
    ctx.set_field("run_name", run_name)
    ctx.set_field("csv_path", csv_path)
    ctx.set_field("predict_job_id", predict_job_id)

    message = str(params.get("message") or f"{run_name} via 3LC plugin")
    slug = str(params.get("competition_slug", "")).strip()
    ctx.log(f"Submitting {Path(csv_path).name} for {run_name!r}: {message!r}")
    submission = submit_to_kaggle(csv_path, message, slug, ctx)
    ctx.set_field("submission", submission)
    jobs.update_job_facts(predict_job_id, "submission", submission)
    if submission["status"] != "submitted":
        ctx.log(f"Submit step: {submission['status']} — {submission.get('reason', '')}")

    try:
        config_store.save(
            {
                "submit_state": {
                    "job_id": getattr(ctx, "job_id", ""),
                    "predict_job_id": predict_job_id,
                    "run_name": run_name,
                    "status": submission.get("status"),
                    "ref": submission.get("ref"),
                    "reason": submission.get("reason"),
                    "message": message,
                    "slug": (slug or COMPETITION_SLUG),
                    "finished_at": time.time(),
                }
            }
        )
    except Exception as exc:
        ctx.log(f"WARNING: could not persist the submit-state snapshot ({exc}).")

    if submission["status"] == "failed":
        raise RuntimeError(submission.get("reason") or "Kaggle rejected the submission.")
    return {
        "run_name": run_name,
        "csv_path": csv_path,
        "predict_job_id": predict_job_id,
        "submission": submission,
    }


def predict_submit_state() -> dict[str, Any]:
    """Revisit state for the Predict + Submit tab: the persisted snapshots,
    with the CSV path re-verified on disk. CSV existence decides — a snapshot
    whose CSV was deleted reports state="empty" (fall back to the form)."""
    from tlc_plugin_kaggle import config_store

    cfg = config_store.load() or {}
    ps = cfg.get("predict_state") or {}
    csv_path = str(ps.get("csv_path", ""))
    if not csv_path or not Path(csv_path).is_file():
        return {"state": "empty"}
    out: dict[str, Any] = {"state": "predicted", "predict": ps}
    ss = cfg.get("submit_state") or {}
    if ss.get("predict_job_id") == ps.get("job_id") and ss.get("status"):
        out["submission"] = ss
        if ss.get("status") == "submitted":
            out["state"] = "submitted"
    return out


def run_predict_submit(params: dict[str, Any], ctx: Any) -> dict[str, Any]:
    """Legacy single-job flow (predict + optional submit), kept for the old
    /predict_submit route and pre-split job records."""
    result = _predict_core(params, ctx)

    message = str(params.get("message") or f"{result['run_name']} via 3LC plugin")
    slug = str(params.get("competition_slug", "")).strip()
    if bool(params.get("csv_only", False)):
        submission = {"status": "skipped", "reason": "CSV-only mode — no upload requested."}
    else:
        submission = submit_to_kaggle(result["csv_path"], message, slug, ctx)
    ctx.set_field("submission", submission)
    if submission["status"] != "submitted":
        ctx.log(f"Submit step: {submission['status']} — {submission.get('reason', '')}")

    result.pop("checks", None)
    return {**result, "submission": submission}
