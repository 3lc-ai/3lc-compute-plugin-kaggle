# Copyright 2026 3LC Inc.
# SPDX-License-Identifier: AGPL-3.0-only
"""Train card backend: constrained YOLOv11n pretrained training via 3lc-ultralytics.

Competition constraints are enforced SERVER-SIDE, not in the form:

* ``model=yolo11n.pt`` — the OFFICIAL Ultralytics COCO-pretrained checkpoint,
  downloaded and cached by the plugin and pinned by sha256, so every
  participant trains from byte-identical starting weights.
* ``imgsz=640``, ``pretrained=True`` (the pinned official init — uniform
  init cuts both ways, so ``pretrained=False`` is rejected like any other
  override attempt).
* The locked kwargs are merged LAST into the train() call, so nothing a
  participant submits can override them; additionally ``parse_extra_args``
  rejects any attempt to name a locked key (model / imgsz / pretrained /
  weights / resume) with a participant-facing error, so the attempt fails
  loudly instead of silently losing.

Provenance: the 3lc-ultralytics trainer logs every YOLO arg plus all 3LC
settings onto the tlc.Run via run.set_parameters (engine/trainer.py
_log_3lc_parameters); run_training additionally records the checkpoint's
sha256. The Run's recorded config proves the locked contract:
parameters["model"] endswith "yolo11n.pt", ["imgsz"] == 640,
["pretrained"] == True, ["checkpoint_sha256"] == the official hash.

Uses the documented tlc_ultralytics API only (YOLO, Settings,
model.train(tables=..., settings=...), standard ultralytics callbacks).
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

LOCKED_TRAIN_ARGS: dict[str, Any] = {
    # Resolved to the plugin-managed official checkpoint at train time
    # (ensure_official_checkpoint); the symbolic name here is what the
    # extra-args guard and the locked-copy render.
    "model": "yolo11n.pt",
    "imgsz": 640,
    "pretrained": True,
}

# The pinned init. Everyone trains from byte-identical weights; the sha256
# recorded on the Run is the proof. Official Ultralytics release asset
# (5,613,764 bytes), hash verified on every train.
OFFICIAL_CHECKPOINT_URL = "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt"
OFFICIAL_CHECKPOINT_SHA256 = "0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1"
CHECKPOINT_CACHE = Path.home() / ".3lc-kaggle-plugin" / "checkpoints" / "yolo11n.pt"

# Keys that would defeat the competition locks if injected via extra args.
FORBIDDEN_LOCKED = {"model", "imgsz", "pretrained", "weights", "resume"}
# Keys the plugin manages itself; overriding them breaks the run plumbing.
FORBIDDEN_MANAGED = {"data", "tables", "settings", "project", "name", "exist_ok", "task"}

LOCK_MESSAGE = (
    "This competition trains YOLOv11n from the official COCO-pretrained "
    "checkpoint at 640 px — '{key}' is locked and cannot be overridden "
    "(identical starting weights for every participant)."
)


def _sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_official_checkpoint(ctx: Any = None) -> tuple[Path, str]:
    """(path, sha256) of the plugin-managed official yolo11n.pt.

    Cached under CHECKPOINT_CACHE and hash-verified on every call; a stale
    or tampered cache is re-downloaded, and a download that fails the pin
    raises rather than trains. The fetch surfaces a pre-flight progress
    stage so a first-ever train shows "Fetching official checkpoint" instead
    of a silent stall.
    """

    def log(msg: str) -> None:
        if ctx is not None:
            ctx.log(msg)

    if CHECKPOINT_CACHE.is_file():
        digest = _sha256_file(CHECKPOINT_CACHE)
        if digest == OFFICIAL_CHECKPOINT_SHA256:
            return CHECKPOINT_CACHE, digest
        log(f"Cached checkpoint failed hash verification ({digest[:12]}...); re-downloading the official file.")
        CHECKPOINT_CACHE.unlink()

    if ctx is not None:
        ctx.set_progress({"stage": "checkpoint",
                          "stage_note": "Fetching the official yolo11n.pt checkpoint (5.4 MB, one-time)"})
    log(f"Fetching official checkpoint: {OFFICIAL_CHECKPOINT_URL} -> {CHECKPOINT_CACHE}")
    CHECKPOINT_CACHE.parent.mkdir(parents=True, exist_ok=True)
    import os
    import urllib.request

    tmp = CHECKPOINT_CACHE.with_suffix(".tmp")
    try:
        urllib.request.urlretrieve(OFFICIAL_CHECKPOINT_URL, tmp)
        digest = _sha256_file(tmp)
        if digest != OFFICIAL_CHECKPOINT_SHA256:
            raise RuntimeError(
                "The downloaded checkpoint failed sha256 verification "
                f"(got {digest[:12]}..., expected {OFFICIAL_CHECKPOINT_SHA256[:12]}...). "
                "Check your network (proxy or captive portal?) and try again."
            )
        os.replace(tmp, CHECKPOINT_CACHE)
    finally:
        tmp.unlink(missing_ok=True)
    log(f"Official checkpoint cached: {CHECKPOINT_CACHE} (sha256 {digest[:12]}...)")
    return CHECKPOINT_CACHE, digest

# Run artifacts (weights, plots, submissions). The organizer machine keeps
# its historical location; everywhere else the default must be creatable
# without elevation — a hardcoded C:\Users\Owner path PermissionErrors the
# first train job on any other Windows machine.
_ORGANIZER_SAVE_ROOT = Path(r"C:\Users\Owner\Desktop\3LC Kaggle Competitions\runs\kaggle-plugin")
DEFAULT_SAVE_ROOT = str(
    _ORGANIZER_SAVE_ROOT
    if _ORGANIZER_SAVE_ROOT.parent.is_dir()
    else Path.home() / ".3lc-kaggle-plugin" / "runs"
)

# Exposed training args: name -> (converter, default, min, max). Bounds are
# enforced server-side below (participant-facing error naming the bound) and
# mirrored as client-side attributes in ui.html; None bounds = free field.
# Bounds apply to the FINAL kwargs, so extra args cannot sidestep them.
_EXPOSED = {
    "epochs": (int, 20, 1, 300),
    "batch": (int, 16, 1, 128),
    "lr0": (float, 0.01, 0.0001, 0.1),
    "lrf": (float, 0.01, 0.01, 1.0),
    "optimizer": (str, "auto", None, None),
    "patience": (int, 100, 0, 100),
    "device": (str, "0", None, None),
    "workers": (int, 0, 0, 16),  # Windows: keep dataloader workers at 0
}

_OPTIMIZERS = ("auto", "SGD", "Adam", "AdamW", "NAdam", "RAdam", "RMSProp")

BOUND_MESSAGE = "{key} must be between {lo} and {hi} (got {val})."


def _check_bound(key: str, val: Any) -> None:
    """Range-check a final kwarg against _EXPOSED bounds (post-merge)."""
    spec = _EXPOSED.get(key)
    if spec is None or spec[2] is None:
        return
    _, _, lo, hi = spec
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        raise ValueError(f"Invalid value for {key}: {val!r} (expected a number).")
    if not (lo <= val <= hi):
        raise ValueError(BOUND_MESSAGE.format(key=key, lo=lo, hi=hi, val=val))


def _coerce_scalar(raw: str) -> Any:
    s = raw.strip()
    low = s.lower()
    if low in ("true", "false"):
        return low == "true"
    if low in ("none", "null"):
        return None
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s.strip("\"'")


def parse_extra_args(text: str) -> dict[str, Any]:
    """Parse 'key=value key2=value2' free text; enforce the competition locks.

    Raises ValueError with a participant-facing message on any locked or
    plugin-managed key.
    """
    out: dict[str, Any] = {}
    if not text or not text.strip():
        return out
    tokens = [t for chunk in text.replace(",", " ").split() for t in [chunk.strip()] if t]
    for token in tokens:
        if "=" not in token:
            raise ValueError(f"Extra args must be key=value pairs — could not parse '{token}'.")
        key, _, value = token.partition("=")
        key = key.strip()
        if key in FORBIDDEN_LOCKED:
            raise ValueError(LOCK_MESSAGE.format(key=key))
        if key in FORBIDDEN_MANAGED:
            raise ValueError(f"'{key}' is managed by the plugin and cannot be set via extra args.")
        if not key.isidentifier():
            raise ValueError(f"Invalid extra-arg name: '{key}'.")
        out[key] = _coerce_scalar(value)
    return out


def build_train_kwargs(params: dict[str, Any]) -> dict[str, Any]:
    """Exposed fields + validated extra args + locked args (locked last)."""
    kwargs: dict[str, Any] = {}
    for key, (conv, default, _lo, _hi) in _EXPOSED.items():
        raw = params.get(key, default)
        if raw is None or raw == "":
            raw = default
        try:
            # int fields tolerate "16.0"-style input as long as it's integral
            kwargs[key] = int(float(raw)) if conv is int and float(raw) == int(float(raw)) else conv(raw)
        except (TypeError, ValueError):
            raise ValueError(f"Invalid value for {key}: {raw!r}")
    optimizer = str(kwargs["optimizer"]).strip()
    matched = next((o for o in _OPTIMIZERS if o.lower() == optimizer.lower()), None)
    if matched is None:
        raise ValueError(f"optimizer must be one of {', '.join(_OPTIMIZERS)} (got {optimizer!r}).")
    kwargs["optimizer"] = matched
    if str(kwargs["device"]).strip().isdigit():
        kwargs["device"] = int(str(kwargs["device"]).strip())

    kwargs.update(parse_extra_args(str(params.get("extra_args", ""))))

    # Bounds run on the MERGED kwargs so 'epochs=999' via extra args is
    # rejected with the same participant-facing message as the form field.
    for key, val in kwargs.items():
        _check_bound(key, val)

    # The competition locks — merged last, they always win.
    kwargs.update(LOCKED_TRAIN_ARGS)
    return kwargs


# Judgment bounds for the exposed 3LC settings (same message style as the
# training args). dims/reducer are membership checks, not ranges.
_SETTINGS_BOUNDS = {
    "conf_thres": (0.0, 1.0),
    "max_det": (1, 1000),
    "collection_epoch_start": (0, 300),
    "collection_epoch_interval": (1, 300),
}
_EMB_DIMS = (0, 2, 3)
_EMB_REDUCERS = ("pacmap", "umap")


def build_settings(params: dict[str, Any]) -> Any:
    """The 3LC settings block — the point of the competition."""
    from tlc_ultralytics import Settings

    def _f(key: str, default: Any, conv: Any) -> Any:
        raw = params.get(key, default)
        try:
            val = conv(raw) if raw not in (None, "") else default
        except (TypeError, ValueError):
            raise ValueError(f"Invalid value for {key}: {raw!r}")
        bounds = _SETTINGS_BOUNDS.get(key)
        if bounds is not None and val is not None and not (bounds[0] <= val <= bounds[1]):
            raise ValueError(BOUND_MESSAGE.format(key=key, lo=bounds[0], hi=bounds[1], val=val))
        return val

    for dim_key in ("image_embeddings_dim", "instance_embeddings_dim"):
        if _f(dim_key, 0, int) not in _EMB_DIMS:
            raise ValueError(f"{dim_key} must be one of {_EMB_DIMS}.")
    if str(params.get("image_embeddings_reducer") or "pacmap") not in _EMB_REDUCERS:
        raise ValueError(f"image_embeddings_reducer must be one of {_EMB_REDUCERS}.")

    return Settings(
        project_name=str(params.get("project_name") or "exdark-competition").strip(),
        run_name=str(params.get("run_name") or f"kaggle_run_{time.strftime('%Y%m%d_%H%M%S')}").strip(),
        conf_thres=_f("conf_thres", 0.1, float),
        max_det=_f("max_det", 300, int),
        collect_loss=bool(params.get("collect_loss", False)),
        image_embeddings_dim=_f("image_embeddings_dim", 0, int),
        image_embeddings_reducer=str(params.get("image_embeddings_reducer") or "pacmap"),
        instance_embeddings_dim=_f("instance_embeddings_dim", 0, int),
        ground_truth_instance_embeddings=bool(params.get("ground_truth_instance_embeddings", False)),
        sampling_weights=bool(params.get("sampling_weights", False)),
        exclude_zero_weight_training=bool(params.get("exclude_zero_weight_training", False)),
        exclude_zero_weight_collection=bool(params.get("exclude_zero_weight_collection", False)),
        collection_val_only=bool(params.get("collection_val_only", False)),
        collection_disable=bool(params.get("collection_disable", False)),
        collection_epoch_start=_f("collection_epoch_start", None, int),
        collection_epoch_interval=_f("collection_epoch_interval", 1, int),
    )


# Canonical per-epoch metrics kept as compact history for the UI's stat
# chips + sparklines. Short keys on purpose: the history is re-flushed to
# the job JSON every epoch. mAP50-95 must match before mAP50 (substring).
def _canonical_metrics(metrics: dict[str, Any]) -> dict[str, float]:
    out: dict[str, float] = {}
    for key, val in metrics.items():
        if not isinstance(val, (int, float)):
            continue
        if "mAP50-95" in key:
            out["m95"] = float(val)
        elif "mAP50" in key:
            out["m50"] = float(val)
        elif "precision" in key:
            out["p"] = float(val)
        elif "recall" in key:
            out["r"] = float(val)
    return out


def _resolve_table(url: str, use_latest: bool, ctx: Any, role: str) -> Any:
    import tlc

    table = tlc.Table.from_url(tlc.Url(str(url).strip().strip('"')))
    if use_latest:
        latest = table.latest()
        if str(latest.url) != str(table.url):
            ctx.log(f"{role}: following latest revision {latest.url}")
        table = latest
    ctx.log(f"{role}: {table.url} ({table.row_count} rows)")
    return table


def get_run_parameters(run: Any) -> dict[str, Any]:
    """Best-effort readback of a tlc.Run's recorded parameters."""
    constants = getattr(run, "constants", None)
    if isinstance(constants, dict):
        params = constants.get("parameters")
        if isinstance(params, dict):
            return params
    params = getattr(run, "parameters", None)
    if isinstance(params, dict):
        return params
    return {}


