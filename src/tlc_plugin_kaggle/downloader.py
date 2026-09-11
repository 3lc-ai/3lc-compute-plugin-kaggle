# Copyright 2026 3LC Inc.
# SPDX-License-Identifier: AGPL-3.0-only
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
    if str(data.get("mode") or "").strip() == "top_up":
        # A top-up has no destination to choose: it writes into the directory
        # the recorded kit is already in. Probing/creating dest/<version> here
        # would create an empty v3 folder beside a kit that is about to become
        # v3 in place, which is the confusion this whole path removes.
        return {"mode": "top_up", "keep_archives": bool(data.get("keep_archives"))}

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


def fetch_manifest(
    version_dir: Path, log: Callable[[str], None], *, persist: bool = True
) -> dict[str, Any]:
    """Fresh manifest from the CDN, persisted next to the shards.

    ``persist=False`` returns it without writing. The top-up needs that: its
    target directory already holds the OLD version's manifest, which stays
    correct for the tree beside it until the top-up actually succeeds. Writing
    the new one first would leave a failed top-up claiming a version the tree
    is not, and Verify would report mass mismatch on an intact kit."""
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
    # The prefix is built from STARTER_KIT_VERSION, so a manifest naming a
    # different version means the object under that prefix is not the kit this
    # plugin asked for: a staging mistake, not drift. It used to pass silently,
    # visible only in a check-detail line nothing compared.
    served = str(manifest.get("kit_version") or "")
    if served != constants.STARTER_KIT_VERSION:
        raise RuntimeError(
            f"The published manifest is for kit {served or '(unnamed)'}, but this "
            f"plugin asked for kit {constants.STARTER_KIT_VERSION}. The starter kit "
            "is misconfigured on the server. Report this to the organizers; there "
            "is nothing to fix on this machine."
        )
    if persist:
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
    honesty rule as import_state: success means "on disk right now") AND
    against the shipped kit version.

    Three distinct states, deliberately named apart:

      "success"    — the kit on disk is the version this plugin ships.
      "superseded" — a complete, intact kit of an OLDER version. Not a fault
                     and not an error: the participant keeps training. It
                     carries kit_dir (the resolved directory) so the fragment
                     renders the real path instead of rebuilding it.
      "stale"      — the recorded kit is gone from disk.

    "superseded" is not folded into "stale": one state string covering two
    conditions is the divergence class this release exists to close, and the
    two need opposite copy (one offers a fresh download, the other says
    nothing is wrong). Before v1.2.12 nothing compared the versions at all, so
    a v1 holder was told "downloaded 2 days ago" forever after the v2 bump.
    """
    from tlc_plugin_kaggle import jobs

    for job in jobs.list_jobs("download_kit"):
        if job.get("status") != "completed":
            continue
        facts = job.get("facts") or {}
        yaml_path = str(facts.get("dataset_yaml") or "")
        if not (yaml_path and Path(yaml_path).is_file()):
            return {
                "state": "stale",
                "reason": f"kit no longer on disk at {yaml_path or facts.get('dest_dir')}",
            }
        recorded = str(facts.get("kit_version") or "")
        dest_dir = str(facts.get("dest_dir") or "")
        out: dict[str, Any] = {
            "state": "success" if recorded == constants.STARTER_KIT_VERSION else "superseded",
            "job_id": job.get("id"),
            "created_at": job.get("created_at"),
            "dest_dir": facts.get("dest_dir"),
            "dataset_yaml": yaml_path,
            "kit_version": facts.get("kit_version"),
            "current_version": constants.STARTER_KIT_VERSION,
            "file_count": (job.get("result") or {}).get("file_count"),
        }
        # Resolved here, not in the fragment: the kit directory is a
        # server-side fact and the copy names it verbatim. Recorded on every
        # state, not just superseded, because verify_now needs it too.
        out["kit_dir"] = kit_dir_of(facts)
        return out
    return {"state": "empty"}


def kit_dir_of(facts: dict[str, Any]) -> str:
    """The version directory a download record actually wrote.

    Recorded since v1.2.13 as facts["kit_dir"]. Before that it could only be
    derived as dest/<version>, which an IN-PLACE top-up breaks: a topped-up
    v1 holder is on v3 content inside the v1 directory, so dest/"v3" names a
    directory that does not exist while a good kit sits next door. Read the
    record; derive only for records written before it was recorded; and when
    the record names no version at all, return "" rather than guess - that
    fallback was the v1.2.12 bug in miniature.
    """
    recorded_dir = str(facts.get("kit_dir") or "")
    if recorded_dir:
        return recorded_dir
    dest_dir = str(facts.get("dest_dir") or "")
    version = str(facts.get("kit_version") or "")
    return str(Path(dest_dir) / version) if (dest_dir and version) else ""


def verify_now() -> dict[str, Any]:
    """On-demand full files[] re-verification for the revisit Verify action.

    Uses the manifest kept next to the extracted kit (the version prefix is
    immutable, so the local copy equals the CDN's). The revisit line's claim
    is exactly as strong as its check; this is the strong check (T1)."""
    import json

    state = download_state()
    # A superseded kit verifies exactly like a current one: the manifest beside
    # it is its OWN version's, so the check is honest for the population this
    # release is for. Refusing here would break Verify for precisely them.
    if state.get("state") not in ("success", "superseded"):
        return {"ok": False, "error": "No completed download on record. Download the starter kit first."}
    version_dir_str = str(state.get("kit_dir") or "")
    if not version_dir_str:
        # No falling back to the CURRENT constant: that is the bug in
        # miniature — it would look under a directory this record never wrote
        # and report the manifest missing while a good kit sat beside it.
        return {
            "ok": False,
            "error": "This download predates kit-version recording, so the kit "
                     "directory cannot be identified. Download the starter kit again.",
        }
    version_dir = Path(version_dir_str)
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


# The dataset.yaml keys that already-imported Tables resolve through. A
# top-up writes into the directory those Tables read from, so changing any of
# these under them would silently re-point or re-label live data. Comments and
# formatting are not load-bearing and a change confined to them is allowed
# through - which is why this compares PARSED values, not the file hash.
_LOAD_BEARING_YAML_KEYS = ("path", "train", "val", "test", "nc", "names")


def _yaml_keys(raw: bytes) -> dict[str, Any]:
    import yaml

    cfg = yaml.safe_load(raw.decode("utf-8"))
    if not isinstance(cfg, dict):
        raise ValueError("dataset.yaml is not a mapping")
    return {k: cfg.get(k) for k in _LOAD_BEARING_YAML_KEYS}


def top_up_plan(
    new_manifest: dict[str, Any],
    old_manifest: dict[str, Any] | None,
    version_dir: Path,
) -> dict[str, Any]:
    """What a top-up would fetch, write and remove. Pure: reads the disk,
    changes nothing.

    ``write`` is the delta against the tree as it actually is, not against the
    old manifest, so a locally damaged file is repaired by the same pass.

    ``remove`` is deliberately NOT verify_tree's ``extra``. Extra means "on
    disk, not in the new manifest", which covers both files the kit dropped and
    files the participant added themselves; deleting the second kind would be
    destroying their work. Only paths the OLD manifest also claimed are kit
    files, so only those can be removals. With no old manifest on disk the
    distinction cannot be drawn at all, and nothing is removed."""
    new_files = {f["path"]: f for f in new_manifest["files"]}
    delta = verify_tree(new_manifest, version_dir)
    write = sorted(set(delta["missing"]) | set(delta["mismatch"]))

    removable: list[str] = []
    unowned_extras = list(delta["extra"])
    if old_manifest is not None:
        old_paths = {f["path"] for f in old_manifest["files"]}
        removable = sorted(p for p in delta["extra"] if p in old_paths)
        unowned_extras = sorted(set(delta["extra"]) - set(removable))

    archives = sorted({str(new_files[p]["archive"]) for p in write})
    by_name = {a["name"]: a for a in new_manifest["archives"]}
    return {
        "write": write,
        "remove": removable,
        "keep_extra": unowned_extras,
        "archives": [by_name[n] for n in archives],
        "matched": delta["matched"],
        "removals_known": old_manifest is not None,
        "write_bytes": sum(int(new_files[p]["bytes"]) for p in write),
        "fetch_bytes": sum(int(by_name[n]["bytes"]) for n in archives),
    }


def run_top_up(params: dict[str, Any], ctx: Any) -> dict[str, Any]:
    """Update an existing kit IN PLACE to the shipped version.

    The point of the whole thing: a superseded holder's Tables resolve through
    the dataset.yaml in THIS directory (``path: .`` resolves against the yaml's
    own dir), so a fresh download into a new directory leaves them training
    against the old kit forever. Writing into the directory they already read
    is the only update that reaches them - and it is why the dataset.yaml gate
    below exists, because that same property makes a careless write dangerous.

    Cancellation is honored up to the first byte written into the tree; after
    that the pass runs to its re-verify, which is what makes the result either
    wholly the new kit or a named failure, never a silent half-kit."""
    import json

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

    state = download_state()
    if state.get("state") == "success":
        log("The kit on disk is already the current version. Nothing to update.")
        return {
            "cancelled": False,
            "updated": False,
            "reason": "already current",
            "kit_version": constants.STARTER_KIT_VERSION,
        }
    if state.get("state") != "superseded":
        raise RuntimeError(
            "There is no complete starter kit on this machine to update. "
            "Download the starter kit first."
        )

    version_dir = Path(str(state.get("kit_dir") or ""))
    from_version = str(state.get("kit_version") or "")
    if not version_dir.is_dir():
        raise RuntimeError(
            f"The recorded kit directory is gone: {version_dir}. "
            "Download the starter kit again."
        )
    dest_dir = Path(str(state.get("dest_dir") or version_dir.parent))

    old_manifest: dict[str, Any] | None = None
    old_path = version_dir / "manifest.json"
    if old_path.is_file():
        try:
            old_manifest = json.loads(old_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            old_manifest = None

    # persist=False: the manifest beside the tree still describes the tree
    # until this pass succeeds. See fetch_manifest.
    new_manifest = fetch_manifest(version_dir, log, persist=False)
    kit_dir_name = str(new_manifest["kit_dir_name"])
    plan = top_up_plan(new_manifest, old_manifest, version_dir)
    check(
        "update planned from the published manifest",
        True,
        f"{from_version} -> {new_manifest['kit_version']}: {len(plan['write'])} files "
        f"to write, {len(plan['remove'])} to remove, {plan['matched']} already "
        f"current; {len(plan['archives'])} of {len(new_manifest['archives'])} "
        "shards needed",
    )
    if not plan["removals_known"]:
        check(
            "removals could not be determined",
            True,
            "no manifest beside the kit, so nothing is removed; files the new kit "
            "dropped stay on disk as extras",
        )
    if plan["keep_extra"]:
        check(
            "files not from the kit are left alone",
            True,
            f"{len(plan['keep_extra'])} extra files kept",
        )

    if not plan["write"] and not plan["remove"]:
        # Content already matches; only the stamp is behind.
        _write_manifest(old_path, new_manifest)
        _restamp(set_field, dest_dir, version_dir, new_manifest, kit_dir_name, log)
        log("Kit content already matches the current version; record updated.")
        return _top_up_result(
            dest_dir, version_dir, new_manifest, kit_dir_name, plan, from_version
        )

    # Delta-scoped, not 2x the kit: only the selected shards plus the files
    # they write land on disk, and the shards go away again at the end.
    needed = plan["fetch_bytes"] + plan["write_bytes"] + (100 << 20)
    free = shutil.disk_usage(version_dir).free
    detail = f"{free / 1e9:.1f} GB free, ~{needed / 1e9:.1f} GB needed"
    if not check("enough disk space for the update", free >= needed, detail):
        raise RuntimeError(
            f"Not enough disk space at {version_dir} ({detail}). Free up space, "
            "then run the update again."
        )

    # ── Fetch only the shards the delta needs ───────────────────────────
    total = sum(int(a["bytes"]) for a in plan["archives"]) or 1
    done = 0
    try:
        for i, entry in enumerate(plan["archives"]):
            if is_cancelled():
                raise _Cancelled()

            def report(shard_done: int, _i: int = i, _n: str = entry["name"]) -> None:
                set_progress(
                    {
                        "percent": round(70.0 * (done + shard_done) / total, 1),
                        "label": f"Downloading update {_i + 1}/{len(plan['archives'])}",
                        "phase": "download",
                        "archive": _n,
                        "bytes_done": done + shard_done,
                        "bytes_total": total,
                    }
                )

            _download_shard(entry, version_dir, log, report, is_cancelled)
            done += int(entry["bytes"])
    except _Cancelled:
        log("Cancelled before anything was changed. The kit on disk is untouched.")
        return {
            "cancelled": True,
            "updated": False,
            "resumable": True,
            "kit_dir": str(version_dir),
        }
    check(
        f"{len(plan['archives'])} update shards downloaded and sha256-verified",
        True,
        f"{total:,} bytes",
    )

    # ── The gate: refuse to re-point live Tables ────────────────────────
    yaml_rel = f"{kit_dir_name}/dataset.yaml"
    yaml_path = version_dir / kit_dir_name / "dataset.yaml"
    if yaml_rel in plan["write"] and yaml_path.is_file():
        new_raw = _entry_bytes(version_dir, plan["archives"], yaml_rel)
        try:
            before, after = _yaml_keys(yaml_path.read_bytes()), _yaml_keys(new_raw)
        except (ValueError, OSError) as exc:
            raise RuntimeError(
                f"dataset.yaml could not be compared before updating in place "
                f"({exc}). Download the starter kit fresh instead; the kit on disk "
                "is unchanged."
            ) from exc
        changed = sorted(k for k in _LOAD_BEARING_YAML_KEYS if before[k] != after[k])
        if not check(
            "dataset.yaml keeps its load-bearing keys",
            not changed,
            ", ".join(changed) if changed else "unchanged",
        ):
            raise RuntimeError(
                "This update changes dataset.yaml keys that tables you have already "
                f"imported resolve through ({', '.join(changed)}), so it cannot be "
                "applied in place without changing what those tables read. Download "
                "the starter kit fresh into a new folder and import it. The kit on "
                "disk is unchanged."
            )

    # ── Write, in place ─────────────────────────────────────────────────
    set_progress({"percent": 72.0, "label": "Updating files", "phase": "extract"})
    _extract_selected(version_dir, plan["archives"], plan["write"])
    check(f"{len(plan['write'])} files updated in place", True, str(version_dir))

    if plan["remove"]:
        set_progress(
            {"percent": 85.0, "label": "Removing dropped files", "phase": "extract"}
        )
        for rel in plan["remove"]:
            (version_dir / rel).unlink(missing_ok=True)
            log(f"  REMOVED {rel}")
        check(f"{len(plan['remove'])} files the new kit dropped were removed", True)

    # ── Re-verify the whole tree, not just what changed ─────────────────
    set_progress({"percent": 90.0, "label": "Verifying files", "phase": "verify"})
    delta = verify_tree(new_manifest, version_dir)
    ok = not delta["mismatch"] and not delta["missing"]
    detail = f"{delta['matched']}/{new_manifest['file_count']} files verified"
    if not ok:
        broken = delta["mismatch"] + delta["missing"]
        detail += "; first problems: " + ", ".join(broken[:5])
    if not check("updated kit matches the published manifest", ok, detail):
        for path in (delta["mismatch"] + delta["missing"])[:50]:
            log(f"  DELTA {path}")
        raise RuntimeError(
            f"{len(delta['mismatch']) + len(delta['missing'])} files do not match "
            "the manifest after the update. Run the update again; completed shards "
            "are kept."
        )

    # ── Restamp, then clean up ──────────────────────────────────────────
    _write_manifest(old_path, new_manifest)
    _restamp(set_field, dest_dir, version_dir, new_manifest, kit_dir_name, log)
    if not bool(params.get("keep_archives")):
        for entry in plan["archives"]:
            (version_dir / entry["name"]).unlink(missing_ok=True)
        log("Update shards removed after verification (manifest.json kept)")

    set_progress({"percent": 100.0, "label": "Complete", "phase": "done"})
    return _top_up_result(
        dest_dir,
        version_dir,
        new_manifest,
        kit_dir_name,
        plan,
        from_version,
        verified=delta["matched"],
    )


def _write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    import json

    path.write_text(
        json.dumps(manifest, indent=1) + "\n", encoding="utf-8", newline="\n"
    )


def _entry_bytes(
    version_dir: Path, archives: list[dict[str, Any]], rel: str
) -> bytes:
    """Read one entry out of the downloaded shards without extracting it."""
    for entry in archives:
        zp = version_dir / entry["name"]
        if not zp.is_file():
            continue
        with zipfile.ZipFile(zp) as zf:
            if rel in zf.namelist():
                return zf.read(rel)
    raise RuntimeError(f"{rel} is not in any downloaded shard")


def _extract_selected(
    version_dir: Path, archives: list[dict[str, Any]], wanted: list[str]
) -> None:
    """Extract exactly ``wanted`` from the given shards. Not extractall: the
    matched majority is already correct on disk, and rewriting it would turn a
    one-file update into a whole-kit rewrite."""
    remaining = set(wanted)
    for entry in archives:
        zp = version_dir / entry["name"]
        with zipfile.ZipFile(zp) as zf:
            for info in zf.infolist():
                n = info.filename.replace("\\", "/")
                if n.startswith("/") or ".." in n.split("/"):
                    raise RuntimeError(
                        f"Unsafe path in {entry['name']}: {info.filename}"
                    )
                if n not in remaining:
                    continue
                target = version_dir / n
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
                remaining.discard(n)
    if remaining:
        raise RuntimeError(
            f"{len(remaining)} file(s) the update needs were not in the downloaded "
            f"shards: {', '.join(sorted(remaining)[:5])}"
        )


def _restamp(
    set_field: Callable[[str, Any], None],
    dest_dir: Path,
    version_dir: Path,
    manifest: dict[str, Any],
    kit_dir_name: str,
    log: Callable[[str], None],
) -> None:
    """Record the kit this directory now holds. kit_dir is the fact that makes
    the record survive the version no longer matching the directory name."""
    yaml_path = version_dir / kit_dir_name / "dataset.yaml"
    set_field("dest_dir", str(dest_dir))
    set_field("kit_version", str(manifest["kit_version"]))
    set_field("kit_dir", str(version_dir))
    set_field("dataset_yaml", str(yaml_path))
    _publish_session_yaml(yaml_path)
    log(f"Kit at {version_dir} is now {manifest['kit_version']}")


def _top_up_result(
    dest_dir: Path,
    version_dir: Path,
    manifest: dict[str, Any],
    kit_dir_name: str,
    plan: dict[str, Any],
    from_version: str,
    verified: int | None = None,
) -> dict[str, Any]:
    return {
        "cancelled": False,
        "updated": True,
        "dest_dir": str(dest_dir),
        "kit_dir": str(version_dir),
        "from_version": from_version,
        "kit_version": str(manifest["kit_version"]),
        "dataset_yaml": str(version_dir / kit_dir_name / "dataset.yaml"),
        "file_count": int(manifest["file_count"]),
        "total_bytes": int(manifest["total_bytes"]),
        "written_files": len(plan["write"]),
        "removed_files": len(plan["remove"]),
        "fetched_archives": len(plan["archives"]),
        "verified_files": plan["matched"] if verified is None else verified,
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

    if str(params.get("mode") or "").strip() == "top_up":
        # Same job kind on purpose: download_state keys off the newest
        # completed download_kit record, and a top-up IS the newest thing
        # that happened to this kit. A separate kind would need every
        # reader to learn about it, which is the divergence shape v1.2.12
        # closed.
        return run_top_up(params, ctx)

    resolved = resolve_params(params)  # re-validates: /run skips /validate
    dest_dir = Path(resolved["dest_dir"])
    keep_archives = resolved["keep_archives"]
    version_dir = dest_dir / constants.STARTER_KIT_VERSION
    set_field("dest_dir", str(dest_dir))
    set_field("kit_version", constants.STARTER_KIT_VERSION)
    set_field("kit_dir", str(version_dir))

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
        "kit_dir": str(version_dir),
        "dataset_yaml": str(yaml_path),
        "file_count": int(manifest["file_count"]),
        "total_bytes": int(manifest["total_bytes"]),
        "verified_files": int(delta["matched"]),
        "extra_files": len(delta["extra"]),
    }
