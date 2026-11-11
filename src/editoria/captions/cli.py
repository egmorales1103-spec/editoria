"""captions build (owner: A2)."""

from __future__ import annotations

import typer

from editoria.util.cli import pending

captions_app = typer.Typer(help="Subtítulos ASS/SRT/VTT.", no_args_is_help=True)


def register(app: typer.Typer) -> None:
    @captions_app.command("build")
    def captions_build(
        slug: str = typer.Argument(...),
        version: str = typer.Option("V1", "--version"),
    ) -> None:
        """Genera subtitulos.ass, .srt y .vtt para una versión."""
        pending("captions build")

    app.add_typer(captions_app, name="captions")
