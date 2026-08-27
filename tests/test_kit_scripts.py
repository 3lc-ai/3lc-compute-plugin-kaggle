"""Tests for scripts/make_kit_manifest.py and scripts/check_kit_parity.py.

Built around a small synthetic kit (same shape as the real one: dataset.yaml
and README at the root, labels/, images/{train,val,test}) with a tiny shard
budget so images/train splits into several parts - every property the real
616 MB generation relies on is exercised in milliseconds.
"""

from __future__ import annotations

import hashlib
import json
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import check_kit_parity  # noqa: E402
import make_kit_manifest  # noqa: E402

_CREATED = "2026-01-01T00:00:00Z"  # pinned so manifests are comparable


def _make_kit(root: Path) -> Path:
    kit = root / "starter_kit"
    (kit / "labels" / "train").mkdir(parents=True)
    (kit / "images" / "train").mkdir(parents=True)
    (kit / "images" / "val").mkdir(parents=True)
    (kit / "images" / "test").mkdir(parents=True)
    (kit / "dataset.yaml").write_bytes(b"path: .\nnc: 12\n")
    (kit / "README.md").write_bytes(b"# kit\n")
    (kit / "labels" / "train" / "a.txt").write_bytes(b"0 0.5 0.5 0.1 0.1\n")
    for i in range(6):
        # ~1 KB each, deterministic content; .jpg so the stored-not-deflated
        # branch is exercised
        (kit / "images" / "train" / f"img_{i}.jpg").write_bytes(
            bytes([i]) * 1024)
    (kit / "images" / "val" / "v.jpg").write_bytes(b"\xfe" * 512)
    (kit / "images" / "test" / "t.jpg").write_bytes(b"\xfd" * 512)
    return kit


def _generate(kit: Path, out: Path, shard_bytes: int = 2048) -> dict:
    return make_kit_manifest.generate(
        kit, out, "test-comp", "v1",
        shard_bytes=shard_bytes, created_utc=_CREATED)


@pytest.fixture
def kit(tmp_path):
    return _make_kit(tmp_path)


def test_manifest_lists_every_file_with_true_hashes(kit, tmp_path):
    manifest = _generate(kit, tmp_path / "out")
    on_disk = {p for p in kit.rglob("*") if p.is_file()}
    assert manifest["file_count"] == len(on_disk)
    assert manifest["total_bytes"] == sum(p.stat().st_size for p in on_disk)
    assert manifest["kit_dir_name"] == "starter_kit"
    by_path = {f["path"]: f for f in manifest["files"]}
    for path in on_disk:
        entry = by_path[f"starter_kit/{path.relative_to(kit).as_posix()}"]
        data = path.read_bytes()
        assert entry["bytes"] == len(data)
        assert entry["sha256"] == hashlib.sha256(data).hexdigest()
    # every file's archive assignment names a real archive
    archive_names = {a["name"] for a in manifest["archives"]}
    assert {f["archive"] for f in manifest["files"]} == archive_names
    # archive hashes are true hashes of the written zips
    out = tmp_path / "out" / "v1"
    for a in manifest["archives"]:
        digest = hashlib.sha256((out / a["name"]).read_bytes()).hexdigest()
        assert digest == a["sha256"]


def test_generation_is_deterministic(kit, tmp_path):
    m1 = _generate(kit, tmp_path / "out1")
    m2 = _generate(kit, tmp_path / "out2")
    assert m1 == m2
    for a in m1["archives"]:
        b1 = (tmp_path / "out1" / "v1" / a["name"]).read_bytes()
        b2 = (tmp_path / "out2" / "v1" / a["name"]).read_bytes()
        assert b1 == b2, a["name"]


def test_large_group_splits_and_small_groups_do_not(kit, tmp_path):
    manifest = _generate(kit, tmp_path / "out", shard_bytes=2048)
    groups = {}
    for a in manifest["archives"]:
        group = a["name"].split("-", 2)[2].rsplit(".", 1)[0].rstrip("0123456789").rstrip("-")
        groups.setdefault(group, []).append(a)
    # 6 x 1 KB train images with a 2 KB budget -> 3 shards
    assert len(groups["images-train"]) == 3
    assert len(groups["images-val"]) == 1
    assert len(groups["images-test"]) == 1
    assert len(groups["root-labels"]) == 1
    # no shard (except possibly a single-file one) exceeds the budget by
    # more than one file; here all inputs are under budget individually
    for a in manifest["archives"]:
        assert a["file_count"] >= 1


