"""analyze (owner: A1)."""

from __future__ import annotations

import typer

from editoria.analysis.analyze import analyze_project
from editoria.ingest.errors import IngestError
from editoria.util.cli import fail, open_project
from editoria.util.log import info, ok, warn


def register(app: typer.Typer) -> None:
    @app.command("analyze")
    def analyze_cmd(
        slug: str = typer.Argument(...),
        force: bool = typer.Option(
            False, "--force", help="Regenera segmentos.json aunque el director ya lo haya editado."
        ),
    ) -> None:
        """Silencios, cortes, zona de rostro, segmentos y mapa de edición."""
        ctx = open_project(slug)
        try:
            segs = analyze_project(ctx, force=force)
        except IngestError as exc:
            fail(str(exc))
        silences = ctx.load_silences()
        cuts = ctx.load_cuts()
        face = ctx.load_face()
        ok(f"{len(segs.segments)} segmentos; mapa en {ctx.analysis('mapa_edicion.csv')}")
        info(
            f"Silencios: {len(silences.silences) if silences else 0} · "
            f"cortes: {len(cuts.cuts) if cuts else 0}"
        )
        if face and face.estimated:
            warn("No se detectó rostro: se usó una zona estimada (arriba, al centro).")
