"""Starter-kit CDN downloader (job kind "download_kit").

Fetches the immutable versioned CDN prefix (constants.starter_kit_prefix()),
downloads every shard its manifest.json lists with sha256 verification and
Range-based resume, extracts the kit tree into <dest_dir>/<version>/, verifies
EVERY manifest file against the extracted tree, and finally publishes the
kit's dataset.yaml into the shared session (config_store) so the Import form
starts populated — the A5 server-side session write.

Integrity is manifest sha256, never the HTTP ETag: the shards are multipart
uploads, so their ETags come back as "<hash>-<parts>" markers that are NOT
content MD5s (verified empirically at staging, 2026-08-27). Do not "optimize"
verification to ETag comparison.

Full files[] verification stays on (all 14,004 files, measured ~7.5s) against
a manifest downloaded fresh every run: the prefix is immutable, so a
manifest/shard mismatch means a staging error, not drift.

Resume: a shard downloads to "<name>.part"; an interrupted or cancelled job
leaves .part files behind, and the next job continues them with an HTTP Range
request (the CDN answers 206 — verified at staging; a 200 answer falls back
to a clean restart of that shard). A shard already complete on disk with a
matching sha256 is skipped without a request. Shard archives are deleted only
after the whole tree verifies, so a failed run always resumes.
"""

from __future__ import annotations

import hashlib
import shutil
import urllib.error
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from tlc_plugin_kaggle import constants

_CHUNK = 1 << 20  # 1 MiB reads
# Cancellation/progress cadence in chunks: is_cancelled reads the job record
# from disk, and set_progress flushes it — once per _CHUNK would be a write
# per MB for a 623 MB kit.
_POLL_EVERY = 4
_TIMEOUT = 30  # seconds, per request
_SCHEMA_VERSION = 1  # manifest schema this reader understands
_RETRIES = 2  # attempts per shard before the job fails

# Everything the plugin owns lives under ~/.3lc-kaggle-plugin (jobs/, runs/,
# ui_config.json) — the kit is no exception: one directory to document, one to
# delete, and the redirected-home caveat (P1 class) stays a single caveat
# instead of gaining a new instance. COMPETITION_ID keeps a future generic
# fork's kits apart; the version dir under it keeps v2 from colliding with v1.
DEFAULT_DEST = Path.home() / ".3lc-kaggle-plugin" / "data" / constants.COMPETITION_ID

# Participant-facing (renders in a UI callout, so no em dashes: ui-notes §4).
_RERUN_RESUMES = (
    "Run the download again. Completed shards are kept, and the job resumes "
    "where it stopped."
)


class _Cancelled(Exception):
    """Internal: unwinds the download loop on a cooperative cancel."""


def kit_url(name: str) -> str:
    return f"{constants.starter_kit_prefix()}/{name}"


def _open(url: str, start: int | None = None):
    """One thin seam over urllib (the tests' stub point). ``start`` adds an
    HTTP Range header for resume; callers must handle a 200 (range ignored)."""
    headers = {"Range": f"bytes={start}-"} if start else {}
    req = urllib.request.Request(url, headers=headers)
    return urllib.request.urlopen(req, timeout=_TIMEOUT)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def resolve_params(data: dict[str, Any]) -> dict[str, Any]:
    """Resolve and probe the download params. Shared by /validate/download
    and run_download (defense in depth: the host /run path skips /validate).
    Raises ValueError with a participant-facing message.

    keep_archives defaults to FALSE: keeping ~616 MB of shard zips doubles
    disk use for no participant benefit, and resume-after-failure does not
    need them kept — shards are only deleted AFTER the tree verifies, so
    every failure path still finds them on disk."""
    raw = str(data.get("dest_dir") or "").strip().strip('"')
    dest = Path(raw).expanduser() if raw else DEFAULT_DEST
    if not dest.is_absolute():
        raise ValueError(f"Destination must be an absolute path, got: {dest}")
    version_dir = dest / constants.STARTER_KIT_VERSION
    try:
        version_dir.mkdir(parents=True, exist_ok=True)
        probe = version_dir / ".write-probe"
        probe.write_bytes(b"")
        probe.unlink()
    except OSError as exc:
        raise ValueError(f"Destination is not writable: {dest} ({exc})") from exc
    return {"dest_dir": str(dest), "keep_archives": bool(data.get("keep_archives"))}


