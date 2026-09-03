"""The project root as a first-class dimension (v1.2.10).

Gudbrand set a non-default ``project-root-url``: Import created tables
correctly, the Train tab autofilled paths under the DEFAULT root and gated
them red, and a hand-corrected path went green but did not survive a
reload. Two independent defects, both invisible on a default root:

  1. ``_project_root_url`` called ``ConfigStore.get(tlc_options.ROOT_URL)``
     — a string-keyed API handed an Option OBJECT. The miss was
     indistinguishable from "not set", so a truthiness fallback returned
     the default root on every host for nine releases.
  2. ``url_project`` (and its ui.html mirror) required a literal
     "/projects/" segment, which a root like "D:/3lc-data" does not have,
     so ``classify_override`` answered "drop" and the corrected URL was
     never stored.

Nine releases shipped both because every fixture in this suite hardcodes a
default-shaped root. So these tests parametrize over ``root_shape``
(conftest.ROOT_SHAPES): default / relocated-but-projects-shaped / bare. The
two non-default shapes fail differently — the relocated one only breaks
root resolution, the bare one also breaks the URL parse.

Scope note: tlc's own resolution of the five input forms (canonical
config key, the deprecated ``indexing.project-root-url`` spelling,
TLC_PROJECT_ROOT_URL, its deprecated alias, and --project-root-url) is
verified by probe in docs/PRETAG_1.2.10.md, not here. This suite never
imports real tlc (see conftest.tlc_stub), so a test of that would only be
a test of the stub. What IS pinned here is that the plugin reads the root
through the public accessor at all — see
test_plugin_reads_config_through_tlc_dot_config.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import project_root, write_config

from tlc_plugin_kaggle import config_store, importer

PROJECT = "exdark-competition"
CLASSES = list(importer.CANONICAL_CLASSES)


@pytest.fixture
def rooted(tlc_stub, tmp_path, root_shape):
    """The tlc stub pointed at this shape's project root."""
    tlc_stub.config.project_root_url = project_root(tmp_path, root_shape)
    return tlc_stub


def make_split(tmp_path: Path, split: str, n_images: int = 2, labels: bool = False) -> Path:
    """A YOLO split on disk: <kit>/images/<split> (+ <kit>/labels/<split>)."""
    images = tmp_path / "kit" / "images" / split
    images.mkdir(parents=True, exist_ok=True)
    for i in range(n_images):
        (images / f"img_{i}.jpg").write_bytes(b"")
    if labels:
        labels_dir = tmp_path / "kit" / "labels" / split
        labels_dir.mkdir(parents=True, exist_ok=True)
        for i in range(n_images):
            (labels_dir / f"img_{i}.txt").write_text("0 0.5 0.5 0.1 0.1\n", encoding="utf-8")
    return images


def info_for(tmp_path: Path, splits: dict[str, Path]) -> dict:
    return {"splits": splits, "class_names": CLASSES, "nc": len(CLASSES)}


# ── Fix 1: the root actually resolves ────────────────────────────────────


def test_project_root_url_is_the_configured_root(rooted, tmp_path, root_shape):
    assert importer._project_root_url() == project_root(tmp_path, root_shape)


def test_table_url_follows_the_layout_under_any_root(rooted, tmp_path, root_shape):
    root = project_root(tmp_path, root_shape)
    url = importer._table_url("initial", "exdark_train", PROJECT)
    assert str(url) == f"{root}/{PROJECT}/datasets/exdark_train/tables/initial"


def test_table_url_normalizes_a_windows_style_root(tlc_stub, tmp_path):
    # tlc.Url normalizes separators and the trailing slash, so however the
    # root is spelled in config.yaml the built URL is one canonical string.
    tlc_stub.config.project_root_url = "D:\\3lc-data\\"
    url = importer._table_url("initial", "exdark_train", PROJECT)
    assert str(url) == f"D:/3lc-data/{PROJECT}/datasets/exdark_train/tables/initial"


