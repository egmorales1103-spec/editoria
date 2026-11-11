"""plan draft / plan lint (owner: A2)."""

from __future__ import annotations

from pathlib import Path

import typer

from editoria.util.cli import pending

plan_app = typer.Typer(help="Plan declarativo de edición (plan.yaml).", no_args_is_help=True)


def register(app: typer.Typer) -> None:
    @plan_app.command("draft")
    def plan_draft(
        slug: str = typer.Argument(...),
        style: str = typer.Option("A", "--style", help="A | B | C"),
        out: Path | None = typer.Option(None, "--out"),
    ) -> None:
        """Borrador automático del plan para un estilo."""
        pending("plan draft")

    @plan_app.command("lint")
    def plan_lint(
        slug: str = typer.Argument(...),
        plan: Path | None = typer.Option(None, "--plan"),
        version: str = typer.Option("V1", "--version"),
    ) -> None:
        """Linter de políticas; código distinto de 0 si hay ERROR."""
        pending("plan lint")

    app.add_typer(plan_app, name="plan")
