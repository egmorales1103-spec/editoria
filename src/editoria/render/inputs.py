"""Discover the render inputs written by the other modules inside a version folder."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

from editoria.render.geometry import base_for, face_box_source, scale_face
from editoria.render.media import probe_media
from editoria.schemas import Box, Canvas, ConformedClip, EditPlan, OverlayClip, RenderInputs
from editoria.util import resources
from editoria.util.geometry import zone_box
from editoria.util.log import warn
from editoria.util.project import ProjectContext

CAPTIONS_ASS = "subtitulos.ass"
OVERLAYS_JSON = Path("graficos") / "overlays.json"
MIX_WAV = Path("audio") / "mezcla.wav"
EMOJI_SIZE = 200  # px on a 1080-wide canvas


def _resolve(p: Path, root: Path) -> Path:
    return p if p.is_absolute() else root / p


def load_overlays(vdir: Path) -> list[OverlayClip]:
    path = vdir / OVERLAYS_JSON
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    raw = data.get("overlays", []) if isinstance(data, dict) else data
    clips = [OverlayClip.model_validate(item) for item in raw]
    return [
        c.model_copy(update={"frames_pattern": _resolve(Path(c.frames_pattern), path.parent)})
        for c in clips
    ]


def emoji_overlays(plan: EditPlan, known: set[str], canvas: Canvas) -> list[OverlayClip]:
    """OverlayClips for plan emojis that no other module already provided."""
    out: list[OverlayClip] = []
    size = round(EMOJI_SIZE * canvas.width / 1080)
    for item in plan.graphics:
        if not item.is_emoji or item.id in known:
            continue
        gif = resources.emoji_path(str(item.emoji))
        if not gif.is_file():
            warn(f"Falta el emoji {item.emoji} ({gif}); se omite {item.id}.")
            continue
        box = zone_box(item.zone, canvas, size, size)
        out.append(
            OverlayClip(
                id=item.id,
                frames_pattern=gif,
                x=box.x,
                y=box.y,
                w=box.w,
                h=box.h,
                start=item.in_,
                end=item.out,
                is_gif=True,
            )
        )
    return out


def accepted_shots(ctx: ProjectContext) -> dict[str, ConformedClip]:
    """Accepted shots from the shots module when available; none otherwise."""
    try:
        library_cls = getattr(importlib.import_module("editoria.shots"), "ProjectShotLibrary", None)
    except ImportError:
        return {}
    if library_cls is None:
        return {}
    try:
        shots: dict[str, ConformedClip] = dict(library_cls().accepted(ctx))
    except Exception as exc:  # the shots module is optional for rendering
        warn(f"No se pudieron leer las tomas aceptadas: {exc}")
        return {}
    return shots


def face_box_canvas(ctx: ProjectContext, canvas: Canvas) -> Box | None:
    face = ctx.load_face()
    if face is None:
        return None
    try:
        base = probe_media(ctx.original_video())
        w, h = base.width, base.height
    except Exception:
        w, h = face.frame_w, face.frame_h
    face = scale_face(face, w, h)
    fb = face_box_source(face)
    if fb is None:
        return None
    return base_for(w, h, canvas, face).to_canvas(fb)


def inputs_from_version(ctx: ProjectContext, version: str) -> RenderInputs:
    """Build RenderInputs from the files inside ``04_versiones/<version>/``.

    Missing pieces are skipped with a warning (captions, graphics, mix, shots).
    """
    vdir = ctx.version_dir(version)
    plan = ctx.load_plan(version)
    canvas = plan.canvas

    ass = vdir / CAPTIONS_ASS
    if not ass.is_file():
        if plan.captions.enabled:
            warn(f"No hay {CAPTIONS_ASS} en {version}: el render sale sin subtítulos.")
        ass_path: Path | None = None
    else:
        ass_path = ass

    overlays = load_overlays(vdir)
    if not overlays and any(not g.is_emoji for g in plan.graphics):
        warn(f"No hay {OVERLAYS_JSON.as_posix()} en {version}: el render sale sin gráficos.")
    overlays += emoji_overlays(plan, {o.id for o in overlays}, canvas)

    mix = vdir / MIX_WAV
    if not mix.is_file():
        warn(f"No hay {MIX_WAV.as_posix()} en {version}: se usa el audio del VIDEO_BASE.")

    fonts = resources.fonts_dir()
    shots = accepted_shots(ctx) if any(iv.method == "generated" for iv in plan.video) else {}
    return RenderInputs(
        captions_ass=ass_path,
        fonts_dir=fonts if fonts.is_dir() else None,
        overlays=overlays,
        mix_wav=mix if mix.is_file() else None,
        shots=shots,
        face_box_canvas=face_box_canvas(ctx, canvas),
    )
