"""qc (owner: A5)."""

from __future__ import annotations

import typer

from editoria.util.cli import pending


def register(app: typer.Typer) -> None:
    @app.command("qc")
    def qc_cmd(
        slug: str = typer.Argument(...),
        version: str = typer.Option("V1", "--version"),
    ) -> None:
        """Control de calidad automático (PASS/WARN/FAIL/REVISIÓN HUMANA)."""
        pending("qc")