def test_extracting_all_shards_reproduces_the_tree(kit, tmp_path):
    _generate(kit, tmp_path / "out")
    extracted = tmp_path / "extracted"
    for part in sorted((tmp_path / "out" / "v1").glob("part-*.zip")):
        with zipfile.ZipFile(part) as zf:
            zf.extractall(extracted)
    original = {
        p.relative_to(kit).as_posix(): p.read_bytes()
        for p in kit.rglob("*") if p.is_file()
    }
    restored_root = extracted / "starter_kit"
    restored = {
        p.relative_to(restored_root).as_posix(): p.read_bytes()
        for p in restored_root.rglob("*") if p.is_file()
    }
    assert restored == original


def test_refuses_to_write_over_foreign_content(kit, tmp_path):
    out = tmp_path / "out"
    (out / "v1").mkdir(parents=True)
    (out / "v1" / "unrelated.txt").write_text("x")
    with pytest.raises(SystemExit):
        _generate(kit, out)


def _manifest_path(out: Path) -> Path:
    return out / "v1" / "manifest.json"


def test_parity_passes_on_extracted_tree_and_kit_root_alike(kit, tmp_path):
    _generate(kit, tmp_path / "out")
    manifest = _manifest_path(tmp_path / "out")
    # parent dir (contains starter_kit/)
    report = check_kit_parity.check(manifest, target_dir=kit.parent)
    assert check_kit_parity.is_parity(report)
    assert report["matched"] == json.loads(manifest.read_text())["file_count"]
    # the kit dir itself
    report2 = check_kit_parity.check(manifest, target_dir=kit)
    assert check_kit_parity.is_parity(report2)


def test_parity_reports_each_delta_by_name(kit, tmp_path):
    _generate(kit, tmp_path / "out")
    manifest = _manifest_path(tmp_path / "out")
    # mutate: change content (same size), remove one, add one, resize one
    (kit / "dataset.yaml").write_bytes(b"path: X\nnc: 12\n")  # same length
    (kit / "images" / "val" / "v.jpg").unlink()
    (kit / "train_first.py").write_bytes(b"print('stale')\n")
    (kit / "README.md").write_bytes(b"# kit, but longer now\n")

    report = check_kit_parity.check(manifest, target_dir=kit.parent)
    assert not check_kit_parity.is_parity(report)
    assert report["sha_mismatch"] == ["starter_kit/dataset.yaml"]
    assert report["missing"] == ["starter_kit/images/val/v.jpg"]
    assert [e.split(" ")[0] for e in report["extra"]] == [
        "starter_kit/train_first.py"]
    assert [e.split(" ")[0] for e in report["size_mismatch"]] == [
        "starter_kit/README.md"]


def test_parity_zip_mode_matches_and_reports_extras(kit, tmp_path):
    _generate(kit, tmp_path / "out")
    manifest = _manifest_path(tmp_path / "out")

    def bundle(dest: Path, extra: bool) -> Path:
        with zipfile.ZipFile(dest, "w") as zf:
            for p in sorted(kit.rglob("*")):
                if p.is_file():
                    zf.write(p, f"starter_kit/{p.relative_to(kit).as_posix()}")
            if extra:
                zf.writestr("starter_kit/verify_setup.py", "print('x')\n")
        return dest

    clean = bundle(tmp_path / "clean.zip", extra=False)
    report = check_kit_parity.check(manifest, target_zip=clean)
    assert check_kit_parity.is_parity(report)

    dirty = bundle(tmp_path / "dirty.zip", extra=True)
    report = check_kit_parity.check(manifest, target_zip=dirty)
    assert not check_kit_parity.is_parity(report)
    assert [e.split(" ")[0] for e in report["extra"]] == [
        "starter_kit/verify_setup.py"]
    assert report["matched"] == json.loads(manifest.read_text())["file_count"]


def test_cli_exit_codes(kit, tmp_path, capsys):
    _generate(kit, tmp_path / "out")
    manifest = _manifest_path(tmp_path / "out")
    assert check_kit_parity.main(
        ["--manifest", str(manifest), "--dir", str(kit.parent)]) == 0
    out = capsys.readouterr().out
    assert "RESULT: PARITY" in out
    (kit / "extra.bin").write_bytes(b"\x00")
    assert check_kit_parity.main(
        ["--manifest", str(manifest), "--dir", str(kit.parent)]) == 1
    out = capsys.readouterr().out
    assert "RESULT: DELTA" in out
    assert "starter_kit/extra.bin" in out
