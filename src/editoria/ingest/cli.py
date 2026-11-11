"""init / probe / transcribe (owner: A1)."""

from __future__ import annotations

from pathlib import Path

import typer

from editoria.util.cli import pending


def register(app: typer.Typer) -> None:
    @app.command("init")
    def init_cmd(
        video: Path = typer.Argument(..., help="VIDEO_BASE (exportación recortada en CapCut)."),
        slug: str = typer.Option(..., "--slug", help="Identificador del proyecto."),
        brand: str = typer.Option("master-solution", "--brand", help="Marca (brands/<slug>)."),
    ) -> None:
        """Crea el espacio de trabajo y copia el original con hash, en solo lectura."""
        pending("init")

    @app.command("probe")
    def probe_cmd(slug: str = typer.Argument(...)) -> None:
        """Metadatos, integridad y avisos del VIDEO_BASE."""
        pending("probe")

    @app.command("transcribe")
    def transcribe_cmd(
        slug: str = typer.Argument(...),
        model: str = typer.Option("large-v3-turbo", "--model"),
        backend: str = typer.Option("whisper", "--backend", help="whisper | fixture"),
    ) -> None:
        """Transcripción con tiempos por palabra; marca las palabras dudosas."""
        pending("transcribe")
