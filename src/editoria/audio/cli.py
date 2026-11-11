"""audio sfx / mix / check-voice (owner: A4)."""

from __future__ import annotations

from pathlib import Path

import typer

from editoria.util.cli import pending

audio_app = typer.Typer(help="Efectos de sonido y mezcla.", no_args_is_help=True)


def register(app: typer.Typer) -> None:
    @audio_app.command("sfx")
    def audio_sfx() -> None:
        """Lista los SFX disponibles con su licencia."""
        pending("audio sfx")

    @audio_app.command("mix")
    def audio_mix(
        slug: str = typer.Argument(...),
        version: str = typer.Option("V1", "--version"),
    ) -> None:
        """Mezcla audio base + SFX (+ música) con loudness objetivo."""
        pending("audio mix")

    @audio_app.command("check-voice")
    def audio_check_voice(
        slug: str = typer.Argument(...),
        media: Path = typer.Argument(...),
    ) -> None:
        """Desfase y similitud de la voz respecto del original."""
        pending("audio check-voice")

    app.add_typer(audio_app, name="audio")
