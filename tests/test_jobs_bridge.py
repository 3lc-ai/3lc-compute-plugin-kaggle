"""Tests for jobs._BridgedJobCtx — the store→SDK event mirror.

The bridge wraps every SDK call in try/except (the store is authoritative,
the event stream best-effort), which means a WRONG CALL SHAPE against the SDK
fails silently: nothing crashes, the event just never reaches the Queue
panel. That is exactly how the v1.2.7→v1.2.8 `result()` regression would
have hidden (SDK 0.3.x renamed the keyword-only `run_url=` parameter to a
positional `url`; the old call TypeError'd inside the except and the
Open-run link vanished with nothing logged). So these tests do NOT assert
"no exception" — they assert the fake SDK ctx, whose methods carry the REAL
0.3.x signatures, actually RECEIVED each event. A signature drift in either
direction turns a received-event assertion red.
"""

from __future__ import annotations

from tlc_plugin_kaggle import jobs


class _Sdk03Ctx:
    """Fake SDK JobContext with the 0.3.x plugin-facing signatures, verbatim.

    Keep these signatures in lockstep with tlc_plugin_sdk.job_context (the
    pinned >=0.3.1,<0.4 window): a bridged call that the real SDK would
    reject raises here too — and is swallowed by the bridge, so the
    received-events list stays empty and the assertion names the loss.
    """

    def __init__(self) -> None:
        self.received: list[tuple] = []
        self.job_id = "sdkjob01"
        self.cancelled = False

    def log(self, message: str) -> None:
        self.received.append(("log", message))

    def progress(self, *, percent: float, label: str = "", timing: dict | None = None) -> None:
        self.received.append(("progress", percent, label))

    def metric(self, label: str, value) -> None:
        self.received.append(("metric", label, value))

    def result(self, url: str) -> None:
        self.received.append(("result", url))


def _bridged(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "JOBS_DIR", tmp_path / "jobs")
    job = {
        "id": "sdkjob01", "kind": "train", "status": "running",
        "cancelled": False, "log": [], "checks": [], "progress": {}, "facts": {},
    }
    sdk = _Sdk03Ctx()
    return jobs._BridgedJobCtx(job, sdk), sdk, job


def test_result_event_reaches_sdk_with_0_3_signature(tmp_path, monkeypatch):
    """The Queue panel's Open-run link: set_field('run_url') must land as a
    result() call the 0.3.x SDK accepts. This is the Z1 regression pin."""
    ctx, sdk, job = _bridged(tmp_path, monkeypatch)
    ctx.set_field("run_url", "http://localhost:5015/objects/runs/p/run1")
    assert ("result", "http://localhost:5015/objects/runs/p/run1") in sdk.received
    # The store copy is written regardless (it is the authoritative side).
    assert job["facts"]["run_url"] == "http://localhost:5015/objects/runs/p/run1"


def test_non_run_url_fields_do_not_emit_result(tmp_path, monkeypatch):
    ctx, sdk, _job = _bridged(tmp_path, monkeypatch)
    ctx.set_field("weights", "C:/x/best.pt")
    assert not [e for e in sdk.received if e[0] == "result"]


def test_epoch_progress_and_metrics_reach_sdk(tmp_path, monkeypatch):
    ctx, sdk, _job = _bridged(tmp_path, monkeypatch)
    ctx.set_progress({"epoch": 2, "total_epochs": 4, "metrics": {"m50": 0.5, "note": "text-ignored"}})
    assert ("progress", 50.0, "Epoch 2/4") in sdk.received
    assert ("metric", "m50", 0.5) in sdk.received
    assert not [e for e in sdk.received if e[0] == "metric" and e[1] == "note"]


def test_percent_progress_reaches_sdk(tmp_path, monkeypatch):
    """Generic writers (download_kit) publish percent/label directly."""
    ctx, sdk, _job = _bridged(tmp_path, monkeypatch)
    ctx.set_progress({"percent": 42.5, "label": "Downloading shard 5/10"})
    assert ("progress", 42.5, "Downloading shard 5/10") in sdk.received


def test_log_reaches_sdk(tmp_path, monkeypatch):
    ctx, sdk, _job = _bridged(tmp_path, monkeypatch)
    ctx.log("hello")
    assert ("log", "hello") in sdk.received


def test_cancellation_is_union_of_sdk_and_disk(tmp_path, monkeypatch):
    ctx, sdk, _job = _bridged(tmp_path, monkeypatch)
    assert ctx.is_cancelled() is False
    sdk.cancelled = True
    assert ctx.is_cancelled() is True
