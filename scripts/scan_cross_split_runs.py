"""Read-only scan of the plugin job store for cross-split table URLs (DP-11).

Flags past train/predict jobs whose recorded params carry a table URL whose
dataset segment does not match its slot (train slot -> exdark_train, val ->
exdark_val, test -> exdark_test), or identical train/val URLs. Prints; never
modifies anything.

Usage:
    python scan_cross_split_runs.py [jobs_dir]

Default jobs_dir: ~/.3lc-kaggle-plugin/jobs (note: on a redirected-home
setup, run it with that home's USERPROFILE, or pass the dir explicitly).

Standalone by design (stdlib only, dataset names inlined) so testers can run
it without the plugin importable.
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

EXPECTED = {
    "train_table_url": "exdark_train",
    "val_table_url": "exdark_val",
    "test_table_url": "exdark_test",
}
KINDS = ("train", "predict", "predict_submit")


def url_dataset(url: str) -> str | None:
    m = re.search(r"[\\/]datasets[\\/]([^\\/]+)[\\/]tables[\\/]", str(url))
    return m.group(1) if m else None


def main() -> int:
    jobs_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / ".3lc-kaggle-plugin" / "jobs"
    print(f"DP-11 cross-split scan over {jobs_dir}")
    print(
        "LIMIT: the job store prunes to the 50 most recent records, and run\n"
        "provenance does not record split identity - a CLEAN RESULT HERE IS\n"
        "NOT PROOF OF ABSENCE for older or pruned runs.\n"
    )
    if not jobs_dir.is_dir():
        print("No jobs directory found - nothing to scan.")
        return 0

    findings = 0
    scanned = 0
    for path in sorted(jobs_dir.glob("*.json")):
        try:
            job = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"  [unreadable] {path.name}: {exc}")
            continue
        if job.get("kind") not in KINDS:
            continue
        scanned += 1
        params = job.get("params") or {}
        problems = []
        for slot, expected in EXPECTED.items():
            url = str(params.get(slot) or "")
            if url and url_dataset(url) != expected:
                problems.append(f"{slot} -> {url_dataset(url) or 'unparseable'} (expected {expected}): {url}")
        turl = str(params.get("train_table_url") or "").rstrip("\\/")
        vurl = str(params.get("val_table_url") or "").rstrip("\\/")
        if turl and turl == vurl:
            problems.append(f"train and val identical: {turl}")
        if problems:
            findings += 1
            when = job.get("created_at")
            stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(when)) if when else "?"
            print(f"FLAGGED  id={job.get('id', path.stem)}  kind={job.get('kind')}  created={stamp}")
            for p in problems:
                print(f"         {p}")
    print(f"\nScanned {scanned} train/predict records; {findings} flagged.")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