def test_table_url_agrees_with_where_the_import_actually_wrote(rooted, tmp_path, root_shape):
    """The bug itself: creation passes project_name/dataset_name and lets
    tlc resolve the root, while _table_url synthesized its own. When those
    two disagree, Import succeeds and every other tab points at nothing."""
    rooted.row_count = 2
    info = info_for(tmp_path, {"train": make_split(tmp_path, "train", labels=True)})
    table, _reused = importer._import_labeled_split(info, "train", PROJECT, "initial")
    assert str(table.url) == str(importer._table_url("initial", "exdark_train", PROJECT))
    assert Path(str(table.url)).is_dir()


# ── Fix 2: the URL parses under any root shape ───────────────────────────


def test_url_helpers_round_trip_a_built_url(rooted, tmp_path, root_shape):
    url = str(importer._table_url("round2", "exdark_train", PROJECT))
    assert config_store.url_project(url) == PROJECT
    assert config_store.url_dataset(url) == "exdark_train"
    assert config_store.url_table(url) == "round2"


def test_url_project_ignores_a_datasets_dir_higher_up():
    # The tail anchor is what makes dropping the "/projects/" anchor safe:
    # a root that itself contains "datasets/" must not win the match.
    url = "D:/datasets/staging/exdark-competition/datasets/exdark_train/tables/initial"
    assert config_store.url_project(url) == "exdark-competition"


def test_url_helpers_accept_backslash_urls_and_whitespace():
    url = "  D:\\3lc-data\\exdark-competition\\datasets\\exdark_train\\tables\\round2  "
    assert config_store.url_project(url) == "exdark-competition"
    assert config_store.url_dataset(url) == "exdark_train"
    assert config_store.url_table(url) == "round2"


@pytest.mark.parametrize(
    ("table_name", "dataset", "expected"),
    [
        ("initial", "exdark_train", "suppress"),  # equals derivation (M1)
        ("round2", "exdark_train", "keep"),  # a genuine revision choice
        ("initial", "exdark_val", "drop"),  # DP-11 cross-split
    ],
)
def test_classify_override_verdicts_are_root_independent(
    rooted, tmp_path, root_shape, table_name, dataset, expected
):
    """Before the fix the bare root collapsed all three verdicts to "drop",
    which is what silently discarded Gudbrand's corrected URL."""
    url = str(importer._table_url(table_name, dataset, PROJECT))
    assert config_store.classify_override(url, PROJECT, "initial", "train") == expected


def test_cross_project_url_still_drops(rooted, tmp_path, root_shape):
    url = str(importer._table_url("initial", "exdark_train", "some-other-project"))
    assert config_store.classify_override(url, PROJECT, "initial", "train") == "drop"


# ── The reuse gates (importer.py:282, 303) ───────────────────────────────


def test_labeled_split_reuse_flag_tracks_the_configured_root(rooted, tmp_path, root_shape):
    rooted.row_count = 2
    info = info_for(tmp_path, {"train": make_split(tmp_path, "train", labels=True)})
    _table, first = importer._import_labeled_split(info, "train", PROJECT, "initial")
    assert first is False  # nothing on disk yet
    _table, second = importer._import_labeled_split(info, "train", PROJECT, "initial")
    assert second is True  # reported "created" for every re-import before the fix


def test_test_split_reuses_an_existing_table(rooted, tmp_path, root_shape):
    rooted.row_count = 2
    info = info_for(tmp_path, {"test": make_split(tmp_path, "test")})
    Path(str(importer._table_url("initial", "exdark_test", PROJECT))).mkdir(parents=True)
    _table, reused, mechanism = importer._import_test_split(info, PROJECT, "initial", lambda _m: None)
    assert (reused, mechanism) == (True, "reuse-existing")


def test_test_split_labelless_import(rooted, tmp_path, root_shape):
    rooted.row_count = 2
    info = info_for(tmp_path, {"test": make_split(tmp_path, "test")})
    _table, reused, mechanism = importer._import_test_split(info, PROJECT, "initial", lambda _m: None)
    assert (reused, mechanism) == (False, "from_yolo_url-labelless")


