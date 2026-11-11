"""render / contact-sheet (owner: A5)."""

from __future__ import annotations

import typer

from editoria.util.cli import command_log, fail, open_project
from editoria.util.ffmpeg import FFmpegError, FFmpegNotFound
from editoria.util.log import info, ok, warn
from editoria.util.project import VIDEO_FILE


def parse_window(text: str) -> tuple[float, float]:
    """'a-b' (seconds) -> (a, b)."""
    try:
        a_s, b_s = text.split("-", 1)
        a, b = float(a_s.strip().replace(",", ".")), float(b_s.strip().replace(",", "."))
    except ValueError as exc:
        raise ValueError(f"Ventana inválida '{text}': usá el formato a-b en segundos.") from exc
    if not 0 <= a < b:
        raise ValueError(f"Ventana inválida '{text}': se necesita 0 ≤ a < b.")
    return a, b


def register(app: typer.Typer) -> None:
    @app.command("render")
    def render_cmd(
        slug: str = typer.Argument(...),
        version: str = typer.Option("V1", "--version"),
        sample_window: str | None = typer.Option(None, "--sample-window", help="a-b en segundos"),
        preset: str | None = typer.Option(
            None, "--preset", help="Preset de x264 (medium; veryfast para muestras)."
        ),
        crf: int = typer.Option(18, "--crf"),
    ) -> None:
        """Compone y exporta el MP4 de una versión."""
        from editoria.render.filtergraph import RenderError
        from editoria.render.inputs import inputs_from_version
        from editoria.render.renderer import FFmpegRenderer
        from editoria.schemas import EncodeSettings

        ctx = open_project(slug)
        try:
            vdir = ctx.version_dir(version)
        except ValueError as exc:
            fail(str(exc))
        if not (vdir / "plan.yaml").is_file():
            fail(f"No existe plan.yaml en {version}.")
        window = None
        if sample_window:
            try:
                window = parse_window(sample_window)
            except ValueError as exc:
                fail(str(exc))
        if window is None:
            out = vdir / VIDEO_FILE
        else:
            out = vdir / f"muestra_{window[0]:g}-{window[1]:g}.mp4"
        if ctx.is_delivered(version) and out.exists():
            fail(f"{version} ya fue entregada: {out.name} es inmutable. Creá una versión nueva.")
        enc = EncodeSettings(
            preset=preset or ("veryfast" if window else "medium"), crf=crf, sample_window=window
        )
        with command_log(ctx.commands_log):
            try:
                plan = ctx.load_plan(version)
                inputs = inputs_from_version(ctx, version)
                renderer = FFmpegRenderer()
                info(f"Renderizando {version} ({enc.preset}, CRF {enc.crf})…")
                path = renderer.render(plan, ctx, inputs, out, enc)
            except (RenderError, ValueError, FileNotFoundError, FFmpegNotFound) as exc:
                fail(str(exc))
            except FFmpegError as exc:
                fail(f"ffmpeg falló durante el render.\n{exc}")
        for w in renderer.warnings:
            warn(w)
        ok(f"Video escrito: {path}")

    @app.command("contact-sheet")
    def contact_sheet_cmd(
        slug: str = typer.Argument(...),
        version: str = typer.Option("V1", "--version"),
        every: float = typer.Option(2.0, "--every"),
    ) -> None:
        """Hoja de contactos de una versión."""
        from editoria.render.contact import contact_sheet

        ctx = open_project(slug)
        with command_log(ctx.commands_log):
            try:
                path = contact_sheet(ctx, version, every)
            except (ValueError, FileNotFoundError, FFmpegNotFound) as exc:
                fail(str(exc))
            except FFmpegError as exc:
                fail(f"ffmpeg falló al armar la hoja de contactos.\n{exc}")
        ok(f"Hoja de contactos: {path}")
