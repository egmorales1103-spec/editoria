"""shots pack / import / compare / verdict / budget / list (owner: A6)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import typer
from rich.markup import escape

from editoria.shots import registry
from editoria.shots.budget import BudgetError, budget_status, record_credit
from editoria.shots.compare import compare_shot
from editoria.shots.errors import ShotError
from editoria.shots.importer import import_shot
from editoria.shots.pack import pack_files, pack_shot
from editoria.shots.prompts import risky_hints
from editoria.shots.verdict import set_verdict
from editoria.util import ffmpeg
from editoria.util.cli import fail, open_project
from editoria.util.log import info, ok, warn

shots_app = typer.Typer(help="Tomas complementarias (Higgsfield).", no_args_is_help=True)


@contextmanager
def _guard() -> Iterator[None]:
    """Turn expected failures into a Spanish message and a non-zero exit."""
    try:
        yield
    except (ShotError, ffmpeg.FFmpegError, ffmpeg.FFmpegNotFound, FileNotFoundError) as exc:
        fail(escape(str(exc)))


@shots_app.command("pack")
def shots_pack(
    slug: str = typer.Argument(...),
    start: float = typer.Option(..., "--in", help="Entrada del segmento (s)."),
    end: float = typer.Option(..., "--out", help="Salida del segmento (s)."),
    change: str = typer.Option(..., "--cambio", help="Cambio de encuadre pedido."),
    retry_of: str | None = typer.Option(
        None, "--reintento-de", help="Id de una toma con veredicto 'reintentar' (ej. G01)."
    ),
) -> None:
    """Prepara segmento, anclas y prompt para Higgsfield (no gasta créditos)."""
    ctx = open_project(slug)
    with _guard():
        meta = pack_shot(ctx, start, end, change, retry_of)
    for hint in risky_hints(change):
        warn(f"El cambio contiene «{hint}»: la sección 5 del prompt maestro lo excluye.")
    ok(f"Paquete {meta.id} listo (intento {meta.attempt}): {escape(meta.pack_dir)}")
    for f in pack_files(ctx, meta.id):
        info(f"  - {escape(f.name)}")
    info(f"Seguí los pasos de {escape(meta.pack_dir)}/pack.md. Veredicto actual: pendiente.")


@shots_app.command("import")
def shots_import(
    slug: str = typer.Argument(...),
    shot_id: str = typer.Argument(...),
    file: Path = typer.Argument(...),
    funcion: str = typer.Option("", "--funcion", help="Función/modelo real, como lo muestra."),
    costo: float | None = typer.Option(None, "--costo", help="Costo mostrado por la herramienta."),
    ajustes: str = typer.Option("", "--ajustes", help="Ajustes mostrados por la herramienta."),
    replace: bool = typer.Option(
        False, "--reemplazar", help="Reemplaza un resultado ya importado."
    ),
) -> None:
    """Valida y conforma un resultado; quita el audio."""
    ctx = open_project(slug)
    with _guard():
        meta = import_shot(
            ctx, shot_id, file, funcion=funcion, ajustes=ajustes, costo=costo, replace=replace
        )
    imp = meta.imported
    if imp is None:  # pragma: no cover - import_shot always sets it
        fail("La importación no registró el resultado.")
    ok(f"{meta.id} importada: {escape(imp.conformed)} ({imp.width}×{imp.height}, {imp.fps} fps)")
    if imp.received_had_audio:
        info("  El audio del resultado se descartó (manda el audio del VIDEO_BASE).")
    if imp.trimmed:
        info("  El resultado era más largo que el segmento y se recortó.")
    if costo is not None:
        status = budget_status(ctx)
        if status.limit is None or status.spent > status.limit:
            warn("El costo registrado deja los créditos sin límite autorizado o por encima.")
    info(f"Siguiente: editoria shots compare {slug} {meta.id}")


@shots_app.command("compare")
def shots_compare(slug: str = typer.Argument(...), shot_id: str = typer.Argument(...)) -> None:
    """Hoja comparativa y métricas de deriva del fondo."""
    ctx = open_project(slug)
    with _guard():
        res = compare_shot(ctx, shot_id)
    info(f"SSIM del fondo: {res.ssim_background:.3f} (peor recorte {res.ssim_background_min:.3f})")
    info(f"Parpadeo del fondo: {res.flicker:.2f} · Diferencia de color: {res.color_delta_e:.2f}")
    for r in res.reasons:
        info(f"  - {r}")
    label = {"estable": "ESTABLE", "revisar": "REVISAR", "deriva": "DERIVA"}[res.recommendation]
    ok(f"Recomendación automática: {label} (la decisión es tuya).")
    info(f"Hoja: {escape(res.sheet)}")
    info(f"Lado a lado: {escape(res.side_by_side)}")
    info("Revisá rostro, manos, bordes y boca: estas métricas no los miden.")


@shots_app.command("verdict")
def shots_verdict(
    slug: str = typer.Argument(...),
    shot_id: str = typer.Argument(...),
    verdict: str = typer.Argument(..., help="aceptado | reintentar | descartado"),
    motivo: str = typer.Option(..., "--motivo"),
    fondo: str = typer.Option("", "--fondo", help="Revisión humana del fondo."),
    identidad: str = typer.Option("", "--identidad", help="Revisión humana de la identidad."),
    manos: str = typer.Option("", "--manos", help="Revisión humana de las manos."),
    sincronia: str = typer.Option("", "--sincronia", help="Revisión humana de la sincronía."),
) -> None:
    """Única vía para aceptar una toma."""
    ctx = open_project(slug)
    with _guard():
        rec = set_verdict(
            ctx,
            shot_id,
            verdict,
            motivo,
            fondo=fondo,
            identidad=identidad,
            manos=manos,
            sincronia=sincronia,
        )
    ok(f"{rec.id}: veredicto '{rec.veredicto}' registrado.")
    if rec.veredicto == "aceptado" and not (ctx.shots_comparisons_dir / rec.id).exists():
        warn(f"No hay comparativa de {rec.id}; se recomienda 'shots compare' antes de usarla.")


@shots_app.command("budget")
def shots_budget(
    slug: str = typer.Argument(...),
    register_amount: float | None = typer.Option(
        None, "--registrar", help="Registra créditos ya consumidos (según la herramienta)."
    ),
    detail: str = typer.Option("", "--detalle", help="Descripción del gasto registrado."),
) -> None:
    """Límite, gastado y restante de créditos."""
    ctx = open_project(slug)
    try:
        if register_amount is not None:
            record_credit(ctx, register_amount, detail or "registro manual")
            ok(f"Registrados {register_amount:g} créditos.")
        status = budget_status(ctx)
    except BudgetError as exc:
        fail(escape(str(exc)))
    if status.limit is None:
        warn("Sin límite autorizado en proyecto.yaml (budget.limit): no se pueden gastar créditos.")
        info(f"Gastado: {status.spent:g} {status.unit}")
        return
    info(f"Límite: {status.limit:g} {status.unit}")
    info(f"Gastado: {status.spent:g} {status.unit}")
    info(f"Restante: {status.remaining:g} {status.unit}")


@shots_app.command("list")
def shots_list(slug: str = typer.Argument(...)) -> None:
    """Tomas registradas y su veredicto."""
    ctx = open_project(slug)
    with _guard():
        records = registry.load_registry(ctx)
    if not records:
        info("No hay tomas registradas todavía.")
        return
    for r in records:
        result = "con resultado" if r.archivo_resultado else "sin resultado"
        info(f"{r.id}  {r.entrada}–{r.salida} s  {r.veredicto}  ({result})")


def register(app: typer.Typer) -> None:
    app.add_typer(shots_app, name="shots")
