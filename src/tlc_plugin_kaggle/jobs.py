"""Disk-persisted job store for the Kaggle plugin.

v2 (session 2): every job is mirrored to ``~/.3lc-kaggle-plugin/jobs/<id>.json``
so job records survive plugin hot reloads and service restarts. A hot reload
purges this module, but the job's worker thread keeps running old code — both
generations write to the same JSON file, and cancellation checks READ the file,
so a cancel issued through the reloaded module still reaches a thread started
before the reload.

The installed host (tlc_compute 0.1.1.47) has no generic run endpoint or
JobContext, so plugins own their job lifecycle. The UI polls
GET /api/plugins/kaggle/jobs/{job_id}.
"""

from __future__ import annotations

import json
import os
import threading
import time
import traceback
import uuid
from pathlib import Path
from typing import Any, Callable

JOBS_DIR = Path.home() / ".3lc-kaggle-plugin" / "jobs"

_jobs: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()

# Completed records kept on disk (newest first); older ones are pruned.
_MAX_JOBS_ON_DISK = 50


class JobCtx:
    """What a job target gets to talk back to the store (and the UI)."""

    def __init__(self, job: dict[str, Any]) -> None:
        self._job = job

    def log(self, message: str) -> None:
        with _lock:
            self._job["log"].append(message)
            _flush_locked(self._job)

    def set_checks(self, checks: list[dict[str, Any]]) -> None:
        with _lock:
            self._job["checks"] = [dict(c) for c in checks]
            _flush_locked(self._job)

    def set_progress(self, progress: dict[str, Any]) -> None:
        """E.g. {"epoch": 3, "total_epochs": 100, "metrics": {...}}."""
        with _lock:
            self._job["progress"] = dict(progress)
            _flush_locked(self._job)

    def set_field(self, key: str, value: Any) -> None:
        """Record durable facts as they become known (run_url, weights, ...)."""
        with _lock:
            self._job["facts"][key] = value
            _flush_locked(self._job)

    def is_cancelled(self) -> bool:
        """Read the on-disk record — survives module reloads (see module doc)."""
        try:
            data = json.loads((_job_path(self._job["id"])).read_text(encoding="utf-8"))
            return bool(data.get("cancelled"))
        except Exception:
            with _lock:
                return bool(self._job.get("cancelled"))


def _job_path(job_id: str) -> Path:
    return JOBS_DIR / f"{job_id}.json"


def _flush_locked(job: dict[str, Any]) -> None:
    """Persist a job record atomically. Caller holds _lock."""
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    path = _job_path(job["id"])
    tmp = path.with_suffix(".json.tmp")
    try:
        tmp.write_text(json.dumps(job, indent=1, default=str), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        pass  # persistence is best-effort; memory copy remains authoritative


def _prune_disk() -> None:
    try:
        files = sorted(JOBS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for f in files[_MAX_JOBS_ON_DISK:]:
            f.unlink(missing_ok=True)
    except OSError:
        pass


def start_job(kind: str, params: dict[str, Any], target: Callable[[dict[str, Any], JobCtx], dict[str, Any]]) -> str:
    """Run ``target(params, ctx)`` on a daemon thread; return the job id."""
    job_id = uuid.uuid4().hex[:12]
    job: dict[str, Any] = {
        "id": job_id,
        "kind": kind,
        "status": "running",
        "created_at": time.time(),
        "finished_at": None,
        "cancelled": False,
        "params": dict(params),
        "log": [],
        "checks": [],
        "progress": {},
        "facts": {},
        "result": None,
        "error": None,
    }
    with _lock:
        _jobs[job_id] = job
        _flush_locked(job)
    _prune_disk()

    ctx = JobCtx(job)

    def runner() -> None:
        try:
            result = target(params, ctx)
            # A cancel may have been issued from another process (or another
            # module generation after a hot reload): it lives only in the
            # on-disk record then. Merge it BEFORE the final flush, which
            # would otherwise clobber the disk flag with our stale memory.
            was_cancelled = ctx.is_cancelled()
            with _lock:
                if was_cancelled:
                    job["cancelled"] = True
                job["result"] = result
                job["status"] = "cancelled" if job.get("cancelled") else "completed"
                _flush_locked(job)
        except Exception as exc:
            with _lock:
                job["error"] = f"{type(exc).__name__}: {exc}"
                job["status"] = "failed"
                job["log"].append(f"FAILED: {exc}")
                _flush_locked(job)
            traceback.print_exc()
        finally:
            with _lock:
                job["finished_at"] = time.time()
                _flush_locked(job)

    threading.Thread(target=runner, name=f"kaggle-{kind}-{job_id}", daemon=True).start()
    return job_id


def cancel_job(job_id: str) -> dict[str, Any] | None:
    """Request cooperative cancellation. Returns the updated record or None."""
    with _lock:
        job = _jobs.get(job_id)
        if job is not None:
            job["cancelled"] = True
            job["log"].append("Cancellation requested — stopping at the next checkpoint.")
            _flush_locked(job)
            return dict(job)
    # Not in this module generation's memory (started before a reload): flip
    # the flag on disk; the old thread's is_cancelled() reads it from there.
    path = _job_path(job_id)
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            data["cancelled"] = True
            data.setdefault("log", []).append("Cancellation requested — stopping at the next checkpoint.")
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(data, indent=1, default=str), encoding="utf-8")
            os.replace(tmp, path)
            return data
        except Exception:
            return None
    return None


def get_job(job_id: str) -> dict[str, Any] | None:
    with _lock:
        job = _jobs.get(job_id)
        if job is not None:
            out = dict(job)
            out["log"] = list(job["log"])
            out["checks"] = [dict(c) for c in job["checks"]]
            out["progress"] = dict(job["progress"])
            out["facts"] = dict(job["facts"])
            return out
    # Fall back to disk (pre-reload/pre-restart jobs).
    path = _job_path(job_id)
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def list_jobs(kind: str | None = None) -> list[dict[str, Any]]:
    """All known jobs (memory + disk), newest first, without logs."""
    seen: dict[str, dict[str, Any]] = {}
    try:
        for f in JOBS_DIR.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                seen[data.get("id", f.stem)] = data
            except Exception:
                continue
    except OSError:
        pass
    with _lock:
        for job_id, job in _jobs.items():
            seen[job_id] = job
    out = []
    for job in sorted(seen.values(), key=lambda j: j.get("created_at", 0), reverse=True):
        slim = {k: v for k, v in job.items() if k not in ("log", "checks")}
        if kind is None or slim.get("kind") == kind:
            out.append(slim)
    return out


def active_jobs_generic(project_name: str = "") -> list[dict[str, Any]]:
    """Feed the Hub's generic Queue & Progress panel (host get_active_jobs)."""
    out: list[dict[str, Any]] = []
    for job in list_jobs():
        if job.get("status") not in ("running", "queued"):
            continue
        progress = job.get("progress") or {}
        entry: dict[str, Any] = {
            "id": job["id"],
            "plugin_id": "kaggle",
            "plugin_name": "Kaggle Competition",
            "plugin_icon": "🏁",
            "status": job["status"],
            "title": f"Kaggle {job.get('kind', 'job')}",
            "subtitle": str((job.get("params") or {}).get("project_name", "")),
            "run_url": (job.get("facts") or {}).get("run_url"),
        }
        if progress.get("total_epochs"):
            entry["progress"] = {
                "percent": 100.0 * float(progress.get("epoch", 0)) / float(progress["total_epochs"]),
                "label": f"Epoch {progress.get('epoch', 0)}/{progress['total_epochs']}",
            }
        out.append(entry)
    return out