def fetch_manifest(version_dir: Path, log: Callable[[str], None]) -> dict[str, Any]:
    """Fresh manifest from the CDN, persisted next to the shards."""
    import json

    url = kit_url("manifest.json")
    log(f"Fetching {url}")
    try:
        with _open(url) as resp:
            raw = resp.read()
    except (urllib.error.URLError, OSError) as exc:
        raise RuntimeError(
            f"Could not reach the starter-kit CDN: {exc}. Check the internet "
            f"connection. {_RERUN_RESUMES}"
        ) from exc
    manifest = json.loads(raw.decode("utf-8"))
    if manifest.get("schema_version") != _SCHEMA_VERSION:
        raise RuntimeError(
            f"The published manifest uses schema {manifest.get('schema_version')}, "
            f"this plugin understands schema {_SCHEMA_VERSION}. Update the plugin, "
            "then run the download again."
        )
    (version_dir / "manifest.json").write_bytes(raw)
    return manifest


def _free_space(version_dir: Path, manifest: dict[str, Any]) -> tuple[bool, str]:
    """Peak usage is shards + extracted tree (archives are deleted only after
    verification), minus whatever a previous attempt already left on disk."""
    have = sum(p.stat().st_size for p in version_dir.rglob("*") if p.is_file())
    needed = max(0, 2 * int(manifest["total_bytes"]) + (100 << 20) - have)
    free = shutil.disk_usage(version_dir).free
    return free >= needed, f"{free / 1e9:.1f} GB free, ~{needed / 1e9:.1f} GB needed"


def _download_shard(
    entry: dict[str, Any],
    version_dir: Path,
    log: Callable[[str], None],
    report: Callable[[int], None],
    is_cancelled: Callable[[], bool],
) -> None:
    """One shard: skip if already verified on disk, else resume/download,
    then sha256-verify and finalize (.part -> final rename)."""
    name, size, sha = entry["name"], int(entry["bytes"]), str(entry["sha256"])
    final = version_dir / name
    part = version_dir / (name + ".part")

    if final.is_file():
        if final.stat().st_size == size and _sha256_file(final) == sha:
            log(f"{name}: already on disk, sha256 verified — skipped")
            report(size)
            return
        log(f"{name}: on disk but does not match the manifest — re-downloading")
        final.unlink()

    last_error: Exception | None = None
    for attempt in range(1, _RETRIES + 1):
        try:
            start = part.stat().st_size if part.is_file() else 0
            if start >= size:  # over-long partial can only be corrupt
                part.unlink()
                start = 0
            if start:
                log(f"{name}: resuming at byte {start:,} of {size:,}")
            received = start
            with _open(kit_url(name), start or None) as resp, part.open(
                "r+b" if start else "wb"
            ) as f:
                if start:
                    if getattr(resp, "status", 200) == 206:
                        f.seek(0, 2)
                    else:
                        log(f"{name}: range request not honored — restarting the shard")
                        f.seek(0)
                        f.truncate()
                        received = 0
                chunks = 0
                while True:
                    chunk = resp.read(_CHUNK)
                    if not chunk:
                        break
                    f.write(chunk)
                    received += len(chunk)
                    chunks += 1
                    if chunks % _POLL_EVERY == 0:
                        report(min(received, size))
                        if is_cancelled():
                            raise _Cancelled()
            if received != size:
                raise OSError(f"connection ended at {received:,} of {size:,} bytes")
            if _sha256_file(part) != sha:
                part.unlink()  # nothing in it is trustworthy — restart clean
                raise OSError("sha256 mismatch after download")
            part.replace(final)
            log(f"{name}: {size:,} bytes, sha256 verified")
            report(size)
            return
        except _Cancelled:
            raise
        except (urllib.error.URLError, OSError) as exc:
            last_error = exc
            if attempt < _RETRIES:
                log(f"{name}: {exc} — retrying")
    raise RuntimeError(f"Could not download {name}: {last_error}. {_RERUN_RESUMES}")


def verify_tree(manifest: dict[str, Any], version_dir: Path) -> dict[str, Any]:
    """Compare the extracted kit tree against manifest files[] (path, bytes,
    sha256). Walks only the kit dir, so shards/manifest alongside it never
    count as extras. Same delta vocabulary as scripts/check_kit_parity.py."""
    kit_dir_name = str(manifest["kit_dir_name"])
    expected = {f["path"]: f for f in manifest["files"]}
    kit_root = version_dir / kit_dir_name

    actual: dict[str, Path] = {}
    if kit_root.is_dir():
        for p in kit_root.rglob("*"):
            if p.is_file():
                rel = PurePosixPath(p.relative_to(version_dir).as_posix()).as_posix()
                actual[rel] = p

    out: dict[str, Any] = {"matched": 0, "mismatch": [], "missing": [], "extra": []}
    for path, entry in expected.items():
        p = actual.get(path)
        if p is None:
            out["missing"].append(path)
        elif p.stat().st_size != entry["bytes"] or _sha256_file(p) != entry["sha256"]:
            out["mismatch"].append(path)
        else:
            out["matched"] += 1
    out["extra"] = sorted(set(actual) - set(expected))
    out["mismatch"].sort()
    out["missing"].sort()
    return out


