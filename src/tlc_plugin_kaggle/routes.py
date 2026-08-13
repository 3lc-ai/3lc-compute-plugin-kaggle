"""REST routes for the Kaggle plugin (0.2.x worker app).

Paths are RELATIVE: the SDK worker serves this controller in the plugin's own
Litestar app, and the host proxies /api/plugins/kaggle-exdark/<subpath> -> /<subpath>
via its catch-all — so client-side URLs are unchanged from v1.1.x. Adding or
renaming routes needs only a worker restart (plugin reload), never a service
restart. Reserved paths the HOST owns ahead of the proxy: /ui, /compute, /run,
POST /jobs/{id}/run, POST /jobs/{id}/cancel — job START and CANCEL therefore
go through the host dispatch channel; the /validate/<kind> handlers below keep
the fail-fast form UX (400 + participant-facing message) that /run's
fire-and-return contract does not provide.
"""

from __future__ import annotations

from typing import Any

from litestar import Controller, Response, get, post
from litestar.exceptions import NotFoundException
from litestar.status_codes import HTTP_400_BAD_REQUEST

from tlc_plugin_kaggle.constants import DEFAULT_PROJECT, DEFAULT_TABLE


def _resolve_predict_params(data: Any) -> tuple[dict[str, Any] | None, Response | None]:
    """Shared request validation for the predict-shaped routes: resolve
    train_job_id | weights_path to an on-disk weights file and require a
    test table URL. Returns (params, None) or (None, error response)."""
    from pathlib import Path

    from tlc_plugin_kaggle import jobs

    def bad(msg: str) -> tuple[None, Response]:
        return None, Response(content={"error": msg}, status_code=HTTP_400_BAD_REQUEST)

    if not isinstance(data, dict):
        return bad("Body must be a JSON object")
    weights = str(data.get("weights_path", "")).strip().strip('"')
    train_job_id = str(data.get("train_job_id", "")).strip()
    # Direct weights files are host-only (same gate as local scoring):
    # participants predict from plugin runs so every submission carries
    # verified provenance. Enforced here, not just hidden in the UI.
    if weights:
        from tlc_plugin_kaggle import predictor

        if not predictor.is_host():
            return bad(
                "Direct weights files are host-only. Select a run trained in "
                "this plugin — predictions must carry verified provenance."
            )
    run_name = ""
    if not weights and train_job_id:
        job = jobs.get_job(train_job_id)
        facts = (job or {}).get("facts") or {}
        weights = str(facts.get("weights", ""))
        run_name = ((job or {}).get("result") or {}).get("run_name", "")
    if not weights:
        return bad("Select a run or provide a weights path.")
    if not Path(weights).is_file():
        return bad(f"Weights file not found: {weights}")
    if not str(data.get("test_table_url", "")).strip():
        return bad("Missing required field 'test_table_url'")

    params = dict(data)
    params["weights_path"] = weights
    if run_name:
        params.setdefault("run_name", run_name)
    return params, None


