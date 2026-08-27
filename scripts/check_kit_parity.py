"""Verify a starter-kit instance against a manifest.json, reporting the delta.

The manifest (from make_kit_manifest.py) is the single source of truth; the
target may be any kit instance:

  --dir  an extracted tree - either the parent that contains the kit dir
         ("starter_kit/") or the kit dir itself (auto-detected)
  --zip  a kit bundle zip (e.g. the Kaggle Data-tab download), verified by
         streaming entries without extracting

Parity = every manifest file present with matching size and sha256, and
nothing extra. The report always names the differing paths - it never
hardcodes expected counts, so a 4-file drift shows up as 4 named lines, not a
bare failure. Exit 0 on parity, 1 on any delta, 2 on usage errors.

This is the repeatable check behind the re-zip lesson: outer archive hashes
are meaningless across systems (Kaggle re-zips uploads), so local copy, CDN
copy, and Kaggle copy are each verified per-file against the same manifest.

Usage:
    python scripts/check_kit_parity.py --manifest <path> (--dir <path> | --zip <path>)
        [--full]

Stdlib-only, like everything else in this repo.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path, PurePosixPath

_PRINT_CAP = 50  # per-category display cap without --full


def _sha256_stream(fobj) -> tuple[str, int]:
    h = hashlib.sha256()
    n = 0
    for chunk in iter(lambda: fobj.read(1 << 20), b""):
        h.update(chunk)
        n += len(chunk)
    return h.hexdigest(), n


def _normalize(name: str) -> str:
    return name.replace("\\", "/").lstrip("./")


def _dir_base(target: Path, kit_dir_name: str) -> Path:
    """Resolve the directory manifest paths ("<kit_dir_name>/...") hang off."""
    if (target / kit_dir_name).is_dir():
        return target
    if target.name == kit_dir_name and target.is_dir():
        return target.parent
    raise SystemExit(
        f"--dir {target} contains no '{kit_dir_name}/' and is not itself "
        f"named '{kit_dir_name}'"
    )


def _walk_dir(base: Path, kit_dir_name: str) -> dict[str, Path]:
    root = base / kit_dir_name
    return {
        PurePosixPath(p.relative_to(base).as_posix()).as_posix(): p
        for p in root.rglob("*")
        if p.is_file()
    }


def check(manifest_path: Path, target_dir: Path | None = None,
          target_zip: Path | None = None) -> dict:
    """Compare one target against the manifest; returns the delta report.

    Report keys: matched (int), size_mismatch / sha_mismatch / missing /
    extra (lists), plus the manifest header fields for display.
    """
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    expected = {f["path"]: f for f in manifest["files"]}

    report = {
        "manifest": {k: manifest[k] for k in
                     ("competition_id", "kit_version", "file_count", "total_bytes")},
        "matched": 0,
        "size_mismatch": [],
        "sha_mismatch": [],
        "missing": [],
        "extra": [],
    }

    actual: dict[str, tuple[int, str]] = {}  # path -> (bytes, sha256)
    if target_zip is not None:
        with zipfile.ZipFile(target_zip) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                name = _normalize(info.filename)
                with zf.open(info) as f:
                    digest, nbytes = _sha256_stream(f)
                actual[name] = (nbytes, digest)
    else:
        base = _dir_base(Path(target_dir), manifest["kit_dir_name"])
        for name, path in _walk_dir(base, manifest["kit_dir_name"]).items():
            with path.open("rb") as f:
                digest, nbytes = _sha256_stream(f)
            actual[name] = (nbytes, digest)

    for path, entry in expected.items():
        got = actual.get(path)
        if got is None:
            report["missing"].append(path)
        elif got[0] != entry["bytes"]:
            report["size_mismatch"].append(
                f"{path} (expected {entry['bytes']} bytes, got {got[0]})")
        elif got[1] != entry["sha256"]:
            report["sha_mismatch"].append(f"{path}")
        else:
            report["matched"] += 1
    for path in actual:
        if path not in expected:
            report["extra"].append(f"{path} ({actual[path][0]} bytes)")

    for key in ("size_mismatch", "sha_mismatch", "missing", "extra"):
        report[key].sort()
    return report


def is_parity(report: dict) -> bool:
    return not any(
        report[k] for k in ("size_mismatch", "sha_mismatch", "missing", "extra"))


def print_report(report: dict, full: bool = False) -> None:
    m = report["manifest"]
    print(f"Parity report - manifest {m['kit_version']} ({m['competition_id']}), "
          f"{m['file_count']} files, {m['total_bytes']:,} bytes")
    print(f"  matched:        {report['matched']}")
    labels = (
        ("size_mismatch", "size mismatch: "),
        ("sha_mismatch", "sha256 mismatch:"),
        ("missing", "missing (in manifest, not in target):"),
        ("extra", "extra (in target, not in manifest): "),
    )
    for key, label in labels:
        entries = report[key]
        print(f"  {label} {len(entries)}")
        shown = entries if full else entries[:_PRINT_CAP]
        for line in shown:
            print(f"    {line}")
        if len(entries) > len(shown):
            print(f"    ... and {len(entries) - len(shown)} more (use --full)")
    print("RESULT: PARITY" if is_parity(report) else "RESULT: DELTA")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manifest", required=True, type=Path)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--dir", type=Path, help="extracted kit tree")
    target.add_argument("--zip", type=Path, help="kit bundle zip")
    parser.add_argument("--full", action="store_true",
                        help="print every differing path (no display cap)")
    args = parser.parse_args(argv)

    report = check(args.manifest, target_dir=args.dir, target_zip=args.zip)
    print_report(report, full=args.full)
    return 0 if is_parity(report) else 1


if __name__ == "__main__":
    sys.exit(main())
