"""audio sfx / mix / check-voice (owner: A4)."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.table import Table

from editoria.audio.mix import mix_for_version
from editoria.audio.sfx import list_sfx
from editoria.audio.voice import check_voice
from editoria.audio.wavio import AudioError
from editoria.util.cli import command_log, fail, open_project
from editoria.util.ffmpeg import FFmpegError, FFmpegNotFound
from editoria.util.log import console, info, ok, warn

audio_app = typer.Typer(help="Efectos de sonido y mezcla.", no_args_is_help=True)

MAX_OFFSET_MS = 1000.0 / 30.0  # one frame at 30 fps
MIN_SIMILARITY = 0.5


def register(app: typer.Typer) -> None:
    @audio_app.command("sfx")
    def audio_sfx() -> None:
        """Lista los SFX disponibles con su licencia."""
        rows = list_sfx()
        table = Table(title="Efectos de sonido (assets/sfx)")
        for col in ("id", "dur. (s)", "licencia", "autoría", "uso sugerido", "estado"):
            table.add_column(col)
        for r in rows:
            if not r.exists:
                state = "[red]FALTA[/red]"
            elif r.hash_ok is False:
                state = "[red]hash distinto[/red]"
            elif not r.license:
                state = "[red]sin licencia[/red]"
            else:
                state = "[green]ok[/green]"
            dur = f"{r.duration_s:.2f}" if r.duration_s is not None else "-"
            table.add_row(r.id, dur, r.license or "-", r.author or "-", r.suggested_use, state)
        console.print(table)

    @audio_app.command("mix")
    def audio_mix(
        slug: str = typer.Argument(..., help="Slug del proyecto."),
        version: str = typer.Option("V1", "--version", help="Versión a mezclar."),
    ) -> None:
        """Mezcla audio base + SFX (+ música) con loudness objetivo."""
        ctx = open_project(slug)
        try:
            with command_log(ctx.commands_log):
                result = mix_for_version(ctx, version)
        except (AudioError, FileNotFoundError, ValueError, FFmpegError, FFmpegNotFound) as exc:
            fail(str(exc))
        ok(f"Mezcla escrita en {result.wav}")
        info(
            f"Loudness integrado: {result.lufs:.1f} LUFS | true peak: {result.true_peak:.1f} dBTP"
            + (f" | LRA: {result.lra:.1f} LU" if result.lra is not None else "")
        )
        info(f"Muestras con clipping: {result.clipped_samples}")
        if result.voice_to_sfx_db is not None:
            info(f"Relación voz/SFX (ventanas con voz): {result.voice_to_sfx_db:.1f} dB")

    @audio_app.command("check-voice")
    def audio_check_voice(
        slug: str = typer.Argument(..., help="Slug del proyecto."),
        media: Path = typer.Argument(..., help="MP4 o WAV a comparar con el audio original."),
    ) -> None:
        """Desfase y similitud de la voz respecto del original."""
        ctx = open_project(slug)
        if not media.exists():
            fail(f"No existe el archivo '{media}'.")
        try:
            with command_log(ctx.commands_log):
                res = check_voice(ctx.original_video(), media)
        except (AudioError, FileNotFoundError, FFmpegError, FFmpegNotFound) as exc:
            fail(str(exc))
        info(f"Desfase: {res.offset_ms:+.1f} ms | similitud: {res.similarity:.3f}")
        bad = False
        if abs(res.offset_ms) > MAX_OFFSET_MS:
            warn(f"Desfase mayor a un cuadro ({MAX_OFFSET_MS:.0f} ms): voz desincronizada.")
            bad = True
        if res.similarity < MIN_SIMILARITY:
            warn("Similitud baja: el audio no parece ser el del VIDEO_BASE.")
            bad = True
        if bad:
            raise typer.Exit(code=1)
        ok("La voz coincide con el original.")

    app.add_typer(audio_app, name="audio")