class KaggleController(Controller):
    """Kaggle competition workflow endpoints."""

    path = ""

    @get("/import/preflight", sync_to_thread=True)
    def import_preflight(self, yaml_path: str = "") -> dict[str, Any]:
        """Read-only dry run of the yaml for the Import form's progressive
        disclosure. Never writes; failures come back as {"error": ...} with
        HTTP 200 so the debounced form handler treats them as render states,
        not exceptions."""
        from tlc_plugin_kaggle import importer

        if not yaml_path.strip():
            return {"error": "yaml_path is required"}
        try:
            return importer.preflight(yaml_path)
        except Exception as exc:
            return {"error": f"{type(exc).__name__}: {exc}"}

    @post("/validate/import", sync_to_thread=True)
    def validate_import(self, data: dict[str, Any]) -> Response:
        """Fail-fast validation for the Import job; the UI then POSTs the
        returned params (plus kind) to the host's /api/plugins/kaggle-exdark/run.
        Body: {dataset_yaml, project_name?, table_name?}."""
        from tlc_plugin_kaggle import importer

        if not isinstance(data, dict) or not str(data.get("dataset_yaml", "")).strip():
            return Response(
                content={"error": "Missing required field 'dataset_yaml'"},
                status_code=HTTP_400_BAD_REQUEST,
            )

        # Fail fast on an unreadable yaml before spawning the job thread.
        try:
            importer.parse_dataset_yaml(str(data["dataset_yaml"]))
        except Exception as exc:
            return Response(
                content={"error": f"{type(exc).__name__}: {exc}"},
                status_code=HTTP_400_BAD_REQUEST,
            )

        raw_force = data.get("force_splits") or []
        if not isinstance(raw_force, list):
            return Response(
                content={"error": "'force_splits' must be a list of split names"},
                status_code=HTTP_400_BAD_REQUEST,
            )
        params = {
            "dataset_yaml": str(data["dataset_yaml"]).strip(),
            "project_name": str(data.get("project_name") or DEFAULT_PROJECT).strip(),
            "table_name": str(data.get("table_name") or DEFAULT_TABLE).strip(),
            "force_splits": [s for s in (str(x) for x in raw_force) if s in importer.SPLITS],
        }
        return Response(content={"ok": True, "params": params}, status_code=200)

    @get("/import/state", sync_to_thread=True)
    def import_state(self) -> dict[str, Any]:
        """Revisit state for the Import tab: the persisted last-successful-
        import snapshot, re-verified against table existence on disk."""
        from tlc_plugin_kaggle import importer

        try:
            return importer.verified_import_state()
        except Exception as exc:
            return {"state": "empty", "reason": f"{type(exc).__name__}: {exc}"}

    @get("/import/revisions", sync_to_thread=True)
    def import_revisions(self, url: str = "") -> dict[str, Any]:
        """Revision info for one table (force-reimport confirmation guard)."""
        from tlc_plugin_kaggle import importer

        if not url.strip():
            return {"error": "url is required"}
        try:
            return importer.table_revisions(url.strip())
        except Exception as exc:
            return {"error": f"{type(exc).__name__}: {exc}"}

    @get("/jobs/{job_id:str}")
    async def job_status(self, job_id: str) -> dict[str, Any]:
        from tlc_plugin_kaggle import jobs

        job = jobs.get_job(job_id)
        if job is None:
            raise NotFoundException(detail=f"No such job: {job_id}")
        return job

    @get("/jobs")
    async def jobs_list(self, kind: str = "") -> list[dict[str, Any]]:
        from tlc_plugin_kaggle import jobs

        return jobs.list_jobs(kind or None)

    @get("/tables/defaults", sync_to_thread=True)
    def table_defaults(self, project: str = DEFAULT_PROJECT, table: str = DEFAULT_TABLE) -> dict[str, Any]:
        """Canonical table URLs for the pickers' defaults, with exists flags."""
        from tlc_plugin_kaggle import importer

        out: dict[str, Any] = {"project": project}
        for split in ("train", "val", "test"):
            url = importer._table_url(table, f"exdark_{split}", project)
            out[split] = {"url": str(url), "exists": url.exists()}
        return out

    @post("/validate/train", sync_to_thread=True)
    def validate_train(self, data: dict[str, Any]) -> Response:
        """Fail-fast validation for the Train job (locked server-side:
        yolo11n.pt pinned COCO-pretrained init / 640); UI then POSTs /run."""
        from tlc_plugin_kaggle import trainer

        if not isinstance(data, dict):
            return Response(content={"error": "Body must be a JSON object"}, status_code=HTTP_400_BAD_REQUEST)
        for field in ("train_table_url", "val_table_url"):
            if not str(data.get(field, "")).strip():
                return Response(
                    content={"error": f"Missing required field '{field}'"},
                    status_code=HTTP_400_BAD_REQUEST,
                )

        # Fail fast — the extra-args lock guard, bounds, and field validation
        # run here so a locked-key attempt or out-of-bounds value is a 400
        # with the participant-facing message, not a failed job. run_training
        # re-validates (defense in depth: the locked kwargs are merged last
        # there regardless). validate_settings, NOT build_settings: this
        # request must never import torch — a cold worker paying that import
        # here is the round-1 first-train timeout.
        try:
            trainer.build_train_kwargs(data)
            trainer.validate_settings(data)
        except ValueError as exc:
            return Response(content={"error": str(exc)}, status_code=HTTP_400_BAD_REQUEST)

        return Response(content={"ok": True, "params": dict(data)}, status_code=200)

    @get("/runs", sync_to_thread=True)
    def list_runs(self) -> list[dict[str, Any]]:
        """Train jobs for the Run selector, newest first, with provenance
        summary fields. Unusable runs (failed, still training, weights gone
        from disk) are included with usable=False and a participant-facing
        reason so the selector can list them disabled."""
        from pathlib import Path

        from tlc_plugin_kaggle import jobs

        out: list[dict[str, Any]] = []
        for job in jobs.list_jobs("train"):
            facts = job.get("facts") or {}
            result = job.get("result") or {}
            progress = job.get("progress") or {}
            history = progress.get("history") or []
            status = str(job.get("status") or "")
            weights = str(facts.get("weights") or "")
            weights_on_disk = bool(weights) and Path(weights).is_file()

            usable, reason = True, ""
            if status == "running":
                usable, reason = False, "still training"
            elif not weights:
                usable, reason = False, (
                    f"failed: {job.get('error')}" if job.get("error") else "no best.pt saved"
                )
            elif not weights_on_disk:
                usable, reason = False, "best.pt missing on disk"

            # Display-time clamp for records written before the final-val
            # guard (trainer.on_fit_epoch_end): ultralytics' best-model
            # validation pass logged as epochs+1, so old 2-epoch runs say 3.
            epochs_completed = result.get("epochs_completed") or progress.get("epoch")
            requested = (job.get("params") or {}).get("epochs")
            try:
                if epochs_completed and requested:
                    epochs_completed = min(int(epochs_completed), int(float(requested)))
            except (TypeError, ValueError):
                pass

            m50s = [h.get("m50") for h in history if isinstance(h.get("m50"), (int, float))]
            provenance = result.get("provenance") or []
            # Contract era, read from the run's own stored provenance labels:
            # pre-repositioning runs asserted "(from scratch)" and stay valid
            # history — conforming yolo11n runs, truthfully tagged legacy.
            if any("from scratch" in str(c.get("label") or "") for c in provenance):
                contract = "legacy_scratch"
            elif provenance:
                contract = "pretrained"
            else:
                contract = None
            out.append(
                {
                    "job_id": job.get("id"),
                    "run_name": result.get("run_name")
                    or facts.get("run_name")
                    or (job.get("params") or {}).get("run_name")
                    or "",
                    "weights": weights,
                    "run_url": facts.get("run_url"),
                    "status": status,
                    "created_at": job.get("created_at"),
                    "epochs_completed": epochs_completed,
                    "best_map50": max(m50s) if m50s else None,
                    "provenance_ok": bool(provenance) and all(c.get("ok") for c in provenance),
                    "contract": contract,
                    "checkpoint_sha256": facts.get("checkpoint_sha256")
                    or result.get("checkpoint_sha256")
                    or "",
                    "usable": usable,
                    "reason": reason,
                }
            )
        return out

    @post("/validate/predict", sync_to_thread=True)
    def validate_predict(self, data: dict[str, Any]) -> Response:
        """Fail-fast validation for the predict job (step 1: inference ->
        CSV -> validation -> sanity -> local score); UI then POSTs /run.

        Body: {train_job_id? | weights_path?, test_table_url, conf?, device?}
        """
        params, err = _resolve_predict_params(data)
        if err is not None:
            return err
        return Response(content={"ok": True, "params": params}, status_code=200)

    @post("/validate/submit", sync_to_thread=True)
    def validate_submit(self, data: dict[str, Any]) -> Response:
        """Fail-fast validation for the Kaggle-submit job (step 2: upload a
        prior predict job's validated CSV); UI then POSTs /run.

        Body: {predict_job_id, message?, competition_slug?}
        """
        from pathlib import Path

        from tlc_plugin_kaggle import jobs

        if not isinstance(data, dict) or not str(data.get("predict_job_id", "")).strip():
            return Response(
                content={"error": "Missing required field 'predict_job_id'"},
                status_code=HTTP_400_BAD_REQUEST,
            )
        # Fail fast with the participant-facing message before spawning the
        # job thread; run_kaggle_submit re-validates (defense in depth).
        pjob = jobs.get_job(str(data["predict_job_id"]).strip())
        csv_path = str(((pjob or {}).get("facts") or {}).get("csv_path", ""))
        if pjob is None or not csv_path or not Path(csv_path).is_file():
            return Response(
                content={"error": "No validated prediction CSV found for that job. Run inference first."},
                status_code=HTTP_400_BAD_REQUEST,
            )
        return Response(content={"ok": True, "params": dict(data)}, status_code=200)

    @get("/submit/state", sync_to_thread=True)
    def submit_state(self) -> dict[str, Any]:
        """Revisit state for the Predict + Submit tab: persisted snapshots
        with the CSV re-verified on disk."""
        from tlc_plugin_kaggle import predictor

        try:
            return predictor.predict_submit_state()
        except Exception as exc:
            return {"state": "empty", "reason": f"{type(exc).__name__}: {exc}"}

    @get("/tables/list", sync_to_thread=True)
    def tables_list(self, project: str = DEFAULT_PROJECT) -> dict[str, Any]:
        """Datasets -> ordered revision chains (revision picker)."""
        from tlc_plugin_kaggle import importer

        try:
            return importer.list_project_tables(project)
        except Exception as exc:
            return {"project": project, "datasets": [], "error": f"{type(exc).__name__}: {exc}"}

    @get("/kaggle/status", sync_to_thread=True)
    def kaggle_status(self, slug: str = "") -> dict[str, Any]:
        """Live Kaggle section of the Status card (sync, manual Refresh)."""
        from tlc_plugin_kaggle import predictor

        return predictor.kaggle_live_status(slug)

    @get("/kaggle/connection", sync_to_thread=True)
    def kaggle_connection(self, slug: str = "") -> dict[str, Any]:
        """Submit tab connection panel: no_credentials / not_joined / ready."""
        from tlc_plugin_kaggle import predictor

        return predictor.kaggle_connection(slug)

    @get("/submissions/{job_id:str}/download", sync_to_thread=True)
    def download_submission(self, job_id: str) -> Response:
        """Stream a predict job's generated submission.csv to the browser."""
        from pathlib import Path

        from tlc_plugin_kaggle import jobs

        job = jobs.get_job(job_id)
        if job is None:
            raise NotFoundException(detail=f"No such job: {job_id}")
        csv_path = str((job.get("facts") or {}).get("csv_path", ""))
        if not csv_path or not Path(csv_path).is_file():
            raise NotFoundException(detail=f"Job {job_id} has no submission CSV on disk.")
        return Response(
            content=Path(csv_path).read_bytes(),
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="{Path(csv_path).name}"',
                "Cache-Control": "no-store",
            },
        )

    @get("/config", sync_to_thread=True)
    def get_config(self) -> dict[str, Any]:
        """Last-used form values per tab (re-runs become one click), plus a
        _meta block (version, repository) the fragment renders in the
        footer and stamps into diagnostics."""
        import tlc_plugin_kaggle
        from tlc_plugin_kaggle import config_store, constants, predictor

        out = config_store.load()
        # The session always arrives populated: missing fields (fresh
        # install, partial write) fill from the shipped defaults here, so
        # the fragment carries no default literals of its own.
        stored = out.get("session")
        out["session"] = {
            **config_store.default_session(),
            **(stored if isinstance(stored, dict) else {}),
        }
        out["_meta"] = {
            "version": tlc_plugin_kaggle.__version__,
            "repository_url": tlc_plugin_kaggle.REPOSITORY_URL,
            # Host machines (metric + solution on disk) get host-only UI:
            # the direct weights-file source and local scores.
            "host": predictor.is_host(),
            # Shipped slug, so the fragment can render the effective slug
            # (session.slug_override or this) without a Kaggle connection.
            "default_slug": constants.COMPETITION_SLUG,
        }
        return out

    @post("/config", sync_to_thread=True)
    def save_config(self, data: dict[str, Any]) -> Response:
        """Merge per-tab form snapshots. Body: {"session": {...}} /
        {"train": {...}} etc. Writes carrying keys retired by session_v1
        are rejected whole (400): only a stale cached fragment sends them,
        and a visible failure beats silently re-creating the duplication."""
        from tlc_plugin_kaggle import config_store

        if not isinstance(data, dict):
            return Response(content={}, status_code=200)
        try:
            return Response(content=config_store.save(data), status_code=200)
        except ValueError as exc:
            return Response(content={"error": str(exc)}, status_code=HTTP_400_BAD_REQUEST)

    @get("/pipeline", sync_to_thread=True)
    def pipeline_state(self, project: str = DEFAULT_PROJECT) -> dict[str, Any]:
        """Where the participant is in the Import -> Train -> Submit loop.

        Import-done delegates to verified_import_state so the stepper
        checkmark and the Import tab's revisit view can never disagree:
        both mean "snapshot (or synthesized pre-snapshot state) whose three
        tables verifiably exist on disk right now".
        """
        from tlc_plugin_kaggle import importer, jobs

        all_jobs = jobs.list_jobs()
        import_done = importer.verified_import_state().get("state") == "success"
        train_done = any(
            j.get("kind") == "train" and (j.get("facts") or {}).get("weights") for j in all_jobs
        )
        # Two-step flow: a kaggle_submit job that Kaggle accepted, or a
        # legacy single-job predict_submit completion.
        submit_done = any(
            (j.get("kind") == "kaggle_submit"
             and ((j.get("facts") or {}).get("submission") or {}).get("status") == "submitted")
            or (j.get("kind") == "predict_submit" and j.get("status") == "completed")
            for j in all_jobs
        )
        return {"import": import_done, "train": train_done, "submit": submit_done}
