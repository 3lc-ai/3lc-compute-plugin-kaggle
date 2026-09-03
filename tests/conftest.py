"""Shared plumbing for the pytest layer (v1.2.6 session refactor).

The migration fixtures are the two REAL ui_config.json files from the dev
machine (July 0.1.x home / current v1.2.5 home), sanitized: every
C:\\Users\\Owner path prefix is the literal token <FIXTURE_ROOT>
(substituted with tmp_path at test time, separator style preserved), the
competition slug is a fixture value, and Kaggle submission refs are zeroed
(account-linked identifiers). Tests that need import_state's table URLs to
"resolve on disk" create the directories under tmp_path first — the URLs
are directories in the real 3LC layout.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

# The package __init__ imports the SDK only to define the KagglePlugin
# entrypoint class; every module under test is stdlib-only at import time.
# When the SDK isn't installed (plain pytest venv), a two-name stub lets the
# package import — the stub is never exercised. A real installed SDK wins.
try:
    import tlc_plugin_sdk  # noqa: F401
except ModuleNotFoundError:
    _stub = types.ModuleType("tlc_plugin_sdk")
    _stub.ComputePlugin = type("ComputePlugin", (), {})
    _stub.JobContext = type("JobContext", (), {})
    sys.modules["tlc_plugin_sdk"] = _stub

from tlc_plugin_kaggle import config_store, constants

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE_SLUG = "fixture-competition-slug-test"


@pytest.fixture
def store(tmp_path, monkeypatch):
    """config_store pointed at an isolated file, with the shipped slug
    pinned to the fixtures' sanitized value — so "persisted slug equals the
    shipped constant" behaves exactly like the real configs the fixtures
    were taken from (both carried the then-current test slug)."""
    monkeypatch.setattr(config_store, "CONFIG_PATH", tmp_path / "ui_config.json")
    monkeypatch.setattr(constants, "COMPETITION_SLUG", FIXTURE_SLUG)
    return config_store


# ── Project-root shapes (v1.2.10) ────────────────────────────────────────
# Every captured fixture was taken from a machine on the DEFAULT project
# root, whose path ends in ".../3LC/3LC/projects". That made the whole suite
# blind to two root-dependent bugs for nine releases: _project_root_url
# always returned the default root, and url_project required a literal
# "/projects/" segment. Tests that care about the root parametrize over
# these three shapes, which fail differently:
#
#   default   — the shipped layout; the no-regression guard.
#   relocated — moved, but still ends in "projects" (breaks root resolution
#               only: the URL still parses).
#   bare      — like "D:/3lc-data": no "projects" segment anywhere (breaks
#               root resolution AND the URL parse).
#
# The value is the path tail that replaces the default root's tail; None
# means "leave the fixture exactly as captured".
ROOT_SHAPES = {
    "default": None,
    "relocated": "relocated/projects",
    "bare": "3lc-data",
}

_DEFAULT_ROOT_TAIL = "/AppData/Local/3LC/3LC/projects/"


@pytest.fixture(params=sorted(ROOT_SHAPES))
def root_shape(request):
    """The three root shapes, by name. Pass to fixture_config(projects_tail=)
    or resolve with project_root(tmp_path, shape)."""
    return request.param


def project_root(root: Path, shape: str) -> str:
    """The project root a given shape resolves to, under a tmp_path."""
    tail = ROOT_SHAPES[shape]
    if tail is None:
        return (root / "AppData/Local/3LC/3LC/projects").as_posix()
    return (root / tail).as_posix()


def fixture_config(name: str, root: Path, projects_tail: str | None = None) -> dict:
    """One captured config, rehomed under `root`.

    projects_tail replaces the default root's ".../3LC/3LC/projects" tail, so
    the same real fixture can be replayed under a relocated or bare root
    without a second copy of the file on disk.
    """
    text = (FIXTURES / f"ui_config.{name}.json").read_text(encoding="utf-8")
    text = text.replace("<FIXTURE_ROOT>", root.as_posix())
    if projects_tail is not None:
        assert _DEFAULT_ROOT_TAIL in text, f"fixture {name} no longer carries the default root tail"
        text = text.replace(_DEFAULT_ROOT_TAIL, f"/{projects_tail}/")
    return json.loads(text)


def write_config(store, data: dict) -> None:
    store.CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    store.CONFIG_PATH.write_text(json.dumps(data, indent=1), encoding="utf-8")


def materialize_tables(cfg: dict) -> None:
    for entry in (cfg.get("import_state", {}).get("tables") or {}).values():
        Path(entry["url"]).mkdir(parents=True, exist_ok=True)


# ── A stand-in for tlc (v1.2.10) ─────────────────────────────────────────
# The suite never imports real tlc: it wants an activated API key and drags
# in torch, which is the whole reason the plugin defers that import. So the
# code paths that run THROUGH tlc — root resolution, the URL builder, the
# import reuse gates — had no coverage at all, and that is where the
# wrong-project-root bug lived. This shim covers only what importer.py
# touches, and deliberately reproduces the two behaviors the real SDK has
# that the bug depended on: Url normalizes separators, and the writers lay
# tables out under the CONFIGURED project root (so a test can catch
# _table_url disagreeing with where an import actually landed).


class FakeUrl:
    """tlc.Url: joins with /, normalizes separators, answers exists()."""

    def __init__(self, value):
        self._v = str(value).replace("\\", "/").rstrip("/")

    def __truediv__(self, other):
        return FakeUrl(f"{self._v}/{other}")

    def __str__(self):
        return self._v

    def __repr__(self):
        return f"FakeUrl({self._v!r})"

    def __eq__(self, other):
        return str(self) == str(other)

    def __hash__(self):
        return hash(self._v)

    def exists(self):
        return Path(self._v).exists()


class FakeTable:
    def __init__(self, url, row_count=0, inputs=(), rows=None, value_map=None):
        self.url = FakeUrl(url)
        self.row_count = row_count
        self.input_tables = [FakeUrl(i) for i in inputs]
        self.table_rows = rows if rows is not None else []
        self._value_map = value_map or {}

    def latest(self):
        return self

    def get_value_map(self, _column):
        return self._value_map


@pytest.fixture
def tlc_stub(monkeypatch):
    """A fake `tlc` module in sys.modules, scoped to the test.

    Set the root with ``tlc_stub.config.project_root_url = ...``; inspect
    what the import path did with ``tlc_stub.calls``.
    """
    mod = types.ModuleType("tlc")
    mod.calls = []
    mod.config = types.SimpleNamespace(project_root_url="")
    mod.Url = FakeUrl
    mod.schemas = types.SimpleNamespace(ImageSchema=lambda *a, **k: {"kind": "image"})

    def _canonical(dataset_name, table_name):
        root = str(mod.config.project_root_url)
        project = mod.project_name
        return FakeUrl(f"{root}/{project}/datasets/{dataset_name}/tables/{table_name}")

    def _write(url, if_exists, row_count):
        path = Path(str(url))
        if path.exists() and if_exists == "raise":
            raise FileExistsError(f"table already exists: {url}")
        path.mkdir(parents=True, exist_ok=True)
        return FakeTable(url, row_count=row_count)

    class Table:
        @staticmethod
        def from_yolo_url(images_url, **kwargs):
            mod.calls.append(("from_yolo_url", {"images_url": str(images_url), **kwargs}))
            mod.project_name = kwargs["project_name"]
            url = _canonical(kwargs["dataset_name"], kwargs["table_name"])
            return _write(url, kwargs.get("if_exists"), mod.row_count)

        @staticmethod
        def from_url(url):
            mod.calls.append(("from_url", {"url": str(url)}))
            return FakeTable(url, row_count=mod.row_count)

    class TableWriter:
        def __init__(self, **kwargs):
            mod.calls.append(("TableWriter", dict(kwargs)))
            mod.project_name = kwargs["project_name"]
            self._kwargs = kwargs
            self._rows = []

        def add_row(self, row):
            self._rows.append(row)

        def finalize(self):
            url = _canonical(self._kwargs["dataset_name"], self._kwargs["table_name"])
            return _write(url, self._kwargs.get("if_exists"), len(self._rows))

    mod.project_name = ""
    mod.row_count = 0
    mod.Table = Table
    mod.TableWriter = TableWriter
    monkeypatch.setitem(sys.modules, "tlc", mod)
    return mod
