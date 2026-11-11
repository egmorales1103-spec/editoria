"""plan draft / plan lint (owner: A2)."""

from __future__ import annotations

from pathlib import Path

import typer

from editoria.util.cli import fail, open_project
from editoria.util.log import ok, warn

plan_app = typer.Typer(help="Plan declarativo de edición (plan.yaml).", no_args_is_help=True)


def register(app: typer.Typer) -> None:
    @plan_app.command("draft")
    def plan_draft(
        slug: str = typer.Argument(...),
        style: str = typer.Option("A", "--style", help="A | B | C"),
        out: Path | None = typer.Option(
            None, "--out", help="Destino (por defecto 03_propuestas/plan_<estilo>.yaml)."
        ),
        window: str | None = typer.Option(
            None, "--window", help="Ventana de muestra inicio-fin en segundos (por ej. 2-9.5)."
        ),
    ) -> None:
        """Borrador automático del plan para un estilo."""
        from editoria.planning.draft import draft_plan, parse_window
        from editoria.policy import has_errors, lint_plan, print_findings
        from editoria.schemas import write_model

        ctx = open_project(slug)
        sid = style.strip().upper()
        if sid not in ("A", "B", "C"):
            fail(f"Estilo inválido '{style}': usá A, B o C.")
        try:
            preset = ctx.load_style(sid)
            win = parse_window(window) if window else None
            plan = draft_plan(ctx, preset, window=win)
        except (FileNotFoundError, ValueError) as exc:
            fail(str(exc))
        target = out or ctx.proposals_dir / f"plan_{sid}.yaml"
        write_model(target, plan)
        ok(f"Borrador del estilo {sid} escrito en {target}")
        findings = lint_plan(plan, ctx)
        print_findings(findings)
        if has_errors(findings):
            warn("El borrador tiene errores de política: revisalo antes de usarlo.")
            raise typer.Exit(code=1)

    @plan_app.command("lint")
    def plan_lint(
        slug: str = typer.Argument(...),
        plan: Path | None = typer.Option(None, "--plan", help="Ruta de un plan.yaml."),
        version: str = typer.Option("V1", "--version"),
    ) -> None:
        """Linter de políticas; código distinto de 0 si hay ERROR."""
        from editoria.policy import has_errors, lint_file, print_findings
        from editoria.util.project import PLAN_FILE

        ctx = open_project(slug)
        if plan is not None:
            path = plan if plan.exists() or plan.is_absolute() else ctx.root / plan
        else:
            try:
                path = ctx.version_dir(version) / PLAN_FILE
            except ValueError as exc:
                fail(str(exc))
        _, findings = lint_file(path, ctx)
        print_findings(findings, title=f"Linter de políticas — {path.name}")
        if has_errors(findings):
            raise typer.Exit(code=1)

    app.add_typer(plan_app, name="plan")
