"""init / probe / transcribe (owner: A1)."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.table import Table

from editoria.ingest.errors import IngestError
from editoria.ingest.probe import has_corruption, probe_project
from editoria.ingest.transcribe import DEFAULT_MODEL, transcribe_project
from editoria.ingest.workspace import init_project, slugify, validate_video
from editoria.util.cli import fail, open_project
from editoria.util.log import console, info, ok, warn


def register(app: typer.Typer) -> None:
    @app.command("init")
    def init_cmd(
        video: Path | None = typer.Argument(
            None, help="VIDEO_BASE (exportación recortada en CapCut)."
        ),
        slug: str | None = typer.Option(
            None, "--slug", help="Identificador del proyecto (por defecto, el nombre del archivo)."
        ),
        brand: str = typer.Option("master-solution", "--brand", help="Marca (brands/<slug>)."),
    ) -> None:
        """Crea el espacio de trabajo y copia el original con hash, en solo lectura."""
        try:
            src = validate_video(video)
            final_slug = slug or slugify(src.stem)
            ctx = init_project(src, final_slug, brand)
        except IngestError as exc:
            fail(str(exc))
        cfg = ctx.load_config()
        ok(f"Proyecto '{ctx.slug}' creado en {ctx.root}")
        info(f"Original copiado (no movido): {ctx.root / cfg.original}")
        info(f"sha256: {cfg.original_sha256}")
        info(f"Siguiente paso: editoria probe {ctx.slug}")

    @app.command("probe")
    def probe_cmd(slug: str = typer.Argument(...)) -> None:
        """Metadatos, integridad y avisos del VIDEO_BASE."""
        ctx = open_project(slug)
        try:
            res = probe_project(ctx)
        except Exception as exc:  # ffmpeg errors are reported, not shown as tracebacks
            fail(f"No se pudo analizar el video: {exc}")
        table = Table(show_header=False, box=None)
        for key, val in (
            ("Duración", f"{res.duration_s:.2f} s"),
            ("Resolución", f"{res.display_width}x{res.display_height}"),
            ("FPS", f"{res.fps}{' (variable)' if res.vfr else ''}"),
            ("Video", f"{res.video_codec} {res.pix_fmt}"),
            (
                "Audio",
                f"{res.audio.codec} {res.audio.sr} Hz, {res.audio.ch} canal(es)"
                if res.audio
                else "sin audio",
            ),
        ):
            table.add_row(key, val)
        console.print(table)
        for w in res.warnings:
            warn(w)
        if has_corruption(res):
            fail("El archivo parece dañado; revisá los avisos antes de seguir.")
        ok(f"Datos guardados en {ctx.analysis('probe.json')}")

    @app.command("transcribe")
    def transcribe_cmd(
        slug: str = typer.Argument(...),
        model: str = typer.Option(DEFAULT_MODEL, "--model", help="large-v3-turbo | small | ..."),
        backend: str = typer.Option("whisper", "--backend", help="whisper | fixture"),
        force: bool = typer.Option(False, "--force", help="Ignora la caché de transcripción."),
    ) -> None:
        """Transcripción con tiempos por palabra; marca las palabras dudosas."""
        ctx = open_project(slug)
        try:
            tr = transcribe_project(ctx, model=model, backend=backend, force=force)
        except IngestError as exc:
            fail(str(exc))
        flagged = sum(1 for w in tr.words if w.flagged)
        ok(f"{len(tr.words)} palabras transcritas con '{tr.model}'; {flagged} dudosa(s).")
        if flagged:
            warn(f"Revisá las palabras marcadas en {ctx.analysis('transcript_revision.md')}")
        else:
            info(f"Revisión: {ctx.analysis('transcript_revision.md')}")
