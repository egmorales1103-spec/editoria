"""Human-facing rendering of linter findings (Spanish)."""

from __future__ import annotations

from collections.abc import Sequence

from rich.table import Table

from editoria.schemas import Finding
from editoria.util.files import fmt_ts
from editoria.util.log import console


def findings_table(findings: Sequence[Finding], title: str = "Linter de políticas") -> Table:
    table = Table(title=title, show_lines=False)
    table.add_column("Nivel")
    table.add_column("Regla")
    table.add_column("Tiempo")
    table.add_column("Elemento")
    table.add_column("Mensaje", overflow="fold")
    for f in findings:
        level = "[red]ERROR[/red]" if f.severity == "ERROR" else "[yellow]WARN[/yellow]"
        table.add_row(
            level, f.id, fmt_ts(f.t) if f.t is not None else "-", f.element or "-", f.message
        )
    return table


def summary(findings: Sequence[Finding]) -> str:
    errors = sum(1 for f in findings if f.severity == "ERROR")
    warns = len(findings) - errors
    if not findings:
        return "Sin hallazgos: el plan cumple las políticas."
    return f"{errors} ERROR, {warns} WARN."


def print_findings(findings: Sequence[Finding], title: str = "Linter de políticas") -> None:
    if findings:
        console.print(findings_table(findings, title))
    console.print(summary(findings))