def check_provenance(run_url: str) -> list[dict[str, Any]]:
    """The acceptance criterion: the Run's own record proves the locked
    contract — the pinned official init (by hash), architecture, resolution."""
    import tlc

    run = tlc.Run.from_url(tlc.Url(run_url))
    p = get_run_parameters(run)
    model = str(p.get("model", "")).replace("\\", "/")
    sha = str(p.get("checkpoint_sha256", "") or "")
    return [
        {
            "label": "run records model == yolo11n.pt (official checkpoint)",
            "ok": model.endswith("yolo11n.pt"),
            "detail": f"model={p.get('model')!r}",
        },
        {
            "label": "run records imgsz == 640",
            "ok": p.get("imgsz") == 640,
            "detail": f"imgsz={p.get('imgsz')!r}",
        },
        {
            "label": "run records pretrained == True (official init)",
            "ok": p.get("pretrained") in (True, "True", 1),
            "detail": f"pretrained={p.get('pretrained')!r}",
        },
        {
            "label": "run records the official checkpoint sha256",
            "ok": sha == OFFICIAL_CHECKPOINT_SHA256,
            "detail": f"checkpoint_sha256={(sha[:12] + '...') if sha else '(missing)'}",
        },
    ]


def run_training(params: dict[str, Any], ctx: Any) -> dict[str, Any]:
    """The Train job. Long-running; reports via ctx; cancels cooperatively."""
    from tlc_ultralytics import YOLO

    train_kwargs = build_train_kwargs(params)  # raises on locked-key attempts
    settings = build_settings(params)
    # The run name is generated here when the field was blank — surface it
    # immediately so the UI's in-run header can show it from epoch 0.
    ctx.set_field("run_name", settings.run_name)

    use_latest = bool(params.get("use_latest", True))
    train_table = _resolve_table(params["train_table_url"], use_latest, ctx, "train")
    val_table = _resolve_table(params["val_table_url"], use_latest, ctx, "val")

    save_root = str(params.get("save_root") or DEFAULT_SAVE_ROOT)
    Path(save_root).mkdir(parents=True, exist_ok=True)

    # Pin the init before anything else: cached-or-downloaded official
    # checkpoint, hash-verified. The resolved path becomes the model arg so
    # the Run's own record carries it.
    ckpt_path, ckpt_sha = ensure_official_checkpoint(ctx)
    train_kwargs["model"] = str(ckpt_path)
    ctx.set_field("checkpoint_sha256", ckpt_sha)

    ctx.log(
        f"Locked: model=yolo11n.pt (official COCO-pretrained, sha256 {ckpt_sha[:12]}...) "
        "· imgsz=640 · pretrained=True. "
        f"Training {train_kwargs['epochs']} epochs, batch {train_kwargs['batch']}, "
        f"device {train_kwargs['device']}."
    )

    model = YOLO(str(ckpt_path), task="detect")

    state: dict[str, Any] = {
        "epoch": 0,
        "cancelled": False,
        "train_start": time.time(),
        "history": [],
        # Within-epoch batch progress. batch_i is our own count of
        # on_train_batch_end callbacks (the loop index is a local in
        # ultralytics' _do_train, not a trainer attribute); batch_n comes
        # from len(trainer.train_loader). No internals patched.
        "batch_i": 0,
        "batch_n": 0,
        "last_batch_flush": 0.0,
        # Last epoch-level progress payload; batch flushes extend it so a
        # poll never sees history/ETA vanish mid-epoch.
        "progress": {"epoch": 0, "total_epochs": int(train_kwargs["epochs"]), "metrics": {}, "history": []},
    }

    def _check_cancel(trainer: Any) -> None:
        if ctx.is_cancelled():
            state["cancelled"] = True
            trainer.stop = True

    def on_train_epoch_start(trainer: Any) -> None:
        state["batch_i"] = 0
        try:
            state["batch_n"] = len(trainer.train_loader)
        except Exception:
            state["batch_n"] = 0

    def on_train_batch_end(trainer: Any) -> None:
        _check_cancel(trainer)
        state["batch_i"] += 1
        # Throttle: the job record flushes to disk on every set_progress,
        # so batch updates land at most ~1/s.
        now = time.time()
        if now - state["last_batch_flush"] < 1.0:
            return
        state["last_batch_flush"] = now
        ctx.set_progress({**state["progress"], "batch_i": state["batch_i"], "batch_n": state["batch_n"]})

    def on_fit_epoch_end(trainer: Any) -> None:
        _check_cancel(trainer)
        epoch = int(getattr(trainer, "epoch", 0)) + 1
        total = int(getattr(trainer, "epochs", 0))
        metrics = {
            k: round(float(v), 5)
            for k, v in (getattr(trainer, "metrics", {}) or {}).items()
            if isinstance(v, (int, float))
        }
        state["epoch"] = epoch
        # Compact per-epoch history for the UI's stat chips + sparklines.
        state["history"].append({"e": epoch, **_canonical_metrics(metrics)})
        # ETA from measured epoch time, available once epoch 1 completes.
        elapsed = time.time() - state["train_start"]
        avg_epoch = elapsed / max(epoch, 1)
        progress = {
            "epoch": epoch,
            "total_epochs": total,
            "metrics": metrics,
            "history": list(state["history"]),
            "avg_epoch_s": round(avg_epoch, 1),
            "eta_s": round(avg_epoch * max(total - epoch, 0)),
        }
        state["progress"] = progress
        # Epoch boundary: batch_i resets to 0, so the client's overall
        # fraction (epoch + batch_i/batch_n) / total stays continuous.
        ctx.set_progress({**progress, "batch_i": 0, "batch_n": state["batch_n"]})
        ctx.log(f"epoch {epoch}/{total} — " + ", ".join(f"{k}={v}" for k, v in list(metrics.items())[:4]))

    model.add_callback("on_train_epoch_start", on_train_epoch_start)
    model.add_callback("on_train_batch_end", on_train_batch_end)
    model.add_callback("on_fit_epoch_end", on_fit_epoch_end)

    model.train(
        tables={"train": train_table, "val": val_table},
        settings=settings,
        project=save_root,
        name=settings.run_name,
        **train_kwargs,
    )

    trainer = model.trainer
    run = getattr(trainer, "_run", None)
    run_url = str(run.url) if run is not None else ""
    best = str(getattr(trainer, "best", "") or "")
    ctx.set_field("run_url", run_url)
    ctx.set_field("weights", best)  # session 3 (Predict + Submit) consumes this

    # The hash is the proof of the pinned init — record it on the Run itself
    # (merged with the trainer's own parameter log) so check_provenance reads
    # it back from the Run record, not from plugin state.
    if run is not None:
        try:
            run.set_parameters({**get_run_parameters(run), "checkpoint_sha256": ckpt_sha})
        except Exception as exc:
            ctx.log(f"WARNING: could not record checkpoint_sha256 on the Run ({exc}).")

    if state["cancelled"]:
        ctx.log("Training stopped by cancellation request.")
        if run is not None:
            try:
                run.set_status_cancelled()
            except Exception:
                pass

    checks = check_provenance(run_url) if run_url else []
    ctx.set_checks(checks)
    for c in checks:
        ctx.log(("PASS " if c["ok"] else "FAIL ") + c["label"] + f" — {c['detail']}")

    best_exists = bool(best) and Path(best).is_file()
    ctx.log(f"best.pt: {best} (exists: {best_exists})")

    return {
        "run_url": run_url,
        "run_name": settings.run_name,
        "weights": best,
        "weights_exists": best_exists,
        "cancelled": state["cancelled"],
        "epochs_completed": state["epoch"],
        "provenance": checks,
        "locked": dict(LOCKED_TRAIN_ARGS),
        "checkpoint_sha256": ckpt_sha,
    }
