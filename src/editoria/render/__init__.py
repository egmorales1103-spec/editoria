"""render module: compositor (FFmpegRenderer), input discovery and contact sheets (A5)."""

from editoria.render.contact import CONTACT_SHEET_FILE, contact_sheet, sheet_marks
from editoria.render.filtergraph import RenderError, RenderGraph, build_render_graph
from editoria.render.geometry import ZoomGuardError, face_boxes_on_canvas, zoom_violation
from editoria.render.inputs import inputs_from_version
from editoria.render.media import MediaInfo, probe_media
from editoria.render.renderer import FILTERGRAPH_FILE, FFmpegRenderer

__all__ = [
    "CONTACT_SHEET_FILE",
    "FILTERGRAPH_FILE",
    "FFmpegRenderer",
    "MediaInfo",
    "RenderError",
    "RenderGraph",
    "ZoomGuardError",
    "build_render_graph",
    "contact_sheet",
    "face_boxes_on_canvas",
    "inputs_from_version",
    "probe_media",
    "sheet_marks",
    "zoom_violation",
]
