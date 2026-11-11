"""Root CLI: mounts every module's commands via ``register(app)``."""

from __future__ import annotations

import sys
from pathlib import Path

import typer

from editoria import __version__
from editoria.util.project import set_projects_dir

# Spanish output must survive Windows consoles and pipes (cp1252 by default).
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure") and (_stream.encoding or "").lower() != "utf-8":
        _stream.reconfigure(encoding="utf-8", errors="replace")

app = typer.Typer(
    name="editoria",
    help="EditorIA: edición de reels con IA, reproducible y verificable.",
    no_args_is_help=True,
    rich_markup_mode="rich",
    pretty_exceptions_show_locals=False,
)


def _version_cb(value: bool) -> None:
    if value:
        typer.echo(f"editoria {__version__}")
        raise typer.Exit()


@app.callback()
def _root(
    proyectos: Path | None = typer.Option(
        None,
        "--proyectos",
        envvar="EDITORIA_PROJECTS",
        help="Carpeta de proyectos (por defecto ./proyectos).",
    ),
    show_version: bool = typer.Option(
        False, "--version", callback=_version_cb, is_eager=True, help="Muestra la versión."
    ),
) -> None:
    set_projects_dir(proyectos)


def _register_all() -> None:
    from editoria import deliver, doctor, pipeline
    from editoria.analysis import cli as analysis_cli
    from editoria.audio import cli as audio_cli
    from editoria.captions import cli as captions_cli
    from editoria.graphics import cli as graphics_cli
    from editoria.ingest import cli as ingest_cli
    from editoria.planning import cli as planning_cli
    from editoria.qc import cli as qc_cli
    from editoria.render import cli as render_cli
    from editoria.shots import cli as shots_cli
    from editoria.versioning import cli as versioning_cli

    for mod in (
        doctor,
        ingest_cli,
        analysis_cli,
        versioning_cli,
        planning_cli,
        captions_cli,
        graphics_cli,
        audio_cli,
        render_cli,
        qc_cli,
        shots_cli,
        pipeline,
        deliver,
    ):
        mod.register(app)


_register_all()


def main() -> None:
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
