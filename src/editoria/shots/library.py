"""ProjectShotLibrary: the render-facing view of the registry (only accepted shots)."""

from __future__ import annotations

from editoria.schemas import ConformedClip
from editoria.shots import registry
from editoria.shots.media import video_info
from editoria.util.log import warn
from editoria.util.project import ProjectContext


class ProjectShotLibrary:
    """Implements ``editoria.contracts.ShotLibrary``."""

    def accepted(self, ctx: ProjectContext) -> dict[str, ConformedClip]:
        """Shots with verdict 'aceptado' whose conformed, silent file exists."""
        out: dict[str, ConformedClip] = {}
        for rec in registry.load_registry(ctx):
            if rec.veredicto != "aceptado":
                continue
            path = ctx.root / rec.archivo_resultado if rec.archivo_resultado else None
            if path is None or not path.is_file():
                warn(f"La toma {rec.id} está aceptada pero falta su archivo; se omite.")
                continue
            info = video_info(path)
            if info.has_audio:
                warn(f"La toma {rec.id} tiene audio; se omite (P03). Reimportala.")
                continue
            out[rec.id] = ConformedClip(
                shot_id=rec.id,
                path=path,
                start=float(rec.entrada),
                end=float(rec.salida),
                width=info.width,
                height=info.height,
            )
        return out
