"""version new / feedback parse (owner: A1)."""

from __future__ import annotations

from pathlib import Path

import typer

from editoria.ingest.errors import IngestError
from editoria.util.cli import fail, open_project
from editoria.util.log import info, ok
from editoria.versioning.feedback import parse_feedback, save_feedback
from editoria.versioning.versions import new_version

version_app = typer.Typer(help="Versiones inmutables (V1, V2, ...).", no_args_is_help=True)
feedback_app = typer.Typer(help="Feedback con tiempos.", no_args_is_help=True)


def register(app: typer.Typer) -> None:
    @version_app.command("new")
    def version_new(
        slug: str = typer.Argument(...),
        from_: str = typer.Option("V1", "--from", help="Versión de origen."),
    ) -> None:
        """Crea la versión siguiente a partir de otra (exige feedback parseado)."""
        ctx = open_project(slug)
        try:
            new = new_version(ctx, from_)
        except IngestError as exc:
            fail(str(exc))
        ok(f"Creada {new} a partir de {from_}: {ctx.version_dir(new) / 'plan.yaml'}")
        info("Aplicá los cambios del feedback en el plan y no toques las versiones anteriores.")

    @feedback_app.command("parse")
    def feedback_parse(
        slug: str = typer.Argument(...),
        file: Path = typer.Argument(..., help="Feedback_V1.md completado."),
        version: str = typer.Option("V1", "--version"),
        force: bool = typer.Option(False, "--force", help="Reemplaza un feedback.json existente."),
    ) -> None:
        """Convierte la tabla de feedback en FeedbackItem[] (feedback.json)."""
        ctx = open_project(slug)
        try:
            feedback = parse_feedback(file, version)
            out = save_feedback(ctx, feedback, force=force)
        except IngestError as exc:
            fail(str(exc))
        ok(f"{len(feedback.items)} cambio(s) con tiempo guardados en {out}")

    app.add_typer(version_app, name="version")
    app.add_typer(feedback_app, name="feedback")
