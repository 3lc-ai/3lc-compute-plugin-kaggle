# Copyright 2026 3LC Inc.
# SPDX-License-Identifier: AGPL-3.0-only
"""Packaging invariants: the version strings agree, and the wheel is complete.

Both bugs that prompted this file hid behind an editable install, where the
distribution's own metadata is never built and never read back. Every other
test here imports straight from ``src/``; this one builds the real wheel and
asserts against the artifact.

The version fact this pins: ``__init__._read_version()`` reads
``importlib.metadata`` (i.e. pyproject, at BUILD time) and falls back to
plugin.toml, while the 0.2.x host reads plugin.toml directly for the manifest.
Those are two sources for one fact, so a divergence shows the Hub one version
and the fragment footer another - and the footer is what tester diagnostics
carry. v1.2.3 already shipped a v1.2.2 footer from the neighbouring mistake.

DELIBERATELY NOT ASSERTED: that catalog.json's newest entry equals the shipped
version. RELEASING.md orders tag -> catalog and this suite runs BEFORE the tag,
so at test time the catalog legitimately still holds the previous release;
asserting equality would fail every release. That pairing stays a PRETAG step.
What IS asserted is the catalog's internal consistency, which is where the real
release-time errors have actually landed (a hand-paste that introduced a
duplicate key; a manifest block disagreeing with its own entry).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DIST_NAME = "3lc-compute-plugin-kaggle"
IMPORT_NAME = "tlc_plugin_kaggle"


def _pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def _plugin_toml() -> dict:
    return tomllib.loads(
        (ROOT / "src" / IMPORT_NAME / "plugin.toml").read_text(encoding="utf-8")
    )


def _catalog() -> dict:
    return json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def wheel(tmp_path_factory) -> Path:
    """The real wheel, built with hatchling directly.

    Not ``python -m build``: that spins up an isolated env and fetches the
    backend over the network. hatchling is a dev-group dependency precisely so
    this stays offline and fast.
    """
    out = tmp_path_factory.mktemp("dist")
    proc = subprocess.run(
        [sys.executable, "-m", "hatchling", "build", "-t", "wheel", "-d", str(out)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"wheel build failed:\n{proc.stdout}\n{proc.stderr}"
    wheels = list(out.glob("*.whl"))
    assert len(wheels) == 1, f"expected exactly one wheel, got {wheels}"
    return wheels[0]


def test_the_four_version_strings_agree(wheel):
    """pyproject, its legacy-host mirror, plugin.toml, and the built metadata.

    plugin.toml is what the 0.2.x host shows in the plugin list; the wheel's
    metadata is what ``importlib.metadata`` gives the footer and diagnostics.
    """
    py = _pyproject()
    versions = {
        "pyproject [project]": py["project"]["version"],
        "pyproject [tool.tlc-compute]": py["tool"]["tlc-compute"]["version"],
        "plugin.toml": _plugin_toml()["version"],
    }

    with zipfile.ZipFile(wheel) as zf:
        meta = next(n for n in zf.namelist() if n.endswith(".dist-info/METADATA"))
        text = zf.read(meta).decode("utf-8")
    match = re.search(r"^Version: (.+)$", text, re.M)
    assert match, "built wheel has no Version in its METADATA"
    versions["wheel METADATA"] = match.group(1).strip()

    assert len(set(versions.values())) == 1, f"version strings disagree: {versions}"


def test_wheel_carries_the_fragment_and_the_manifest(wheel):
    """ui.html and plugin.toml are data files, not modules.

    A packaging change that dropped either would leave the plugin importable
    and unusable: no UI to serve, and no manifest for the host to read.
    """
    with zipfile.ZipFile(wheel) as zf:
        names = set(zf.namelist())
        for required in (f"{IMPORT_NAME}/ui.html", f"{IMPORT_NAME}/plugin.toml"):
            assert required in names, f"{required} missing from the wheel"
        assert zf.getinfo(f"{IMPORT_NAME}/ui.html").file_size > 100_000


def test_catalog_entries_are_internally_consistent():
    """Per entry: version == manifest.version == the tag in its source URL."""
    catalog = _catalog()
    plugins = catalog["plugins"]
    assert len(plugins) == 1, "catalog carries more than one plugin block"
    for entry in plugins[0]["versions"]:
        version = entry["version"]
        assert entry["manifest"]["version"] == version, (
            f"catalog {version}: manifest.version is {entry['manifest']['version']}"
        )
        tag = re.search(r"@v([^\s@]+)$", entry["source"])
        assert tag, f"catalog {version}: source names no @vX.Y.Z tag"
        assert tag.group(1) == version, (
            f"catalog {version}: source points at v{tag.group(1)}"
        )


def test_catalog_ids_match_the_plugin_id():
    """RELEASING.md: the catalog id must equal the plugin id, or the host
    installs a plugin it then cannot resolve. Also the entry-point key."""
    plugin_id = _plugin_toml()["id"]
    plugins = _catalog()["plugins"]
    assert plugins[0]["id"] == plugin_id
    for entry in plugins[0]["versions"]:
        assert entry["manifest"]["id"] == plugin_id, (
            f"catalog {entry['version']}: manifest.id is {entry['manifest']['id']}"
        )
    entry_points = _pyproject()["project"]["entry-points"]["tlc_compute.plugins"]
    assert plugin_id in entry_points, "entry-point key must equal the plugin id"


def test_catalog_versions_are_unique_and_newest_first():
    """The duplicate-key class RELEASING.md warns about, plus the ordering the
    host's resolution and `.../HEAD/catalog.json` readers assume."""
    versions = [e["version"] for e in _catalog()["plugins"][0]["versions"]]
    assert len(versions) == len(set(versions)), f"duplicate catalog versions: {versions}"

    def key(v: str) -> tuple[int, ...]:
        return tuple(int(part) for part in v.split("."))

    assert versions == sorted(versions, key=key, reverse=True), (
        f"catalog entries are not newest-first: {versions}"
    )
