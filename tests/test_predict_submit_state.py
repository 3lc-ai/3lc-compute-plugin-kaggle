"""DP-08: the revisit basis requires the predict JOB RECORD to exist, not
just the CSV — the job store prunes at 50 records, and a snapshot whose
record was pruned would render an unlocked step 2 whose submit and CSV
download both 404.
"""

from __future__ import annotations

from conftest import write_config

from tlc_plugin_kaggle import jobs, predictor


def _write_state(store, tmp_path, job_id="p1", with_csv=True):
    csv_path = tmp_path / "submission.csv"
    if with_csv:
        csv_path.write_text("id,image_id,prediction_string\n", encoding="utf-8")
    write_config(store, {
        "predict_state": {"job_id": job_id, "csv_path": str(csv_path), "run_name": "r1"},
        "_migrations": {"device_blank_default": True, "session_v1": "fresh"},
    })
    return csv_path


def test_record_and_csv_present_is_predicted(store, tmp_path, monkeypatch):
    _write_state(store, tmp_path)
    monkeypatch.setattr(jobs, "get_job", lambda jid: {"id": jid})
    assert predictor.predict_submit_state()["state"] == "predicted"


def test_pruned_record_is_empty_despite_csv(store, tmp_path, monkeypatch):
    _write_state(store, tmp_path)
    monkeypatch.setattr(jobs, "get_job", lambda jid: None)  # pruned
    assert predictor.predict_submit_state() == {"state": "empty"}


def test_missing_csv_is_empty_despite_record(store, tmp_path, monkeypatch):
    _write_state(store, tmp_path, with_csv=False)
    monkeypatch.setattr(jobs, "get_job", lambda jid: {"id": jid})
    assert predictor.predict_submit_state() == {"state": "empty"}


def test_missing_job_id_is_empty(store, tmp_path, monkeypatch):
    _write_state(store, tmp_path, job_id="")
    monkeypatch.setattr(jobs, "get_job", lambda jid: {"id": jid})
    assert predictor.predict_submit_state() == {"state": "empty"}


def test_submitted_pairing_still_resolves(store, tmp_path, monkeypatch):
    csv_path = tmp_path / "submission.csv"
    csv_path.write_text("id,image_id,prediction_string\n", encoding="utf-8")
    write_config(store, {
        "predict_state": {"job_id": "p1", "csv_path": str(csv_path), "run_name": "r1"},
        "submit_state": {"predict_job_id": "p1", "status": "submitted", "ref": "00000000"},
        "_migrations": {"device_blank_default": True, "session_v1": "fresh"},
    })
    monkeypatch.setattr(jobs, "get_job", lambda jid: {"id": jid})
    out = predictor.predict_submit_state()
    assert out["state"] == "submitted"
    assert out["submission"]["ref"] == "00000000"
