"""Render every template graphic of a version's plan to ``graficos/<id>/%05d.png``."""

from __future__ import annotations

import json
from fractions import Fraction
from pathlib import Path

from editoria.graphics.renderer import PlaywrightGraphicsRenderer, RenderStats
from editoria.graphics.templates import GraphicsError
from editoria.schemas import Canvas, OverlayClip, to_data
from editoria.util import resources
from editoria.util.log import warn
from editoria.util.project import ProjectContext

GRAPHICS_DIR = "graficos"
OVERLAYS_FILE = "overlays.json"
DEFAULT_FPS = Fraction(30)


def project_fps(ctx: ProjectContext, canvas: Canvas) -> Fraction:
    """Canvas fps; ``source`` resolves through probe.json (30 fps with WARN if missing)."""
    if canvas.fps != "source":
        return canvas.resolve_fps(canvas.fps)
    try:
        return canvas.resolve_fps(ctx.load_probe().fps)
    except (FileNotFoundError, ValueError):
        warn("No se encontró probe.json: los gráficos se renderizan a 30 fps.")
        return DEFAULT_FPS


def graphics_dir(ctx: ProjectContext, version: str) -> Path:
    return ctx.version_dir(version) / GRAPHICS_DIR


def write_overlays(path: Path, clips: list[OverlayClip]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"overlays": [to_data(c) for c in clips]}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def render_plan_graphics(
    ctx: ProjectContext,
    version: str,
    *,
    renderer: PlaywrightGraphicsRenderer | None = None,
    stats: list[RenderStats] | None = None,
) -> list[OverlayClip]:
    """Render the plan items that use a ``template`` (emojis are handled by the lead).

    Writes ``04_versiones/<V>/graficos/<id>/%05d.png`` and ``graficos/overlays.json``.
    ``stats``, when given, receives one :class:`RenderStats` per item.
    """
    if ctx.is_delivered(version):
        raise GraphicsError(
            f"La versión {version} ya fue entregada y es inmutable; creá una nueva con "
            "'editoria version new'."
        )
    plan = ctx.load_plan(version)
    brand = resources.load_brand(plan.brand)
    canvas = plan.canvas
    fps = project_fps(ctx, canvas)
    out_root = graphics_dir(ctx, version)
    items = [g for g in plan.graphics if g.template is not None]
    clips: list[OverlayClip] = []
    own = renderer is None
    r = renderer or PlaywrightGraphicsRenderer()
    try:
        for item in items:
            clips.append(r.render(item, brand, canvas, fps, out_root / item.id))
            if stats is not None and r.last_stats is not None:
                stats.append(r.last_stats)
    finally:
        if own:
            r.close()
    write_overlays(out_root / OVERLAYS_FILE, clips)
    return clips
