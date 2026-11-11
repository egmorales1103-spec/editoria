"""propose / run: end-to-end orchestration (owner: lead, Ola 2)."""

from __future__ import annotations

import typer

from editoria.util.cli import pending


def register(app: typer.Typer) -> None:
    @app.command("propose")
    def propose_cmd(
        slug: str = typer.Argument(...),
        window: str | None = typer.Option(None, "--window", help="a-b en segundos"),
    ) -> None:
        """Tres muestras A/B/C sobre el mismo pasaje + comparativa."""
        pending("propose")

    @app.command("run")
    def run_cmd(slug: str = typer.Argument(...)) -> None:
        """Punta a punta; se detiene siempre tras V1."""
        pending("run")
