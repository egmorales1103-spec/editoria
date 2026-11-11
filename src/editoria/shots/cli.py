"""shots pack / import / compare / verdict / budget (owner: A6)."""

from __future__ import annotations

from pathlib import Path

import typer

from editoria.util.cli import pending

shots_app = typer.Typer(help="Tomas complementarias (Higgsfield).", no_args_is_help=True)


def register(app: typer.Typer) -> None:
    @shots_app.command("pack")
    def shots_pack(
        slug: str = typer.Argument(...),
        start: float = typer.Option(..., "--in"),
        end: float = typer.Option(..., "--out"),
        change: str = typer.Option(..., "--cambio", help="Cambio de encuadre pedido."),
    ) -> None:
        """Prepara segmento, anclas y prompt para Higgsfield."""
        pending("shots pack")

    @shots_app.command("import")
    def shots_import(
        slug: str = typer.Argument(...),
        shot_id: str = typer.Argument(...),
        file: Path = typer.Argument(...),
    ) -> None:
        """Valida y conforma un resultado; quita el audio."""
        pending("shots import")

    @shots_app.command("compare")
    def shots_compare(slug: str = typer.Argument(...), shot_id: str = typer.Argument(...)) -> None:
        """Hoja comparativa y métricas de deriva del fondo."""
        pending("shots compare")

    @shots_app.command("verdict")
    def shots_verdict(
        slug: str = typer.Argument(...),
        shot_id: str = typer.Argument(...),
        verdict: str = typer.Argument(..., help="aceptado | reintentar | descartado"),
        motivo: str = typer.Option(..., "--motivo"),
    ) -> None:
        """Única vía para aceptar una toma."""
        pending("shots verdict")

    @shots_app.command("budget")
    def shots_budget(slug: str = typer.Argument(...)) -> None:
        """Límite, gastado y restante de créditos."""
        pending("shots budget")

    app.add_typer(shots_app, name="shots")
