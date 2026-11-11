"""Motion graphics: HTML/CSS templates rendered to RGBA PNG sequences (owner: A3)."""

from editoria.graphics.plan import (
    GRAPHICS_DIR,
    OVERLAYS_FILE,
    graphics_dir,
    project_fps,
    render_plan_graphics,
)
from editoria.graphics.preview import PreviewResult, preview_template
from editoria.graphics.renderer import (
    CHROMIUM_MISSING_MSG,
    FRAME_PATTERN,
    FRAME_START,
    GraphicsUnavailable,
    PlaywrightGraphicsRenderer,
    RenderStats,
    chromium_available,
    frame_count,
)
from editoria.graphics.templates import (
    GraphicsError,
    GraphicsParamsError,
    GraphicTemplate,
    TemplateMeta,
    TemplateNotFound,
    list_templates,
    load_template,
)

__all__ = [
    "CHROMIUM_MISSING_MSG",
    "FRAME_PATTERN",
    "FRAME_START",
    "GRAPHICS_DIR",
    "OVERLAYS_FILE",
    "GraphicTemplate",
    "GraphicsError",
    "GraphicsParamsError",
    "GraphicsUnavailable",
    "PlaywrightGraphicsRenderer",
    "PreviewResult",
    "RenderStats",
    "TemplateMeta",
    "TemplateNotFound",
    "chromium_available",
    "frame_count",
    "graphics_dir",
    "list_templates",
    "load_template",
    "preview_template",
    "project_fps",
    "render_plan_graphics",
]
