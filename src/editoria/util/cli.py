"""Small helpers shared by every module's cli.py."""

from __future__ import annotations

from typing import NoReturn

import typer

from editoria.util.ffmpeg import command_log
from editoria.util.log import error, warn
from editoria.util.project import ProjectContext, ProjectNotFound

PENDING_EXIT = 3


def pending(command: str) -> NoReturn:
    """Stub response used before a module is implemented."""
    warn(f"'{command}' está pendiente: todavía no está implementado.")
    raise typer.Exit(code=PENDING_EXIT)


def fail(message: str, code: int = 1) -> NoReturn:
    error(message)
    raise typer.Exit(code=code)


def open_project(slug: str) -> ProjectContext:
    """Open a project or exit with a Spanish error."""
    try:
        return ProjectContext.open(slug)
    except ProjectNotFound as exc:
        fail(str(exc))


__all__ = ["PENDING_EXIT", "command_log", "fail", "open_project", "pending"]