def test_test_split_gt_leak_guard_builds_images_only(rooted, tmp_path, root_shape):
    """Labels on disk (organizer machine): the table is built with
    TableWriter so hidden ground truth cannot leak in."""
    rooted.row_count = 2
    info = info_for(tmp_path, {"test": make_split(tmp_path, "test", labels=True)})
    _table, reused, mechanism = importer._import_test_split(info, PROJECT, "initial", lambda _m: None)
    assert (reused, mechanism) == (False, "tablewriter-images-only")
    writer = next(c for c in rooted.calls if c[0] == "TableWriter")
    assert writer[1]["if_exists"] == "raise"


def test_test_split_with_labels_and_an_existing_table_reuses_instead_of_raising(
    rooted, tmp_path, root_shape
):
    """The premise the TableWriter branch documents ("url.exists() was False
    above, anything else is a race") was FALSE under a non-default root: the
    reuse gate looked under the default root, missed, and the writer then
    hit if_exists="raise" on a table that really did exist."""
    rooted.row_count = 2
    info = info_for(tmp_path, {"test": make_split(tmp_path, "test", labels=True)})
    Path(str(importer._table_url("initial", "exdark_test", PROJECT))).mkdir(parents=True)
    _table, reused, mechanism = importer._import_test_split(info, PROJECT, "initial", lambda _m: None)
    assert (reused, mechanism) == (True, "reuse-existing")
    assert not [c for c in rooted.calls if c[0] == "TableWriter"]


# ── Revisit view and the revision picker ─────────────────────────────────


def test_verified_import_state_synthesizes_from_the_configured_root(
    rooted, tmp_path, root_shape, store
):
    """The pre-snapshot branch (importer.py:523): older configs carry no
    import_state.tables, so the URLs are re-derived. Under the wrong root
    they resolved nowhere and the Import tab fell back to a blank form."""
    write_config(
        store,
        {
            "session": {**config_store.default_session(), "project_name": PROJECT},
            "_migrations": {"device_blank_default": True, "session_v1": "fresh"},
        },
    )
    for split in importer.SPLITS:
        Path(str(importer._table_url("initial", f"exdark_{split}", PROJECT))).mkdir(parents=True)

    state = importer.verified_import_state()
    assert state["state"] == "success"
    assert state["synthesized"] is True
    assert state["verified"] == {s: True for s in importer.SPLITS}


def test_list_project_tables_walks_the_configured_root(rooted, tmp_path, root_shape):
    rooted.row_count = 5
    for split in importer.SPLITS:
        Path(str(importer._table_url("initial", f"exdark_{split}", PROJECT))).mkdir(parents=True)

    out = importer.list_project_tables(PROJECT)
    assert [d["name"] for d in out["datasets"]] == ["exdark_test", "exdark_train", "exdark_val"]
    for dataset in out["datasets"]:
        assert [t["name"] for t in dataset["tables"]] == ["initial"]
        assert dataset["tables"][0]["latest"] is True


def test_list_project_tables_is_empty_when_the_root_holds_nothing(rooted, tmp_path, root_shape):
    assert importer.list_project_tables(PROJECT) == {"project": PROJECT, "datasets": []}


# ── The regression that made all of the above invisible ──────────────────


def test_plugin_reads_config_through_tlc_dot_config():
    """3LC config is read through the public accessor, never tlcconfig's
    string-keyed store or its private default helper. Inlining it back is
    how this bug returns: ConfigStore.get() is keyed by string (an Option
    misses silently) AND returns raw values, so "~/3lc-data", "$VAR" and
    "<ALIAS>" arrive unexpanded. See _project_root_url's docstring."""
    package = Path(importer.__file__).parent
    offenders = {
        path.name: line.strip()
        for path in sorted(package.glob("*.py"))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.lstrip().startswith(("import tlcconfig", "from tlcconfig"))
    }
    assert offenders == {}


def test_url_seg_patterns_carry_no_projects_literal():
    """The default root ends in "projects"; no other root does. A pattern
    that names it is the bug (config_store.URL_SEG_PATTERNS)."""
    for kind, pattern in config_store.URL_SEG_PATTERNS.items():
        assert "projects" not in pattern, kind
