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

        params = {
            "dataset_yaml": str(data["dataset_yaml"]).strip(),
            "project_name": str(data.get("project_name") or "exdark-competition").strip(),
            "table_name": str(data.get("table_name") or "initial").strip(),
        }
        job_id = jobs.start_job("import", params, importer.run_import)
        return Response(content={"job_id": job_id}, status_code=200)

    @get("/jobs/{job_id:str}")
    async def job_status(self, job_id: str) -> dict[str, Any]:
        from tlc_plugin_kaggle import jobs

        job = jobs.get_job(job_id)
        if job is None:
            raise NotFoundException(detail=f"No such job: {job_id}")
        return job
