"""deliver: V1 package (owner: lead, Ola 2)."""

from __future__ import annotations

import typer

from editoria.util.cli import pending


def register(app: typer.Typer) -> None:
    @app.command("deliver")
    def deliver_cmd(
        slug: str = typer.Argument(...),
        version: str = typer.Option("V1", "--version"),
    ) -> None:
        """Arma el paquete de entrega separando lo ejecutado de lo pendiente."""
        pending("deliver")
