"""render / contact-sheet (owner: A5)."""

from __future__ import annotations

import typer

from editoria.util.cli import pending


def register(app: typer.Typer) -> None:
    @app.command("render")
    def render_cmd(
        slug: str = typer.Argument(...),
        version: str = typer.Option("V1", "--version"),
        sample_window: str | None = typer.Option(None, "--sample-window", help="a-b en segundos"),
        preset: str = typer.Option("medium", "--preset"),
        crf: int = typer.Option(18, "--crf"),
    ) -> None:
        """Compone y exporta el MP4 de una versión."""
        pending("render")

    @app.command("contact-sheet")
    def contact_sheet_cmd(
        slug: str = typer.Argument(...),
        version: str = typer.Option("V1", "--version"),
        every: float = typer.Option(2.0, "--every"),
    ) -> None:
        """Hoja de contactos de una versión."""
        pending("contact-sheet")
