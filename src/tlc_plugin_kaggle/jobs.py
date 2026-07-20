"""In-plugin job store for the installed host (tlc_compute 0.1.1.47).

The installed host has no generic run endpoint and no JobContext — plugins own
their job lifecycle (the built-ins each ship a runner). This is the minimal
version: one daemon thread per job, state in a module-level dict, polled by the
UI via GET /api/plugins/kaggle/jobs/{job_id}.

Reload caveat: a hot reload purges this module, so running jobs and their
records are lost. Import jobs take seconds, so this is acceptable for card 1;
the session-2 trainer will persist job state to disk instead.
"""

from __future__ import annotations

import threading
import time
import traceback
import uuid
from typing import Any, Callable

_jobs: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()

# Keep only the most recent records so a long-lived service doesn't grow.
_MAX_JOBS = 20


def _prune_locked() -> None:
    if len(_jobs) <= _MAX_JOBS:
        return
    by_age = sorted(_jobs.values(), key=lambda j: j["created_at"])
    for job in by_age[: len(_jobs) - _MAX_JOBS]:
        if job["status"] not in ("running", "queued"):
            _jobs.pop(job["id"], None)


def start_job(kind: str, params: dict[str, Any], target: Callable[[dict[str, Any], Callable[[str], None]], dict[str, Any]]) -> str:
    """Run ``target(params, log)`` on a daemon thread; return the job id.

    ``target`` returns the job's result dict on success and raises on failure.
    Anything it passes to ``log`` becomes a UI log line. It may also set
    ``job['checks']`` via the log callback owner (see importer.run_import).
    """
    job_id = uuid.uuid4().hex[:12]
    job: dict[str, Any] = {
        "id": job_id,
        "kind": kind,
        "status": "running",
        "created_at": time.time(),
        "finished_at": None,
        "params": {k: v for k, v in params.items() if k != "_internal"},
        "log": [],
        "checks": [],
        "result": None,
        "error": None,
    }
    with _lock:
        _jobs[job_id] = job
        _prune_locked()

    def log(message: str) -> None:
        with _lock:
            job["log"].append(message)

    def set_checks(checks: list[dict[str, Any]]) -> None:
        with _lock:
            job["checks"] = checks

    def runner() -> None:
        try:
            params["_set_checks"] = set_checks
            result = target(params, log)
            with _lock:
                job["result"] = result
                job["status"] = "completed"
        except Exception as exc:
            with _lock:
                job["error"] = f"{type(exc).__name__}: {exc}"
                job["status"] = "failed"
                job["log"].append(f"FAILED: {exc}")
            traceback.print_exc()
        finally:
            with _lock:
                job["finished_at"] = time.time()

    threading.Thread(target=runner, name=f"kaggle-{kind}-{job_id}", daemon=True).start()
    return job_id


def get_job(job_id: str) -> dict[str, Any] | None:
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return None
        # Shallow copy is enough: values are replaced, not mutated in place,
        # except the log/checks lists which we copy explicitly.
        out = dict(job)
        out["log"] = list(job["log"])
        out["checks"] = [dict(c) for c in job["checks"]]
        return out


def active_jobs_generic(project_name: str = "") -> list[dict[str, Any]]:
    """Feed the Hub's generic Queue & Progress panel (host get_active_jobs)."""
    out: list[dict[str, Any]] = []
    with _lock:
        for job in _jobs.values():
            if job["status"] not in ("running", "queued"):
                continue
            out.append(
                {
                    "id": job["id"],
                    "plugin_id": "kaggle",
                    "plugin_name": "Kaggle Competition",
                    "plugin_icon": "🏁",
                    "status": job["status"],
                    "title": f"Kaggle {job['kind']}",
                    "subtitle": str(job["params"].get("project_name", "")),
                    "run_url": None,
                }
            )
    return out
