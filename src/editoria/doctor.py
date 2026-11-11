"""`editoria doctor`: environment checks (owner: A1)."""

from __future__ import annotations

import typer

from editoria.util.cli import pending


def register(app: typer.Typer) -> None:
    @app.command("doctor")
    def doctor_cmd() -> None:
        """Verifica ffmpeg, filtros, libass, Chromium, modelo whisper y disco."""
        pending("doctor")
