"""REST routes for the Kaggle plugin.

Mounted once at service startup (installed host collects controllers only in
create_app) — adding/renaming routes here requires a compute-service restart;
changing handler BODIES only needs a plugin reload because the implementation
is lazy-imported per request.
"""

from __future__ import annotations

from typing import Any

from litestar import Controller, Response, get, post
from litestar.exceptions import NotFoundException
from litestar.status_codes import HTTP_400_BAD_REQUEST


class KaggleController(Controller):
    """Kaggle competition workflow endpoints."""

    path = "/api/plugins/kaggle"

    # This controller shadows the generic wildcard routes for our prefix, so
    # /ui must be re-exposed explicitly (see ComputePlugin.get_route_handlers
    # docstring on route shadowing).
    @get("/ui", media_type="text/html")
    async def ui(self) -> Response:
        from tlc_compute.plugins.registry import get_plugin

        plugin = get_plugin("kaggle")
        html = plugin.get_ui_fragment() if plugin else ""
        return Response(content=html, media_type="text/html", headers={"Cache-Control": "no-store"})

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

    @post("/import", sync_to_thread=True)
    def start_import(self, data: dict[str, Any]) -> Response:
        """Start the Import job. Body: {dataset_yaml, project_name?, table_name?}."""
        from tlc_plugin_kaggle import importer, jobs

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
            "project_name": str(data.get("project_name") or "exdark-competition").strip(),
            "table_name": str(data.get("table_name") or "initial").strip(),
            "force_splits": [s for s in (str(x) for x in raw_force) if s in importer.SPLITS],
        }
        job_id = jobs.start_job("import", params, importer.run_import)
        return Response(content={"job_id": job_id}, status_code=200)

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

    @post("/jobs/{job_id:str}/cancel", sync_to_thread=True)
    def cancel_job(self, job_id: str) -> dict[str, Any]:
        from tlc_plugin_kaggle import jobs

        job = jobs.cancel_job(job_id)
        if job is None:
            raise NotFoundException(detail=f"No such job: {job_id}")
        return {"cancelled": True, "job_id": job_id, "status": job.get("status")}

    @get("/jobs")
    async def jobs_list(self, kind: str = "") -> list[dict[str, Any]]:
        from tlc_plugin_kaggle import jobs

        return jobs.list_jobs(kind or None)

    @get("/tables/defaults", sync_to_thread=True)
    def table_defaults(self, project: str = "exdark-competition", table: str = "initial") -> dict[str, Any]:
        """Canonical table URLs for the pickers' defaults, with exists flags."""
        import tlc

        out: dict[str, Any] = {"project": project}
        for split in ("train", "val", "test"):
            url = tlc.Url.create_table_url(table, f"exdark_{split}", project)
            out[split] = {"url": str(url), "exists": url.exists()}
        return out

    @post("/train", sync_to_thread=True)
    def start_train(self, data: dict[str, Any]) -> Response:
        """Start the Train job. Locked server-side: yolo11n.yaml / 640 / no pretrained."""
        from tlc_plugin_kaggle import jobs, trainer

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
        # there regardless).
        try:
            trainer.build_train_kwargs(data)
            trainer.build_settings(data)
        except ValueError as exc:
            return Response(content={"error": str(exc)}, status_code=HTTP_400_BAD_REQUEST)

        job_id = jobs.start_job("train", dict(data), trainer.run_training)
        return Response(content={"job_id": job_id}, status_code=200)

    @get("/runs")
    async def list_runs(self) -> list[dict[str, Any]]:
        """Completed train jobs that produced weights, newest first (Run selector)."""
        from tlc_plugin_kaggle import jobs

        out: list[dict[str, Any]] = []
        for job in jobs.list_jobs("train"):
            facts = job.get("facts") or {}
            if not facts.get("weights"):
                continue
            out.append(
                {
                    "job_id": job.get("id"),
                    "run_name": (job.get("result") or {}).get("run_name")
                    or (job.get("params") or {}).get("run_name")
                    or "",
                    "weights": facts.get("weights"),
                    "run_url": facts.get("run_url"),
                    "status": job.get("status"),
                    "created_at": job.get("created_at"),
                }
            )
        return out

    @post("/predict_submit", sync_to_thread=True)
    def start_predict_submit(self, data: dict[str, Any]) -> Response:
        """Start the Predict + Submit job.

        Body: {train_job_id? | weights_path?, test_table_url, conf?, device?,
               message?, competition_slug?, csv_only?}
        """
        from pathlib import Path

        from tlc_plugin_kaggle import jobs, predictor

        if not isinstance(data, dict):
            return Response(content={"error": "Body must be a JSON object"}, status_code=HTTP_400_BAD_REQUEST)

        weights = str(data.get("weights_path", "")).strip().strip('"')
        train_job_id = str(data.get("train_job_id", "")).strip()
        run_name = ""
        if not weights and train_job_id:
            job = jobs.get_job(train_job_id)
            facts = (job or {}).get("facts") or {}
            weights = str(facts.get("weights", ""))
            run_name = ((job or {}).get("result") or {}).get("run_name", "")
        if not weights:
            return Response(
                content={"error": "Select a run or provide a weights path."},
                status_code=HTTP_400_BAD_REQUEST,
            )
        if not Path(weights).is_file():
            return Response(
                content={"error": f"Weights file not found: {weights}"},
                status_code=HTTP_400_BAD_REQUEST,
            )
        if not str(data.get("test_table_url", "")).strip():
            return Response(
                content={"error": "Missing required field 'test_table_url'"},
                status_code=HTTP_400_BAD_REQUEST,
            )

        params = dict(data)
        params["weights_path"] = weights
        if run_name:
            params.setdefault("run_name", run_name)
        job_id = jobs.start_job("predict_submit", params, predictor.run_predict_submit)
        return Response(content={"job_id": job_id}, status_code=200)

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
        """Last-used form values per tab (re-runs become one click)."""
        from tlc_plugin_kaggle import config_store

        return config_store.load()

    @post("/config", sync_to_thread=True)
    def save_config(self, data: dict[str, Any]) -> dict[str, Any]:
        """Merge per-tab form snapshots. Body: {"train": {...}} etc."""
        from tlc_plugin_kaggle import config_store

        if not isinstance(data, dict):
            return {}
        return config_store.save(data)

    @get("/pipeline", sync_to_thread=True)
    def pipeline_state(self, project: str = "exdark-competition") -> dict[str, Any]:
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
        submit_done = any(
            j.get("kind") == "predict_submit" and j.get("status") == "completed" for j in all_jobs
        )
        return {"import": import_done, "train": train_done, "submit": submit_done}
