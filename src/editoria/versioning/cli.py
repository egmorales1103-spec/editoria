"""version new / feedback parse (owner: A1)."""

from __future__ import annotations

from pathlib import Path

import typer

from editoria.util.cli import pending

version_app = typer.Typer(help="Versiones inmutables (V1, V2, ...).", no_args_is_help=True)
feedback_app = typer.Typer(help="Feedback con tiempos.", no_args_is_help=True)


def register(app: typer.Typer) -> None:
    @version_app.command("new")
    def version_new(
        slug: str = typer.Argument(...),
        from_: str = typer.Option("V1", "--from", help="Versión de origen."),
    ) -> None:
        """Crea la versión siguiente a partir de otra (exige feedback parseado)."""
        pending("version new")

    @feedback_app.command("parse")
    def feedback_parse(
        slug: str = typer.Argument(...),
        file: Path = typer.Argument(..., help="Feedback_V1.md completado."),
        version: str = typer.Option("V1", "--version"),
    ) -> None:
        """Convierte la tabla de feedback en FeedbackItem[] (feedback.json)."""
        pending("feedback parse")

    app.add_typer(version_app, name="version")
    app.add_typer(feedback_app, name="feedback")
