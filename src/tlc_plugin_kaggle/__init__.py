"""Kaggle competition plugin for the 3LC Hub.

Tabbed workflow: Import / Train / Submit / Status — the tab bar doubles as
the pipeline stepper. All four tabs are functional end-to-end.

0.2.x-host (SDK) plugin: behavior-only. The manifest lives in plugin.toml
(read import-free by the host); this class subclasses the SDK's ComputePlugin
and runs out-of-process in the plugin's own provisioned venv (see
docs/ui-notes.md for the worker-model dev loop). Long jobs run through
``run_job`` (the host dispatch channel) so they appear in the Hub's generic
Queue panel, honour host-side cancel, and keep the worker touched for the
supervisor's (future) idle reaper; the disk-backed job store in jobs.py stays
the source of truth the tabs poll.
"""

from pathlib import Path
from typing import Any

from tlc_plugin_sdk import ComputePlugin, JobContext

__version__ = "1.2.0"
REPOSITORY_URL = "https://github.com/3lc-ai/3lc-compute-plugin-kaggle"


class KagglePlugin(ComputePlugin):
    """Behavior class named by plugin.toml's runtime.entrypoint."""

    _ui_cache: str | None = None

    def get_ui_fragment(self) -> str:
        if self._ui_cache is None:
            ui_path = Path(__file__).resolve().parent / "ui.html"
            self._ui_cache = ui_path.read_text(encoding="utf-8")
        return self._ui_cache

    def compute(self, params: dict[str, Any]) -> dict[str, Any]:
        """Generic info endpoint — real work goes through the custom routes."""
        return {
            "plugin": "kaggle",
            "version": __version__,
            "tabs": ["import", "train", "submit", "status"],
            "implemented": ["import", "train", "predict_submit", "status"],
        }

    def get_route_handlers(self) -> list[Any]:
        from tlc_plugin_kaggle.routes import KaggleController

        return [KaggleController]

    def run_job(self, ctx: JobContext) -> None:
        """Host-dispatched job entry (POST /api/plugins/kaggle/run).

        ``ctx.params`` carries ``{"kind": "import" | "train" | "predict" |
        "kaggle_submit" | "predict_submit", ...job params}``. The job runs
        synchronously on the worker's dispatch thread; jobs.run_dispatch
        bridges our disk-backed store (which the tabs poll) to the ctx event
        stream (which feeds the Queue panel and keeps the worker alive).
        """
        from tlc_plugin_kaggle import importer, jobs, predictor, trainer

        targets = {
            "import": importer.run_import,
            "train": trainer.run_training,
            "predict": predictor.run_predict,
            "kaggle_submit": predictor.run_kaggle_submit,
            "predict_submit": predictor.run_predict_submit,
        }
        kind = str(ctx.params.get("kind", "")).strip()
        target = targets.get(kind)
        if target is None:
            msg = f"Unknown job kind: {kind!r}. Expected one of {sorted(targets)}."
            raise ValueError(msg)
        jobs.run_dispatch(kind, dict(ctx.params), target, ctx)
