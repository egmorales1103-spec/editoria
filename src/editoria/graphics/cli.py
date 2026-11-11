"""graphics list / preview / render (owner: A3)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast, get_args

import typer
from rich.table import Table

from editoria.schemas import BrandProfile, Zone, parse_fps
from editoria.util import resources
from editoria.util.cli import command_log, fail, open_project
from editoria.util.ffmpeg import FFmpegError, FFmpegNotFound
from editoria.util.log import console, info, ok, warn

graphics_app = typer.Typer(help="Motion graphics desde plantillas HTML/CSS.", no_args_is_help=True)

EXIT_UNAVAILABLE = 2


def _parse_params(text: str) -> dict[str, Any]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        fail(f"--params no es un JSON válido: {exc.msg} (posición {exc.pos}).")
    if not isinstance(data, dict):
        fail('--params debe ser un objeto JSON, p. ej. \'{"texto": "Hola"}\'.')
    return data


def _parse_zone(value: str | None) -> Zone | None:
    if value is None:
        return None
    allowed = get_args(Zone)
    if value not in allowed:
        fail(f"Zona inválida '{value}'. Opciones: {', '.join(allowed)}.")
    return cast(Zone, value)


def _load_brand(slug: str) -> BrandProfile:
    try:
        return resources.load_brand(slug)
    except FileNotFoundError:
        warn(f"No existe la marca '{slug}'; se usan los colores por defecto.")
        return BrandProfile(name=slug)


def register(app: typer.Typer) -> None:
    from editoria.graphics.plan import OVERLAYS_FILE, graphics_dir, render_plan_graphics
    from editoria.graphics.preview import preview_template
    from editoria.graphics.renderer import GraphicsUnavailable, RenderStats
    from editoria.graphics.templates import GraphicsError, list_templates, load_template

    @graphics_app.command("list")
    def graphics_list() -> None:
        """Lista las plantillas disponibles."""
        metas = list_templates()
        if not metas:
            fail(f"No hay plantillas en {resources.graphics_templates_dir()}.")
        table = Table(title="Plantillas de gráficos", show_lines=False)
        table.add_column("id", no_wrap=True, style="bold")
        for col in ("tamaño", "duración", "zonas", "sfx", "etiquetas"):
            table.add_column(col)
        for m in metas:
            zonas = "x, y (0–1)" if m.ubicacion == "punto" else ", ".join(m.zonas)
            etiquetas = ", ".join(m.etiquetas_obligatorias)
            if m.id == "dato_grafico":
                etiquetas = "Ejemplo (data_source: ejemplo)"
            table.add_row(
                m.id,
                f"{m.width}×{m.height}",
                f"{m.duracion_s:g} s",
                zonas,
                m.sfx_sugerido or "-",
                etiquetas or "-",
            )
        console.print(table)

    @graphics_app.command("preview")
    def graphics_preview(
        template: str = typer.Argument(..., help="Id de la plantilla (ver 'graphics list')."),
        params: str = typer.Option(
            "{}", "--params", help="JSON de parámetros. Vacío = parámetros de ejemplo."
        ),
        out: Path | None = typer.Option(
            None, "--out", help="Carpeta de salida (por defecto ./vista_previa/<plantilla>)."
        ),
        marca: str = typer.Option("master-solution", "--marca", help="Marca de brands/."),
        fps: str = typer.Option("30", "--fps", help="Cuadros por segundo (30, 30000/1001…)."),
        duracion: float | None = typer.Option(
            None, "--duracion", help="Segundos (por defecto, la duración de la plantilla)."
        ),
        zona: str | None = typer.Option(None, "--zona", help="Zona del lienzo."),
    ) -> None:
        """PNG del cuadro medio + MP4 corto sobre gris."""
        try:
            tpl = load_template(template)
        except GraphicsError as exc:
            fail(str(exc))
        values = _parse_params(params) or tpl.example_params()
        target = out or Path.cwd() / "vista_previa" / template
        try:
            res = preview_template(
                template,
                values,
                target,
                brand=_load_brand(marca),
                fps=parse_fps(fps),
                duration=duracion,
                zone=_parse_zone(zona),
            )
        except GraphicsUnavailable as exc:
            fail(str(exc), code=EXIT_UNAVAILABLE)
        except (GraphicsError, FFmpegError, FFmpegNotFound) as exc:
            fail(str(exc))
        ok(f"Cuadro medio: {res.mid_png}")
        ok(f"Video de muestra: {res.mp4}")
        info(
            f"{res.clip.frame_count} cuadros a {res.clip.fps} fps · "
            f"{res.ms_per_frame:.0f} ms por cuadro · etiquetas: {', '.join(res.clip.labels) or '-'}"
        )

    @graphics_app.command("render")
    def graphics_render(
        slug: str = typer.Argument(..., help="Proyecto (carpeta en proyectos/)."),
        version: str = typer.Option("V1", "--version", help="Versión (V1, V2…)."),
    ) -> None:
        """Renderiza los gráficos del plan a secuencias PNG con alfa."""
        ctx = open_project(slug)
        stats: list[RenderStats] = []
        try:
            with command_log(ctx.commands_log):
                clips = render_plan_graphics(ctx, version, stats=stats)
        except GraphicsUnavailable as exc:
            fail(str(exc), code=EXIT_UNAVAILABLE)
        except (GraphicsError, FileNotFoundError, ValueError) as exc:
            fail(str(exc))
        for clip, st in zip(clips, stats, strict=False):
            how = "caché" if st.cached else f"{st.ms_per_frame:.0f} ms/cuadro"
            labels = f" · etiquetas: {', '.join(clip.labels)}" if clip.labels else ""
            info(
                f"  {clip.id}: {st.template} · {clip.frame_count} cuadros · "
                f"{clip.w}×{clip.h} en ({clip.x}, {clip.y}) · {how}{labels}"
            )
        ok(
            f"{len(clips)} gráfico(s) renderizado(s) en {graphics_dir(ctx, version)} "
            f"({OVERLAYS_FILE} actualizado)."
        )

    app.add_typer(graphics_app, name="graphics")


__all__ = ["EXIT_UNAVAILABLE", "graphics_app", "register"]
