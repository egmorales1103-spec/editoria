"""captions build (owner: A2)."""

from __future__ import annotations

import typer

from editoria.util.cli import command_log, fail, open_project
from editoria.util.log import info, ok

captions_app = typer.Typer(help="Subtítulos ASS/SRT/VTT.", no_args_is_help=True)


def register(app: typer.Typer) -> None:
    @captions_app.command("build")
    def captions_build(
        slug: str = typer.Argument(...),
        version: str = typer.Option("V1", "--version"),
    ) -> None:
        """Genera subtitulos.ass, .srt, .vtt y .json para una versión."""
        from editoria.captions.builder import build_for_version

        ctx = open_project(slug)
        try:
            plan_path = ctx.version_dir(version) / "plan.yaml"
        except ValueError as exc:
            fail(str(exc))
        if not plan_path.exists():
            fail(f"No existe {plan_path}. Creá el plan con 'editoria plan draft' o 'version new'.")
        if ctx.is_delivered(version):
            fail(f"La versión {version} ya fue entregada y es inmutable.")
        with command_log(ctx.commands_log):
            try:
                arts = build_for_version(ctx, version)
            except FileNotFoundError as exc:
                fail(str(exc))
        spoken = [e for e in arts.events if not e.editorial]
        titles = len(arts.events) - len(spoken)
        ok(f"Subtítulos de {version}: {len(spoken)} eventos, {titles} títulos editoriales.")
        for p in (arts.ass, arts.srt, arts.vtt):
            info(f"  {p}")

    app.add_typer(captions_app, name="captions")
