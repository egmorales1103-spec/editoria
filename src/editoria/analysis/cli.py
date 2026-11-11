"""analyze (owner: A1)."""

from __future__ import annotations

import typer

from editoria.util.cli import pending


def register(app: typer.Typer) -> None:
    @app.command("analyze")
    def analyze_cmd(slug: str = typer.Argument(...)) -> None:
        """Silencios, cortes, zona de rostro, segmentos y mapa de edición."""
        pending("analyze")