def _publish_session_yaml(yaml_path: Path) -> None:
    """A5 (Phase 0, approved): after a verified download the job writes
    session.dataset_yaml so the Import form starts populated. config_store
    replaces the session object whole, so this merges onto the freshest load;
    a browser save racing this write wins or loses whole — last writer wins,
    by design."""
    from tlc_plugin_kaggle import config_store

    cfg = config_store.load()
    stored = cfg.get("session")
    session = {
        **config_store.default_session(),
        **(stored if isinstance(stored, dict) else {}),
    }
    session["dataset_yaml"] = str(yaml_path)
    config_store.save({"session": session})


def download_state() -> dict[str, Any]:
    """Revisit state for the Download section: the newest completed
    download_kit job, re-verified against dataset.yaml on disk (the same
    honesty rule as import_state: success means "on disk right now")."""
    from tlc_plugin_kaggle import jobs

    for job in jobs.list_jobs("download_kit"):
        if job.get("status") != "completed":
            continue
        facts = job.get("facts") or {}
        yaml_path = str(facts.get("dataset_yaml") or "")
        if yaml_path and Path(yaml_path).is_file():
            return {
                "state": "success",
                "job_id": job.get("id"),
                "created_at": job.get("created_at"),
                "dest_dir": facts.get("dest_dir"),
                "dataset_yaml": yaml_path,
                "kit_version": facts.get("kit_version"),
                "file_count": (job.get("result") or {}).get("file_count"),
            }
        return {
            "state": "stale",
            "reason": f"kit no longer on disk at {yaml_path or facts.get('dest_dir')}",
        }
    return {"state": "empty"}


def verify_now() -> dict[str, Any]:
    """On-demand full files[] re-verification for the revisit Verify action.

    Uses the manifest kept next to the extracted kit (the version prefix is
    immutable, so the local copy equals the CDN's). The revisit line's claim
    is exactly as strong as its check; this is the strong check (T1)."""
    import json

    state = download_state()
    if state.get("state") != "success":
        return {"ok": False, "error": "No completed download on record. Download the starter kit first."}
    version_dir = Path(str(state["dest_dir"])) / str(state.get("kit_version") or constants.STARTER_KIT_VERSION)
    manifest_path = version_dir / "manifest.json"
    if not manifest_path.is_file():
        return {"ok": False, "error": f"manifest.json is no longer on disk at {manifest_path}."}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    delta = verify_tree(manifest, version_dir)
    ok = not delta["mismatch"] and not delta["missing"]
    return {
        "ok": ok,
        "file_count": int(manifest["file_count"]),
        "matched": delta["matched"],
        "missing_count": len(delta["missing"]),
        "mismatch_count": len(delta["mismatch"]),
        "missing": delta["missing"][:20],
        "mismatch": delta["mismatch"][:20],
        "extra_count": len(delta["extra"]),
    }


