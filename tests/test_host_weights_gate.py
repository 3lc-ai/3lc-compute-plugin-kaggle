"""The plugin-run-only gate (v1.2.13).

Participants predict only from runs trained in this plugin, so every
submission carries verified provenance. Until v1.2.13 that rule lived ONLY in
`/validate/predict`; the host's `/run` dispatch never traverses that route
(routes.py, ui.html kgStartJob), so a hand-rolled POST walked straight past
it — the same layer-3 gap DP-11 had already closed for split identity.

These tests pin BOTH layers against ONE resolver. That pairing is the point:
`predictor.resolve_weights` is the single definition site, and a suite that
exercised only the route would have passed against the bug for nine releases,
exactly as the divergence guards in CLAUDE.md §B describe.
"""

from __future__ import annotations

import pytest

from tlc_plugin_kaggle import jobs, predictor, routes


@pytest.fixture
def run_weights(tmp_path, monkeypatch):
    """A finished train job whose weights exist on disk."""
    weights = tmp_path / "runs" / "kaggle_run_1" / "weights" / "best.pt"
    weights.parent.mkdir(parents=True)
    weights.write_bytes(b"plugin-trained")
    monkeypatch.setattr(
        jobs,
        "get_job",
        lambda jid: {
            "id": jid,
            "facts": {"weights": str(weights)},
            "result": {"run_name": "kaggle_run_1"},
        }
        if jid == "train-1"
        else None,
    )
    return weights


@pytest.fixture
def participant(monkeypatch):
    monkeypatch.setattr(predictor, "is_host", lambda: False)


@pytest.fixture
def host(monkeypatch):
    monkeypatch.setattr(predictor, "is_host", lambda: True)


# ── The rule ─────────────────────────────────────────────────────────────

def test_plugin_run_resolves_for_a_participant(run_weights, participant):
    weights, run_name = predictor.resolve_weights({"train_job_id": "train-1"})
    assert weights == str(run_weights)
    assert run_name == "kaggle_run_1"


def test_bare_weights_path_is_refused_for_a_participant(tmp_path, participant):
    mine = tmp_path / "elsewhere.pt"
    mine.write_bytes(b"trained somewhere else")
    with pytest.raises(ValueError) as exc:
        predictor.resolve_weights({"weights_path": str(mine)})
    assert exc.value.args[0] == predictor.HOST_ONLY_WEIGHTS


def test_bare_weights_path_is_allowed_for_the_host(tmp_path, host):
    """The organizer's reference-baseline path stays open — that is the whole
    reason the affordance is gated rather than deleted."""
    mine = tmp_path / "control_pretrained.pt"
    mine.write_bytes(b"reference baseline")
    weights, run_name = predictor.resolve_weights({"weights_path": str(mine)})
    assert weights == str(mine)
    assert run_name == ""


def test_train_job_id_wins_and_the_supplied_path_is_ignored(run_weights, participant, tmp_path):
    """THE bypass case. A naive gate ("allow weights_path when train_job_id is
    present, since /validate resolved it") passes every other test in this file
    and is defeated by one request: send a real id AND an arbitrary path, and
    the arbitrary path is what gets loaded. The supplied path must be IGNORED,
    not merely deprioritised.
    """
    smuggled = tmp_path / "smuggled.pt"
    smuggled.write_bytes(b"trained elsewhere, submitted as a plugin run")

    weights, run_name = predictor.resolve_weights(
        {"train_job_id": "train-1", "weights_path": str(smuggled)}
    )

    assert weights == str(run_weights), "the record's weights must win"
    assert weights != str(smuggled)
    assert run_name == "kaggle_run_1"


def test_the_host_is_held_to_the_same_rule_when_naming_a_run(run_weights, host, tmp_path):
    """Rule 1 is not a participant rule — it is how a train_job_id is read.
    Being the host does not make a smuggled path win over a named run."""
    smuggled = tmp_path / "smuggled.pt"
    smuggled.write_bytes(b"x")
    weights, _ = predictor.resolve_weights(
        {"train_job_id": "train-1", "weights_path": str(smuggled)}
    )
    assert weights == str(run_weights)


# ── Messages that were already load-bearing keep their exact text ────────

def test_neither_field_still_asks_for_a_run_not_for_a_host(participant):
    """A participant who picked nothing gets the ordinary prompt, not the
    host-only refusal — the gate must not swallow the empty-form case."""
    with pytest.raises(ValueError) as exc:
        predictor.resolve_weights({})
    assert exc.value.args[0] == "Select a run or provide a weights path."


def test_run_without_recorded_weights_names_that_cause(monkeypatch, participant):
    monkeypatch.setattr(jobs, "get_job", lambda jid: {"id": jid, "facts": {}})
    with pytest.raises(ValueError, match="no weights on record"):
        predictor.resolve_weights({"train_job_id": "train-1"})


def test_missing_file_names_the_path(tmp_path, host):
    with pytest.raises(ValueError, match="Weights file not found"):
        predictor.resolve_weights({"weights_path": str(tmp_path / "gone.pt")})


# ── Both layers, one policy ──────────────────────────────────────────────

def test_validate_route_refuses_the_participant_with_a_400(tmp_path, participant):
    mine = tmp_path / "elsewhere.pt"
    mine.write_bytes(b"x")
    params, err = routes._resolve_predict_params(
        {"weights_path": str(mine), "test_table_url": "irrelevant"}
    )
    assert params is None
    assert err.status_code == 400
    assert err.content["error"] == predictor.HOST_ONLY_WEIGHTS


def test_the_job_refuses_what_the_route_refuses(tmp_path, participant):
    """The layer that matters: /run never reaches the route, so the job has to
    refuse on its own. JobFailed rather than a bare exception, so the banner
    shows the sentence without a `ValueError:` prefix in front of it.
    """
    from tlc_plugin_sdk import JobFailed

    mine = tmp_path / "elsewhere.pt"
    mine.write_bytes(b"x")

    class _Ctx:
        def set_field(self, *a): ...
        def log(self, *a): ...

    with pytest.raises(JobFailed) as exc:
        predictor._predict_core(
            {"weights_path": str(mine), "test_table_url": "irrelevant"}, _Ctx()
        )
    assert str(exc.value) == predictor.HOST_ONLY_WEIGHTS
    assert "ValueError" not in str(exc.value)


def test_the_job_refuses_the_smuggled_path_too(run_weights, participant, tmp_path):
    """The bypass case again, through the job — the layer an attacker reaches.
    It must not merely refuse; it must load the RECORD's weights and carry on,
    so the failure below is the test table, never the weights.
    """
    smuggled = tmp_path / "smuggled.pt"
    smuggled.write_bytes(b"x")
    seen: dict[str, str] = {}

    class _Ctx:
        def set_field(self, key, value): seen[key] = value
        def log(self, *a): ...

    with pytest.raises(Exception):  # falls over later, on the test table
        predictor._predict_core(
            {
                "train_job_id": "train-1",
                "weights_path": str(smuggled),
                "test_table_url": "irrelevant",
            },
            _Ctx(),
        )
    assert seen.get("weights") == str(run_weights)
