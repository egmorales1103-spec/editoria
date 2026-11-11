"""graphics list / preview / render (owner: A3)."""

from __future__ import annotations

import typer

from editoria.util.cli import pending

graphics_app = typer.Typer(help="Motion graphics desde plantillas HTML/CSS.", no_args_is_help=True)


def register(app: typer.Typer) -> None:
    @graphics_app.command("list")
    def graphics_list() -> None:
        """Lista las plantillas disponibles."""
        pending("graphics list")

    @graphics_app.command("preview")
    def graphics_preview(
        template: str = typer.Argument(...),
        params: str = typer.Option("{}", "--params", help="JSON de parámetros."),
    ) -> None:
        """PNG del cuadro medio + MP4 corto sobre gris."""
        pending("graphics preview")

    @graphics_app.command("render")
    def graphics_render(
        slug: str = typer.Argument(...),
        version: str = typer.Option("V1", "--version"),
    ) -> None:
        """Renderiza los gráficos del plan a secuencias PNG con alfa."""
        pending("graphics render")

    app.add_typer(graphics_app, name="graphics")
