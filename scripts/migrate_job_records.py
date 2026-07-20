"""One-off migration for job records persisted before the session-2 cancel fix.

Those records can carry status="completed" with a clobbered cancelled flag
while their own result says cancelled — rewrite them in place. Also prunes
throwaway kind="test" records from verification harnesses.

Safe to re-run (idempotent). Usage:
    python scripts/migrate_job_records.py
"""

import json
from pathlib import Path

JOBS_DIR = Path.home() / ".3lc-kaggle-plugin" / "jobs"


def main() -> None:
    if not JOBS_DIR.is_dir():
        print("no job store — nothing to migrate")
        return
    fixed = pruned = 0
    for path in sorted(JOBS_DIR.glob("*.json")):
        try:
            job = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if job.get("kind") == "test":
            path.unlink()
            pruned += 1
            print(f"pruned test record {job.get('id')}")
            continue
        if job.get("status") == "completed" and (job.get("result") or {}).get("cancelled"):
            job["status"] = "cancelled"
            job["cancelled"] = True
            path.write_text(json.dumps(job, indent=1, default=str), encoding="utf-8")
            fixed += 1
            print(f"fixed {job.get('id')} ({job.get('kind')}) -> cancelled")
    print(f"done: {fixed} fixed, {pruned} pruned")


if __name__ == "__main__":
    main()
