"""Tests for downloader.py (job kind "download_kit").

A synthetic kit (the test_kit_scripts builder) is generated into a fake CDN
directory and served through a Range-aware stub in place of downloader._open,
so every network behavior the real CDN showed at staging — 206 continuations,
range-ignoring 200s, corrupt bodies — is exercised offline in milliseconds.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from test_kit_scripts import _make_kit  # noqa: E402

import make_kit_manifest  # noqa: E402

from tlc_plugin_kaggle import config_store, constants, downloader, jobs  # noqa: E402

_CREATED = "2026-01-01T00:00:00Z"


class _Resp(io.BytesIO):
    status = 200


class FakeCDN:
    """Serves a generated version dir like the CDN and records every request."""

    def __init__(self, version_dir: Path):
        self.dir = version_dir
        self.requests: list[tuple[str, int | None]] = []
        self.tamper: dict[str, bytes] = {}
        self.ignore_ranges = False

    def open(self, url: str, start: int | None = None):
        name = url.rsplit("/", 1)[1]
        self.requests.append((name, start))
        data = self.tamper.get(name, (self.dir / name).read_bytes())
        if start and not self.ignore_ranges:
            resp = _Resp(data[start:])
            resp.status = 206
        else:
            resp = _Resp(data)
            resp.status = 200
        return resp


class FakeCtx:
    def __init__(self, cancel_on_call: int | None = None):
        self.logs: list[str] = []
        self.checks: list[dict] = []
        self.progress: list[dict] = []
        self.facts: dict = {}
        self._cancel_on = cancel_on_call
        self._calls = 0

    def log(self, m):
        self.logs.append(m)

    def set_checks(self, c):
        self.checks = [dict(x) for x in c]

    def set_progress(self, p):
        self.progress.append(dict(p))

    def set_field(self, k, v):
        self.facts[k] = v

    def is_cancelled(self):
        self._calls += 1
        return self._cancel_on is not None and self._calls >= self._cancel_on


@pytest.fixture
def cdn(tmp_path, monkeypatch):
    kit = _make_kit(tmp_path / "srv")
    make_kit_manifest.generate(
        kit, tmp_path / "srv" / "cdn", "test-comp", constants.STARTER_KIT_VERSION,
        shard_bytes=2048, created_utc=_CREATED,
    )
    fake = FakeCDN(tmp_path / "srv" / "cdn" / constants.STARTER_KIT_VERSION)
    monkeypatch.setattr(downloader, "_open", fake.open)
    monkeypatch.setattr(downloader, "DEFAULT_DEST", tmp_path / "home" / "kit-default")
    monkeypatch.setattr(config_store, "CONFIG_PATH", tmp_path / "home" / "ui_config.json")
    monkeypatch.setattr(jobs, "JOBS_DIR", tmp_path / "home" / "jobs")
    monkeypatch.setattr(jobs, "_jobs", {})
    return fake


def _manifest(fake: FakeCDN) -> dict:
    return json.loads((fake.dir / "manifest.json").read_text(encoding="utf-8"))


def _dest(tmp_path: Path) -> Path:
    return tmp_path / "participant" / "data"


def _version_dir(tmp_path: Path) -> Path:
    """Where the downloader lands the kit: dest / STARTER_KIT_VERSION.

    Derived from the constant, never spelled, so a kit-version bump needs no
    edit here (v1 -> v2 broke nine of these tests when it was a literal).
    """
    return _dest(tmp_path) / constants.STARTER_KIT_VERSION


def test_fresh_download_end_to_end(cdn, tmp_path):
    ctx = FakeCtx()
    result = downloader.run_download({"dest_dir": str(_dest(tmp_path))}, ctx)
    manifest = _manifest(cdn)

    assert result["cancelled"] is False
    assert result["file_count"] == manifest["file_count"]
    assert result["verified_files"] == manifest["file_count"]
    assert all(c["ok"] for c in ctx.checks)

    version_dir = _version_dir(tmp_path)
    yaml_path = version_dir / "starter_kit" / "dataset.yaml"
    assert yaml_path.is_file()
    assert result["dataset_yaml"] == str(yaml_path)
    # A5: the session now points Import at the downloaded kit.
    assert config_store.load()["session"]["dataset_yaml"] == str(yaml_path)
    # Shards removed after verification; the manifest stays.
    assert not list(version_dir.glob("part-*.zip"))
    assert (version_dir / "manifest.json").is_file()
    # Progress reached the generic percent contract's end state.
    assert ctx.progress[-1]["percent"] == 100.0
    assert any(p.get("phase") == "download" for p in ctx.progress)
    assert ctx.facts["dataset_yaml"] == str(yaml_path)


def test_session_write_merges_not_replaces(cdn, tmp_path):
    session = {**config_store.default_session(), "project_name": "my-project"}
    config_store.save({"session": session})
    downloader.run_download({"dest_dir": str(_dest(tmp_path))}, FakeCtx())
    after = config_store.load()["session"]
    assert after["project_name"] == "my-project"
    assert after["dataset_yaml"].endswith("dataset.yaml")


def test_completed_shard_skipped_and_partial_resumed(cdn, tmp_path):
    manifest = _manifest(cdn)
    names = [a["name"] for a in manifest["archives"]]
    version_dir = _version_dir(tmp_path)
    version_dir.mkdir(parents=True)
    # First shard already complete and valid -> no request at all.
    (version_dir / names[0]).write_bytes((cdn.dir / names[0]).read_bytes())
    # Second shard half-done -> Range continuation from its byte count.
    partial = (cdn.dir / names[1]).read_bytes()[:100]
    (version_dir / (names[1] + ".part")).write_bytes(partial)

    result = downloader.run_download({"dest_dir": str(_dest(tmp_path))}, FakeCtx())
    assert result["cancelled"] is False
    assert names[0] not in [n for n, _ in cdn.requests]
    assert (names[1], 100) in cdn.requests


def test_range_ignored_falls_back_to_full_shard(cdn, tmp_path):
    cdn.ignore_ranges = True
    manifest = _manifest(cdn)
    name = manifest["archives"][0]["name"]
    version_dir = _version_dir(tmp_path)
    version_dir.mkdir(parents=True)
    (version_dir / (name + ".part")).write_bytes((cdn.dir / name).read_bytes()[:100])

    ctx = FakeCtx()
    result = downloader.run_download({"dest_dir": str(_dest(tmp_path))}, ctx)
    assert result["cancelled"] is False
    assert (name, 100) in cdn.requests  # the range WAS asked for
    assert any("range request not honored" in m for m in ctx.logs)


def test_corrupt_shard_on_disk_is_redownloaded(cdn, tmp_path):
    manifest = _manifest(cdn)
    entry = manifest["archives"][0]
    version_dir = _version_dir(tmp_path)
    version_dir.mkdir(parents=True)
    (version_dir / entry["name"]).write_bytes(b"\x00" * entry["bytes"])

    result = downloader.run_download({"dest_dir": str(_dest(tmp_path))}, FakeCtx())
    assert result["cancelled"] is False
    assert (entry["name"], None) in cdn.requests


def test_persistent_sha_mismatch_fails_with_participant_message(cdn, tmp_path):
    manifest = _manifest(cdn)
    name = manifest["archives"][0]["name"]
    good = (cdn.dir / name).read_bytes()
    cdn.tamper[name] = good[:-1] + bytes([good[-1] ^ 0xFF])  # same size, wrong sha

    with pytest.raises(RuntimeError, match=name):
        downloader.run_download({"dest_dir": str(_dest(tmp_path))}, FakeCtx())
    # One retry happened before giving up.
    assert [n for n, _ in cdn.requests].count(name) == 2


def test_tree_verification_catches_manifest_shard_disagreement(cdn, tmp_path):
    # An impossible-on-an-immutable-prefix staging error: manifest files[]
    # promises a hash the (individually valid) shard does not contain.
    manifest = _manifest(cdn)
    manifest["files"][0]["sha256"] = "0" * 64
    (cdn.dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    ctx = FakeCtx()
    with pytest.raises(RuntimeError, match="do not match the manifest"):
        downloader.run_download({"dest_dir": str(_dest(tmp_path))}, ctx)
    failed = [c for c in ctx.checks if not c["ok"]]
    assert failed and failed[0]["label"] == "extracted kit matches the manifest"


def test_cancel_between_shards_stays_resumable(cdn, tmp_path):
    manifest = _manifest(cdn)
    names = [a["name"] for a in manifest["archives"]]
    assert len(names) > 1
    ctx = FakeCtx(cancel_on_call=2)  # first shard completes, then cancel

    result = downloader.run_download({"dest_dir": str(_dest(tmp_path))}, ctx)
    version_dir = _version_dir(tmp_path)
    assert result["cancelled"] is True and result["resumable"] is True
    assert (version_dir / names[0]).is_file()  # kept for resume
    assert not (version_dir / "starter_kit").exists()  # never extracted
    assert not config_store.CONFIG_PATH.exists()  # session untouched


def test_extra_files_are_reported_not_fatal(cdn, tmp_path):
    downloader.run_download({"dest_dir": str(_dest(tmp_path))}, FakeCtx())
    extra = _version_dir(tmp_path) / "starter_kit" / "my-notes.txt"
    extra.write_text("mine", encoding="utf-8")

    ctx = FakeCtx()
    result = downloader.run_download({"dest_dir": str(_dest(tmp_path))}, ctx)
    assert result["cancelled"] is False
    assert result["extra_files"] == 1
    assert all(c["ok"] for c in ctx.checks)
    assert extra.is_file()  # left in place


def test_default_dest_lives_under_the_plugin_home():
    # R1: everything the plugin owns stays under ~/.3lc-kaggle-plugin — the
    # kit is not the one exception, and the redirected-home caveat stays a
    # single caveat. (The cdn fixture monkeypatches this; assert the real one.)
    assert downloader.DEFAULT_DEST == (
        Path.home() / ".3lc-kaggle-plugin" / "data" / constants.COMPETITION_ID
    )


def test_resolve_params_defaults_and_rejections(cdn, tmp_path):
    params = downloader.resolve_params({})
    assert params == {"dest_dir": str(downloader.DEFAULT_DEST), "keep_archives": False}
    assert (downloader.DEFAULT_DEST / constants.STARTER_KIT_VERSION).is_dir()  # probed into existence

    with pytest.raises(ValueError, match="absolute"):
        downloader.resolve_params({"dest_dir": "relative/path"})

    quoted = f'"{_dest(tmp_path)}"'
    assert downloader.resolve_params({"dest_dir": quoted, "keep_archives": 1}) == {
        "dest_dir": str(_dest(tmp_path)),
        "keep_archives": True,
    }


def test_keep_archives_keeps_shards(cdn, tmp_path):
    downloader.run_download(
        {"dest_dir": str(_dest(tmp_path)), "keep_archives": True}, FakeCtx()
    )
    manifest = _manifest(cdn)
    version_dir = _version_dir(tmp_path)
    assert len(list(version_dir.glob("part-*.zip"))) == len(manifest["archives"])


def _write_record(ctx: FakeCtx, result: dict) -> None:
    record = {
        "id": "job-1",
        "kind": "download_kit",
        "status": "completed",
        "created_at": 1.0,
        "params": {},
        "progress": {},
        "facts": ctx.facts,
        "result": result,
    }
    jobs.JOBS_DIR.mkdir(parents=True, exist_ok=True)
    (jobs.JOBS_DIR / "job-1.json").write_text(json.dumps(record), encoding="utf-8")


def test_download_state_reverifies_disk(cdn, tmp_path):
    assert downloader.download_state() == {"state": "empty"}

    ctx = FakeCtx()
    result = downloader.run_download({"dest_dir": str(_dest(tmp_path))}, ctx)
    _write_record(ctx, result)

    state = downloader.download_state()
    assert state["state"] == "success"
    assert state["dataset_yaml"] == result["dataset_yaml"]
    assert state["file_count"] == result["file_count"]

    Path(result["dataset_yaml"]).unlink()
    assert downloader.download_state()["state"] == "stale"


def test_verify_now_passes_then_names_the_tamper(cdn, tmp_path):
    ctx = FakeCtx()
    result = downloader.run_download({"dest_dir": str(_dest(tmp_path))}, ctx)
    _write_record(ctx, result)

    v = downloader.verify_now()
    assert v["ok"] is True
    assert v["matched"] == result["file_count"]
    assert v["missing_count"] == 0 and v["mismatch_count"] == 0

    kit_root = _version_dir(tmp_path) / "starter_kit"
    tampered = next(kit_root.rglob("*.jpg"))
    tampered.write_bytes(b"xx")
    v2 = downloader.verify_now()
    assert v2["ok"] is False
    assert v2["mismatch_count"] == 1
    assert tampered.name in v2["mismatch"][0]


def test_verify_now_requires_record_and_manifest(cdn, tmp_path):
    v = downloader.verify_now()
    assert v["ok"] is False and "No completed download" in v["error"]

    ctx = FakeCtx()
    result = downloader.run_download({"dest_dir": str(_dest(tmp_path))}, ctx)
    _write_record(ctx, result)
    (_version_dir(tmp_path) / "manifest.json").unlink()
    v2 = downloader.verify_now()
    assert v2["ok"] is False and "manifest.json" in v2["error"]


# ── Version skew across a kit bump (F1) ──────────────────────────────────
#
# Every other test in this file is deliberately version-AGNOSTIC: the v1 -> v2
# bump broke nine that spelled the version as a literal, and they were fixed by
# deriving it from the constant (16795c5). That is right for those tests, and
# it is exactly why the tests below pin TWO versions on purpose. A suite that
# derives the version everywhere cannot catch a disagreement about the version:
# the write path (constants.STARTER_KIT_VERSION) and the read path (the job
# record's facts.kit_version) only diverge across a bump, so a bump is the
# thing that has to be staged.


@pytest.fixture
def home(tmp_path, monkeypatch):
    """Isolated plugin home WITHOUT pinning a kit version.

    The `cdn` fixture bakes constants.STARTER_KIT_VERSION at setup time, which
    is what makes it version-agnostic; these tests need to move the constant
    mid-test, so they take the home here and serve the CDN via _serve().
    """
    monkeypatch.setattr(downloader, "DEFAULT_DEST", tmp_path / "home" / "kit-default")
    monkeypatch.setattr(config_store, "CONFIG_PATH", tmp_path / "home" / "ui_config.json")
    monkeypatch.setattr(jobs, "JOBS_DIR", tmp_path / "home" / "jobs")
    monkeypatch.setattr(jobs, "_jobs", {})


def _serve(tmp_path, monkeypatch, version: str) -> FakeCDN:
    """Ship `version`: build a synthetic kit for it and make it the constant."""
    monkeypatch.setattr(constants, "STARTER_KIT_VERSION", version)
    srv = tmp_path / f"srv-{version}"
    kit = _make_kit(srv)
    make_kit_manifest.generate(
        kit, srv / "cdn", "test-comp", version, shard_bytes=2048, created_utc=_CREATED,
    )
    fake = FakeCDN(srv / "cdn" / version)
    monkeypatch.setattr(downloader, "_open", fake.open)
    return fake


def test_recorded_version_behind_the_constant_is_superseded(home, tmp_path, monkeypatch):
    # The v1.2.11 bug: the record is complete and its dataset.yaml is on disk,
    # so download_state answered "success" forever and the UI kept rendering
    # the quiet "downloaded N ago" line. The participant was never told a newer
    # kit existed.
    _serve(tmp_path, monkeypatch, "v1")
    ctx = FakeCtx()
    result = downloader.run_download({"dest_dir": str(_dest(tmp_path))}, ctx)
    _write_record(ctx, result)
    assert downloader.download_state()["state"] == "success"

    monkeypatch.setattr(constants, "STARTER_KIT_VERSION", "v2")  # the bump

    state = downloader.download_state()
    assert state["state"] == "superseded"
    assert state["kit_version"] == "v1"
    assert state["current_version"] == "v2"
    # Served, not rebuilt client-side: the fragment renders this path verbatim.
    assert state["kit_dir"] == str(_dest(tmp_path) / "v1")
    assert state["dataset_yaml"] == result["dataset_yaml"]


def test_superseded_is_not_the_missing_kit_state(home, tmp_path, monkeypatch):
    # "stale" already means "kit no longer on disk". The two conditions need
    # different names or the UI cannot tell a superseded kit from a gone one.
    _serve(tmp_path, monkeypatch, "v1")
    ctx = FakeCtx()
    result = downloader.run_download({"dest_dir": str(_dest(tmp_path))}, ctx)
    _write_record(ctx, result)
    monkeypatch.setattr(constants, "STARTER_KIT_VERSION", "v2")
    assert downloader.download_state()["state"] == "superseded"

    Path(result["dataset_yaml"]).unlink()
    assert downloader.download_state()["state"] == "stale"


def test_superseded_kit_still_verifies_against_its_own_manifest(home, tmp_path, monkeypatch):
    # Verify must keep working for exactly the population this release is for.
    # The manifest beside the v1 tree IS v1's, so the check is honest.
    _serve(tmp_path, monkeypatch, "v1")
    ctx = FakeCtx()
    result = downloader.run_download({"dest_dir": str(_dest(tmp_path))}, ctx)
    _write_record(ctx, result)
    monkeypatch.setattr(constants, "STARTER_KIT_VERSION", "v2")

    v = downloader.verify_now()
    assert v["ok"] is True
    assert v["matched"] == result["file_count"]
    # The denominator the fragment renders; unread before v1.2.12 (F10).
    assert v["file_count"] == result["file_count"]


def test_record_without_a_recorded_version_does_not_probe_the_current_one(
    home, tmp_path, monkeypatch
):
    # The bug in miniature: with no recorded version, verify_now used to fall
    # back to the CURRENT constant and report the manifest missing under v2/
    # while a perfectly good v1 kit sat beside it. Say so instead of guessing.
    #
    # A pre-v1.2.12 record carries NEITHER fact - it predates kit_version and
    # predates kit_dir. Dropping only one of them models no release that ever
    # shipped, and (since v1.2.13 records kit_dir) would leave the directory
    # perfectly well known.
    _serve(tmp_path, monkeypatch, "v1")
    ctx = FakeCtx()
    result = downloader.run_download({"dest_dir": str(_dest(tmp_path))}, ctx)
    ctx.facts.pop("kit_version")
    ctx.facts.pop("kit_dir")
    _write_record(ctx, result)
    monkeypatch.setattr(constants, "STARTER_KIT_VERSION", "v2")

    v = downloader.verify_now()
    assert v["ok"] is False
    assert "predates" in v["error"]
    assert "v2" not in v["error"]  # never names a directory it only guessed


def test_recorded_kit_dir_is_read_not_derived(home, tmp_path, monkeypatch):
    """The v1.2.13 fact, and the reason it exists: after an in-place top-up the
    directory no longer equals dest/<version>, so a derived path names a
    directory that does not exist while a good kit sits next door."""
    _serve(tmp_path, monkeypatch, "v1")
    ctx = FakeCtx()
    result = downloader.run_download({"dest_dir": str(_dest(tmp_path))}, ctx)
    _write_record(ctx, result)

    # The topped-up shape: v3 content, still in the v1 directory.
    stamped = dict(ctx.facts)
    stamped["kit_version"] = "v3"
    assert downloader.kit_dir_of(stamped) == str(_dest(tmp_path) / "v1")
    assert downloader.kit_dir_of(stamped) != str(_dest(tmp_path) / "v3")

    # Derivation survives only for records written before kit_dir existed.
    legacy = {"dest_dir": str(_dest(tmp_path)), "kit_version": "v1"}
    assert downloader.kit_dir_of(legacy) == str(_dest(tmp_path) / "v1")
    assert downloader.kit_dir_of({"dest_dir": str(_dest(tmp_path))}) == ""
    assert downloader.kit_dir_of({}) == ""


def test_verify_works_when_only_the_version_fact_is_missing(
    home, tmp_path, monkeypatch
):
    """kit_dir alone is enough: the directory is known even when the version is
    not, so Verify runs instead of refusing. This is the half of the old guard
    that was collateral, not the point of it."""
    _serve(tmp_path, monkeypatch, "v1")
    ctx = FakeCtx()
    result = downloader.run_download({"dest_dir": str(_dest(tmp_path))}, ctx)
    ctx.facts.pop("kit_version")
    _write_record(ctx, result)
    monkeypatch.setattr(constants, "STARTER_KIT_VERSION", "v2")

    v = downloader.verify_now()
    assert v["ok"] is True
    assert v["matched"] == v["file_count"]


def test_manifest_version_disagreeing_with_the_constant_is_refused(
    home, tmp_path, monkeypatch
):
    # Staging error: published under the v1 prefix, manifest says v2. Before
    # v1.2.12 this downloaded and verified green, the disagreement visible only
    # in a check-detail line nothing compared.
    fake = _serve(tmp_path, monkeypatch, "v1")
    manifest = json.loads((fake.dir / "manifest.json").read_text(encoding="utf-8"))
    manifest["kit_version"] = "v2"
    fake.tamper["manifest.json"] = json.dumps(manifest).encode("utf-8")

    with pytest.raises(RuntimeError, match="v2"):
        downloader.run_download({"dest_dir": str(_dest(tmp_path))}, FakeCtx())


# ── In-place top-up (v1.2.13) ───────────────────────────────────────────
#
# The population this exists for: a holder whose Tables already resolve through
# the dataset.yaml in an OLD version directory. v1.2.12 made them informed; a
# fresh download makes the new kit merely present, in a directory nothing reads.
# Only writing into the directory they already read reaches them.


def _serve_next(tmp_path, monkeypatch, version: str, mutate=None) -> FakeCDN:
    """Ship `version`, optionally mutating the kit tree before it is sharded.

    `mutate(kit_dir)` runs on the built tree, so a test can express "the next
    kit changes README.md" or "drops a label file" as the edit it actually is.
    """
    monkeypatch.setattr(constants, "STARTER_KIT_VERSION", version)
    srv = tmp_path / f"srv-{version}"
    kit = _make_kit(srv)
    if mutate is not None:
        mutate(kit)
    make_kit_manifest.generate(
        kit, srv / "cdn", "test-comp", version, shard_bytes=2048, created_utc=_CREATED,
    )
    fake = FakeCDN(srv / "cdn" / version)
    monkeypatch.setattr(downloader, "_open", fake.open)
    return fake


def _hold_v1(tmp_path, monkeypatch):
    """A completed v1 download on disk, with its record written."""
    _serve(tmp_path, monkeypatch, "v1")
    ctx = FakeCtx()
    result = downloader.run_download({"dest_dir": str(_dest(tmp_path))}, ctx)
    _write_record(ctx, result)
    return ctx, result


def _bump_readme(kit: Path) -> None:
    kit.joinpath("README.md").write_bytes(b"# kit\n\nThe Loop, not Tips & Tricks.\n")


def test_top_up_updates_in_place_and_restamps(home, tmp_path, monkeypatch):
    _hold_v1(tmp_path, monkeypatch)
    v1_dir = _dest(tmp_path) / "v1"
    assert downloader.download_state()["state"] == "success"

    fake = _serve_next(tmp_path, monkeypatch, "v2", _bump_readme)
    assert downloader.download_state()["state"] == "superseded"

    ctx = FakeCtx()
    result = downloader.run_download({"mode": "top_up"}, ctx)

    # The whole point: same directory, new content.
    assert result["updated"] is True
    assert result["kit_dir"] == str(v1_dir)
    assert result["from_version"] == "v1" and result["kit_version"] == "v2"
    assert (v1_dir / "starter_kit" / "README.md").read_bytes().endswith(
        b"The Loop, not Tips & Tricks.\n"
    )
    assert not (_dest(tmp_path) / "v2").exists()  # nothing landed alongside

    # Restamped: the record now says v2 while still naming the v1 directory,
    # which is exactly the shape kit_dir_of() exists to survive.
    _write_record(ctx, result)
    state = downloader.download_state()
    assert state["state"] == "success"
    assert state["kit_version"] == "v2"
    assert state["kit_dir"] == str(v1_dir)
    assert downloader.verify_now()["ok"] is True

    # And the manifest beside the tree was restamped too.
    beside = json.loads((v1_dir / "manifest.json").read_text(encoding="utf-8"))
    assert beside["kit_version"] == "v2"
    assert not list(v1_dir.glob("*.zip"))  # shards cleaned up


def test_top_up_fetches_only_the_shards_the_delta_needs(home, tmp_path, monkeypatch):
    _hold_v1(tmp_path, monkeypatch)
    fake = _serve_next(tmp_path, monkeypatch, "v2", _bump_readme)
    fake.requests.clear()

    result = downloader.run_download({"mode": "top_up"}, FakeCtx())

    fetched = {n for n, _ in fake.requests if n != "manifest.json"}
    assert result["fetched_archives"] == 1
    assert len(fetched) == 1
    # README.md is a root file, so it rides the root-labels shard; the image
    # shards are byte-identical and must never cross the wire.
    assert all("images" not in n for n in fetched)
    assert result["written_files"] == 1


def test_top_up_removes_kit_files_but_never_the_participants(home, tmp_path, monkeypatch):
    _hold_v1(tmp_path, monkeypatch)
    v1_kit = _dest(tmp_path) / "v1" / "starter_kit"

    # The participant's own work, sitting in the kit tree.
    mine = v1_kit / "labels" / "train" / "my_notes.txt"
    mine.write_bytes(b"my own file\n")

    def drop_a_label(kit: Path) -> None:
        _bump_readme(kit)
        kit.joinpath("labels", "train", "a.txt").unlink()

    _serve_next(tmp_path, monkeypatch, "v2", drop_a_label)
    result = downloader.run_download({"mode": "top_up"}, FakeCtx())

    assert result["removed_files"] == 1
    assert not (v1_kit / "labels" / "train" / "a.txt").exists()  # kit dropped it
    assert mine.read_bytes() == b"my own file\n"                 # never touched


def test_top_up_without_a_manifest_beside_the_kit_removes_nothing(
    home, tmp_path, monkeypatch
):
    """Without the old manifest there is no way to tell a file the kit dropped
    from a file the participant added, so the safe half is chosen and said."""
    _hold_v1(tmp_path, monkeypatch)
    v1_dir = _dest(tmp_path) / "v1"
    (v1_dir / "manifest.json").unlink()

    def drop_a_label(kit: Path) -> None:
        _bump_readme(kit)
        kit.joinpath("labels", "train", "a.txt").unlink()

    _serve_next(tmp_path, monkeypatch, "v2", drop_a_label)
    ctx = FakeCtx()
    result = downloader.run_download({"mode": "top_up"}, ctx)

    assert result["removed_files"] == 0
    assert (v1_dir / "starter_kit" / "labels" / "train" / "a.txt").exists()
    assert any("removals could not be determined" in c["label"] for c in ctx.checks)


def test_top_up_refuses_a_dataset_yaml_that_changes_load_bearing_keys(
    home, tmp_path, monkeypatch
):
    """SYNTHETIC BY NECESSITY. The real v2 -> v3 changes README.md only, so no
    live upgrade can exercise this gate - and it is the one branch where being
    wrong silently re-points data the participant has already imported. The
    refusal has to be proven against a kit built to trip it."""
    _hold_v1(tmp_path, monkeypatch)
    v1_dir = _dest(tmp_path) / "v1"
    before_readme = (v1_dir / "starter_kit" / "README.md").read_bytes()

    def repoint(kit: Path) -> None:
        kit.joinpath("dataset.yaml").write_bytes(b"path: ../elsewhere\nnc: 11\n")

    _serve_next(tmp_path, monkeypatch, "v2", repoint)
    ctx = FakeCtx()
    with pytest.raises(RuntimeError) as exc:
        downloader.run_download({"mode": "top_up"}, ctx)

    assert "already imported" in str(exc.value)
    assert "path" in str(exc.value) and "nc" in str(exc.value)
    assert "unchanged" in str(exc.value)

    # "The kit on disk is unchanged" has to be true, not just claimed.
    assert (v1_dir / "starter_kit" / "dataset.yaml").read_bytes() == b"path: .\nnc: 12\n"
    assert (v1_dir / "starter_kit" / "README.md").read_bytes() == before_readme
    beside = json.loads((v1_dir / "manifest.json").read_text(encoding="utf-8"))
    assert beside["kit_version"] == "v1"  # not restamped on a refusal
    assert downloader.download_state()["kit_version"] == "v1"


def test_top_up_allows_a_dataset_yaml_that_only_changes_comments(
    home, tmp_path, monkeypatch
):
    """The gate compares parsed values, not the hash: a comment-only rewrite is
    a real case (the v2 kit did exactly that) and must not be refused."""
    _hold_v1(tmp_path, monkeypatch)
    v1_dir = _dest(tmp_path) / "v1"

    def recomment(kit: Path) -> None:
        kit.joinpath("dataset.yaml").write_bytes(
            b"# Keep this file at the kit root.\npath: .\nnc: 12\n"
        )

    _serve_next(tmp_path, monkeypatch, "v2", recomment)
    ctx = FakeCtx()
    result = downloader.run_download({"mode": "top_up"}, ctx)

    assert result["updated"] is True
    assert (v1_dir / "starter_kit" / "dataset.yaml").read_bytes().startswith(b"# Keep")
    assert any(
        c["label"] == "dataset.yaml keeps its load-bearing keys" and c["ok"]
        for c in ctx.checks
    )


def test_top_up_repairs_a_locally_damaged_file(home, tmp_path, monkeypatch):
    """The delta is against the tree as it IS, not against the old manifest, so
    a file corrupted locally is repaired by the same pass that updates."""
    _hold_v1(tmp_path, monkeypatch)
    v1_kit = _dest(tmp_path) / "v1" / "starter_kit"
    (v1_kit / "labels" / "train" / "a.txt").write_bytes(b"corrupted\n")

    _serve_next(tmp_path, monkeypatch, "v2", _bump_readme)
    result = downloader.run_download({"mode": "top_up"}, FakeCtx())

    assert result["updated"] is True
    assert (v1_kit / "labels" / "train" / "a.txt").read_bytes() == b"0 0.5 0.5 0.1 0.1\n"
    assert result["written_files"] == 2  # the README bump AND the repair


def test_top_up_on_a_current_kit_does_nothing(home, tmp_path, monkeypatch):
    _hold_v1(tmp_path, monkeypatch)
    result = downloader.run_download({"mode": "top_up"}, FakeCtx())
    assert result["updated"] is False
    assert result["reason"] == "already current"


def test_top_up_with_no_kit_on_record_says_so(home, tmp_path, monkeypatch):
    _serve(tmp_path, monkeypatch, "v1")
    with pytest.raises(RuntimeError, match="Download the starter kit first"):
        downloader.run_download({"mode": "top_up"}, FakeCtx())


def test_top_up_leaves_the_old_manifest_until_it_succeeds(home, tmp_path, monkeypatch):
    """fetch_manifest(persist=False) is load-bearing: a manifest written before
    the tree matches it would make Verify report mass mismatch on an intact kit."""
    _hold_v1(tmp_path, monkeypatch)
    v1_dir = _dest(tmp_path) / "v1"

    fake = _serve_next(tmp_path, monkeypatch, "v2", _bump_readme)
    # Corrupt the shard the delta needs, so the pass fails after the manifest
    # has been fetched but before the tree is consistent.
    name = next(
        n for n in (a["name"] for a in json.loads(
            (fake.dir / "manifest.json").read_text(encoding="utf-8"))["archives"])
        if "root-labels" in n
    )
    fake.tamper[name] = b"not a zip"

    with pytest.raises(RuntimeError):
        downloader.run_download({"mode": "top_up"}, FakeCtx())

    beside = json.loads((v1_dir / "manifest.json").read_text(encoding="utf-8"))
    assert beside["kit_version"] == "v1"
    assert downloader.verify_now()["ok"] is True  # the v1 kit still verifies
