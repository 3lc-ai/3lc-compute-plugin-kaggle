"""Kaggle competition plugin for the 3LC Hub.

Four-card workflow: Import / Train / Predict + Submit / Status.
Session 1: Import is fully functional; the other cards are stubs.

Installed-host (tlc_compute 0.1.1.47) plugin: the manifest is these class
attributes — the [tool.tlc-compute] table in pyproject.toml is a hand-synced
copy for the future catalog/venv host and is never read by this host.
"""

from pathlib import Path
from typing import Any

from tlc_compute.plugins.base import ComputePlugin, _ICON_SVG
from tlc_compute.plugins.registry import register


class KagglePlugin(ComputePlugin):
    id = "kaggle"
    name = "Kaggle Competition"
    description = (
        "End-to-end Kaggle competition workflow: import the dataset, train the "
        "fixed baseline (YOLOv11n from scratch @ 640), predict and submit."
    )
    version = "0.1.0"
    min_service_version = "0.1.0"
    icon = "🏁"
    icon_svg = _ICON_SVG + '><path d="M3 14V2.5"/><path d="M3 3h9l-2 2.5L12 8H3"/></svg>'
    display_mode = "sidebar"
    section = "AI Tools"
    priority = 40
    compatible_with = ["table"]
    output_types = ["run"]
    repository_url = "https://github.com/3lc-ai/3lc-compute-plugin-kaggle"
    # Import is CPU-only; training (session 2) will move long GPU work onto the
    # shared GPU queue rather than flipping this flag, so the Import card stays
    # usable while other GPU plugins run.
    requires_gpu = False
    training = True

    _ui_cache: str | None = None

    def get_ui_fragment(self) -> str:
        if self._ui_cache is None:
            ui_path = Path(__file__).resolve().parent / "ui.html"
            self._ui_cache = ui_path.read_text(encoding="utf-8")
        return self._ui_cache

    def compute(self, params: dict[str, Any]) -> dict[str, Any]:
        """Generic info endpoint — real work goes through the custom routes."""
        return {
            "plugin": self.id,
            "version": self.version,
            "cards": ["import", "train", "predict_submit", "status"],
            "implemented": ["import"],
        }

    def get_route_handlers(self) -> list[Any]:
        from tlc_plugin_kaggle.routes import KaggleController

        return [KaggleController]

    def get_active_jobs(self, project_name: str = "") -> list[dict[str, Any]]:
        from tlc_plugin_kaggle.jobs import active_jobs_generic

        return active_jobs_generic(project_name)


register(KagglePlugin())
