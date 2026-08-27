"""Generate the CDN starter-kit distribution: sharded zips + manifest.json.

Produces the immutable content of one versioned prefix
(competitions.3lc.ai/kaggle/<competition-id>/starter-kit/<kit-version>/):

    <out>/<kit-version>/
        manifest.json
        part-NN-<group>[-NN].zip

Publishing rule (also in RELEASING.md): a version prefix is IMMUTABLE once
staged. Updating the kit means regenerating with a NEW --kit-version (v2, ...)
and staging that, never overwriting objects under an existing version - the
24h CDN edge cache would otherwise serve a mixed manifest/data set that fails
checksum verification in ways that look like corruption.

Sharding is deterministic: files are grouped by top-level split (images/train,
images/val, images/test, everything else -> root-labels), sorted by path, and
large groups are cut into shards at --shard-mb. Zip entries carry fixed
timestamps and attributes, so the same input tree always produces
byte-identical shards (stable sha256s across regenerations). That determinism
is the point, not tidiness: it makes the manifest independently reproducible -
anyone with the kit tree can rebuild the shards and arrive at the same hashes,
verifying the published manifest instead of trusting it. JPEGs are stored
uncompressed (they do not deflate); everything else is deflated.

The manifest lists both layers the downloader and the parity check need:
  archives[] - the downloadable objects (name, bytes, sha256, file_count)
  files[]    - every file inside the kit (path, bytes, sha256, archive),
               paths prefixed with the kit dir name ("starter_kit/...") to
               match the original kit zip and the Kaggle bundle layout.

Usage:
    python scripts/make_kit_manifest.py --kit-root <dir> --out <dir>
        --competition-id exdark-low-light [--kit-version v1] [--shard-mb 70]

Stdlib-only, like everything else in this repo.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

SCHEMA_VERSION = 1
DEFAULT_SHARD_MB = 70
# Fixed zip metadata so regeneration is byte-identical (zip epoch, rw-r--r--).
_ZIP_DATE_TIME = (1980, 1, 1, 0, 0, 0)
_ZIP_EXTERNAL_ATTR = 0o644 << 16
# Already-compressed formats: store, don't deflate.
_STORED_SUFFIXES = {".jpg", ".jpeg", ".png"}

_SPLIT_GROUPS = ("train", "val", "test")


def _group_for(rel: PurePosixPath) -> str:
    parts = rel.parts
    if len(parts) > 2 and parts[0] == "images" and parts[1] in _SPLIT_GROUPS:
        return f"images-{parts[1]}"
    return "root-labels"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _plan_shards(kit_root: Path, shard_bytes: int) -> list[dict]:
    """Deterministic shard plan: sorted groups, sorted paths, size-cut.

    Returns [{"group": str, "files": [PurePosixPath, ...]}, ...] in final
    shard order. A group only splits when it exceeds shard_bytes.
    """
    groups: dict[str, list[tuple[PurePosixPath, int]]] = {}
    for path in sorted(kit_root.rglob("*")):
        if not path.is_file():
            continue
        rel = PurePosixPath(path.relative_to(kit_root).as_posix())
        groups.setdefault(_group_for(rel), []).append((rel, path.stat().st_size))

    shards: list[dict] = []
    for group in sorted(groups):
        entries = groups[group]
        chunks: list[list[PurePosixPath]] = [[]]
        size = 0
        for rel, nbytes in entries:
            if chunks[-1] and size + nbytes > shard_bytes:
                chunks.append([])
                size = 0
            chunks[-1].append(rel)
            size += nbytes
        for chunk in chunks:
            if chunk:
                shards.append({"group": group, "files": chunk})
    return shards


def _shard_name(index: int, group: str, seq_in_group: int, group_shards: int) -> str:
    suffix = f"-{seq_in_group:02d}" if group_shards > 1 else ""
    return f"part-{index:02d}-{group}{suffix}.zip"


def generate(
    kit_root: Path,
    out_dir: Path,
    competition_id: str,
    kit_version: str = "v1",
    shard_bytes: int = DEFAULT_SHARD_MB * 1024 * 1024,
    created_utc: str | None = None,
) -> dict:
    """Build <out_dir>/<kit_version>/ and return the manifest dict."""
    kit_root = Path(kit_root)
    if not kit_root.is_dir():
        raise SystemExit(f"kit root is not a directory: {kit_root}")
    kit_dir_name = kit_root.name

    version_dir = Path(out_dir) / kit_version
    version_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = version_dir / "manifest.json"
    for stale in version_dir.iterdir():
        if stale != manifest_path and not stale.name.startswith("part-"):
            raise SystemExit(
                f"refusing to write into {version_dir}: unexpected entry {stale.name}"
            )

    plan = _plan_shards(kit_root, shard_bytes)
    group_totals: dict[str, int] = {}
    for shard in plan:
        group_totals[shard["group"]] = group_totals.get(shard["group"], 0) + 1

    archives: list[dict] = []
    files: list[dict] = []
    group_seq: dict[str, int] = {}
    for index, shard in enumerate(plan):
        group = shard["group"]
        seq = group_seq.get(group, 0)
        group_seq[group] = seq + 1
        name = _shard_name(index, group, seq, group_totals[group])
        zip_path = version_dir / name

        with zipfile.ZipFile(zip_path, "w") as zf:
            for rel in shard["files"]:
                data = (kit_root / Path(rel.as_posix())).read_bytes()
                entry = f"{kit_dir_name}/{rel.as_posix()}"
                info = zipfile.ZipInfo(entry, date_time=_ZIP_DATE_TIME)
                info.external_attr = _ZIP_EXTERNAL_ATTR
                info.compress_type = (
                    zipfile.ZIP_STORED
                    if PurePosixPath(entry).suffix.lower() in _STORED_SUFFIXES
                    else zipfile.ZIP_DEFLATED
                )
                zf.writestr(info, data)
                files.append(
                    {
                        "path": entry,
                        "bytes": len(data),
                        "sha256": _sha256_bytes(data),
                        "archive": name,
                    }
                )

        archives.append(
            {
                "name": name,
                "bytes": zip_path.stat().st_size,
                "sha256": _sha256_file(zip_path),
                "file_count": len(shard["files"]),
            }
        )
        print(f"  {name}: {len(shard['files'])} files, "
              f"{archives[-1]['bytes'] / 1e6:.1f} MB", flush=True)

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "competition_id": competition_id,
        "kit_version": kit_version,
        "kit_dir_name": kit_dir_name,
        "created_utc": created_utc
        or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total_bytes": sum(f["bytes"] for f in files),
        "file_count": len(files),
        "archives": archives,
        "files": files,
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--kit-root", required=True, type=Path,
                        help="the kit directory (e.g. .../package_build/starter_kit)")
    parser.add_argument("--out", required=True, type=Path,
                        help="output parent; the version dir is created inside it")
    parser.add_argument("--competition-id", required=True,
                        help="stable bucket identifier (NOT the Kaggle slug)")
    parser.add_argument("--kit-version", default="v1")
    parser.add_argument("--shard-mb", type=int, default=DEFAULT_SHARD_MB)
    args = parser.parse_args(argv)

    manifest = generate(
        args.kit_root,
        args.out,
        args.competition_id,
        args.kit_version,
        shard_bytes=args.shard_mb * 1024 * 1024,
    )
    print(
        f"{args.kit_version}: {manifest['file_count']} files, "
        f"{manifest['total_bytes']:,} bytes, {len(manifest['archives'])} archives "
        f"-> {Path(args.out) / args.kit_version}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
