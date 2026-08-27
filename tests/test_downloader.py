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
        kit, tmp_path / "srv" / "cdn", "test-comp", "v1",
        shard_bytes=2048, created_utc=_CREATED,
    )
    fake = FakeCDN(tmp_path / "srv" / "cdn" / "v1")
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


def test_fresh_download_end_to_end(cdn, tmp_path):
    ctx = FakeCtx()
    result = downloader.run_download({"dest_dir": str(_dest(tmp_path))}, ctx)
    manifest = _manifest(cdn)

    assert result["cancelled"] is False
    assert result["file_count"] == manifest["file_count"]
    assert result["verified_files"] == manifest["file_count"]
    assert all(c["ok"] for c in ctx.checks)

    version_dir = _dest(tmp_path) / "v1"
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
    version_dir = _dest(tmp_path) / "v1"
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
    version_dir = _dest(tmp_path) / "v1"
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
    version_dir = _dest(tmp_path) / "v1"
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
    version_dir = _dest(tmp_path) / "v1"
    assert result["cancelled"] is True and result["resumable"] is True
    assert (version_dir / names[0]).is_file()  # kept for resume
    assert not (version_dir / "starter_kit").exists()  # never extracted
    assert not config_store.CONFIG_PATH.exists()  # session untouched


def test_extra_files_are_reported_not_fatal(cdn, tmp_path):
    downloader.run_download({"dest_dir": str(_dest(tmp_path))}, FakeCtx())
    extra = _dest(tmp_path) / "v1" / "starter_kit" / "my-notes.txt"
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
    assert (downloader.DEFAULT_DEST / "v1").is_dir()  # probed into existence

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
    version_dir = _dest(tmp_path) / "v1"
    assert len(list(version_dir.glob("part-*.zip"))) == len(manifest["archives"])


def test_download_state_reverifies_disk(cdn, tmp_path):
    assert downloader.download_state() == {"state": "empty"}

    ctx = FakeCtx()
    result = downloader.run_download({"dest_dir": str(_dest(tmp_path))}, ctx)
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

    state = downloader.download_state()
    assert state["state"] == "success"
    assert state["dataset_yaml"] == result["dataset_yaml"]
    assert state["file_count"] == result["file_count"]

    Path(result["dataset_yaml"]).unlink()
    assert downloader.download_state()["state"] == "stale"
