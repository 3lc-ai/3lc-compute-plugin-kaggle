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

from tlc_plugin_kaggle import config_store, predictor

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE_SLUG = "fixture-competition-slug-test"


@pytest.fixture
def store(tmp_path, monkeypatch):
    """config_store pointed at an isolated file, with the shipped slug
    pinned to the fixtures' sanitized value — so "persisted slug equals the
    shipped constant" behaves exactly like the real configs the fixtures
    were taken from (both carried the then-current test slug)."""
    monkeypatch.setattr(config_store, "CONFIG_PATH", tmp_path / "ui_config.json")
    monkeypatch.setattr(predictor, "COMPETITION_SLUG", FIXTURE_SLUG)
    return config_store


def fixture_config(name: str, root: Path) -> dict:
    text = (FIXTURES / f"ui_config.{name}.json").read_text(encoding="utf-8")
    text = text.replace("<FIXTURE_ROOT>", root.as_posix())
    return json.loads(text)


def write_config(store, data: dict) -> None:
    store.CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    store.CONFIG_PATH.write_text(json.dumps(data, indent=1), encoding="utf-8")


def materialize_tables(cfg: dict) -> None:
    for entry in (cfg.get("import_state", {}).get("tables") or {}).values():
        Path(entry["url"]).mkdir(parents=True, exist_ok=True)
