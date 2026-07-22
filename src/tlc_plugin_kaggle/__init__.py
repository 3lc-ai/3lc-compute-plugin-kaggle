"""Kaggle competition plugin for the 3LC Hub.

Tabbed workflow: Import / Train / Submit / Status — the tab bar doubles as
the pipeline stepper. All four tabs are functional end-to-end.

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
    # Sidebar identity: one line at sidebar width ("Kaggle Competition"
    # wrapped over two lines next to one-word siblings). The full name
    # leads the description (the only hover-text candidate the manifest
    # offers — there is no dedicated tooltip field); the card header
    # inside the fragment keeps "Kaggle Competition".
    name = "Kaggle"
    description = (
        "Kaggle Competition: import the dataset, train the fixed baseline "
        "(YOLOv11n, pinned COCO-pretrained init @ 640), predict and submit. "
        "The whole competition loop without leaving the Hub."
    )
    version = "1.1.0"
    min_service_version = "0.1.0"
    icon = "🏁"  # host fallback when icon_svg is unsupported
    # Same flag as the fragment's header identity icon (16px grid, 1.5px
    # stroke, currentColor) — two strokes only, stays crisp at 16px.
    icon_svg = _ICON_SVG + '><path d="M3.5 14V2.5"/><path d="M3.5 3h8.5l-1.8 2.5L12 8H3.5"/></svg>'
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
            "tabs": ["import", "train", "submit", "status"],
            "implemented": ["import", "train", "predict_submit", "status"],
        }

    def get_route_handlers(self) -> list[Any]:
        from tlc_plugin_kaggle.routes import KaggleController

        return [KaggleController]

    def get_active_jobs(self, project_name: str = "") -> list[dict[str, Any]]:
        from tlc_plugin_kaggle.jobs import active_jobs_generic

        return active_jobs_generic(project_name)


register(KagglePlugin())