def run_download(params: dict[str, Any], ctx: Any) -> dict[str, Any]:
    """The download job. Raises with a participant-facing message on failure;
    returns {"cancelled": True, ...} when stopped (state stays resumable).

    ``ctx`` is a jobs.JobCtx; like run_import, only log/set_checks are
    required — the rest degrade to no-ops."""
    log = ctx.log
    set_checks = ctx.set_checks
    set_progress = getattr(ctx, "set_progress", lambda p: None)
    set_field = getattr(ctx, "set_field", lambda k, v: None)
    is_cancelled = getattr(ctx, "is_cancelled", lambda: False)

    checks: list[dict[str, Any]] = []

    def check(label: str, ok: bool, detail: str = "") -> bool:
        checks.append({"label": label, "ok": bool(ok), "detail": detail})
        set_checks(checks)
        log(("PASS " if ok else "FAIL ") + label + (f" — {detail}" if detail else ""))
        return ok

    resolved = resolve_params(params)  # re-validates: /run skips /validate
    dest_dir = Path(resolved["dest_dir"])
    keep_archives = resolved["keep_archives"]
    version_dir = dest_dir / constants.STARTER_KIT_VERSION
    set_field("dest_dir", str(dest_dir))
    set_field("kit_version", constants.STARTER_KIT_VERSION)

    manifest = fetch_manifest(version_dir, log)
    archives = manifest["archives"]
    check(
        "manifest fetched from the CDN",
        True,
        f"{manifest['kit_version']}: {manifest['file_count']} files, "
        f"{manifest['total_bytes']:,} bytes in {len(archives)} shards",
    )

    space_ok, space_detail = _free_space(version_dir, manifest)
    if not check("enough disk space at the destination", space_ok, space_detail):
        raise RuntimeError(
            f"Not enough disk space at {dest_dir} ({space_detail}). Free up "
            "space or choose another destination, then run the download again."
        )

    # ── Download ────────────────────────────────────────────────────────
    total = sum(int(a["bytes"]) for a in archives) or 1
    done = 0

    def cancelled_result() -> dict[str, Any]:
        log("Cancelled — completed shards are kept; running the download again resumes.")
        return {"cancelled": True, "dest_dir": str(dest_dir), "resumable": True}

    try:
        for i, entry in enumerate(archives):
            if is_cancelled():
                raise _Cancelled()

            def report(shard_done: int, _i: int = i, _name: str = entry["name"]) -> None:
                set_progress(
                    {
                        "percent": round(90.0 * (done + shard_done) / total, 1),
                        "label": f"Downloading shard {_i + 1}/{len(archives)}",
                        "phase": "download",
                        "archive": _name,
                        "bytes_done": done + shard_done,
                        "bytes_total": total,
                    }
                )

            _download_shard(entry, version_dir, log, report, is_cancelled)
            done += int(entry["bytes"])
    except _Cancelled:
        return cancelled_result()
    check(
        f"all {len(archives)} shards downloaded and sha256-verified",
        True,
        f"{total:,} bytes",
    )

    # ── Extract ─────────────────────────────────────────────────────────
    for i, entry in enumerate(archives):
        if is_cancelled():
            return cancelled_result()
        set_progress(
            {
                "percent": round(90.0 + 7.0 * i / len(archives), 1),
                "label": f"Extracting shard {i + 1}/{len(archives)}",
                "phase": "extract",
            }
        )
        with zipfile.ZipFile(version_dir / entry["name"]) as zf:
            for info in zf.infolist():
                n = info.filename.replace("\\", "/")
                if n.startswith("/") or ".." in n.split("/"):
                    raise RuntimeError(
                        f"Unsafe path in {entry['name']}: {info.filename}"
                    )
            zf.extractall(version_dir)
    check(
        f"all {len(archives)} shards extracted",
        True,
        f"{manifest['file_count']} files",
    )

    # ── Verify the tree (full files[], always) ──────────────────────────
    set_progress({"percent": 97.0, "label": "Verifying files", "phase": "verify"})
    delta = verify_tree(manifest, version_dir)
    tree_ok = not delta["mismatch"] and not delta["missing"]
    detail = f"{delta['matched']}/{manifest['file_count']} files verified"
    if not tree_ok:
        broken = delta["mismatch"] + delta["missing"]
        detail += "; first problems: " + ", ".join(broken[:5])
    if not check("extracted kit matches the manifest", tree_ok, detail):
        for path in (delta["mismatch"] + delta["missing"])[:50]:
            log(f"  DELTA {path}")
        raise RuntimeError(
            f"{len(delta['mismatch']) + len(delta['missing'])} files do not match "
            f"the manifest after extraction. {_RERUN_RESUMES}"
        )
    if delta["extra"]:
        # Not a failure: the kit is the participant's working copy — everything
        # the manifest promises is present and intact, extras are theirs.
        check(
            "no unexpected files in the kit tree",
            True,
            f"{len(delta['extra'])} extra files present, left in place",
        )
        for path in delta["extra"][:20]:
            log(f"  EXTRA {path}")

    yaml_path = version_dir / str(manifest["kit_dir_name"]) / "dataset.yaml"
    if not check("dataset.yaml present at the kit root", yaml_path.is_file(), str(yaml_path)):
        raise RuntimeError(f"dataset.yaml missing from the kit at {yaml_path}. {_RERUN_RESUMES}")

    # ── Publish + cleanup ───────────────────────────────────────────────
    _publish_session_yaml(yaml_path)
    set_field("dataset_yaml", str(yaml_path))
    log("Session updated: Import now points at the downloaded dataset.yaml")

    if not keep_archives:
        for entry in archives:
            (version_dir / entry["name"]).unlink(missing_ok=True)
        log("Shard archives removed after verification (manifest.json kept)")

    set_progress({"percent": 100.0, "label": "Complete", "phase": "done"})
    return {
        "cancelled": False,
        "dest_dir": str(dest_dir),
        "kit_version": str(manifest["kit_version"]),
        "dataset_yaml": str(yaml_path),
        "file_count": int(manifest["file_count"]),
        "total_bytes": int(manifest["total_bytes"]),
        "verified_files": int(delta["matched"]),
        "extra_files": len(delta["extra"]),
    }
