"""``shots verdict``: the only way to accept a shot (P05, P24)."""

from __future__ import annotations

from editoria.schemas import GenerationRecord
from editoria.shots import registry
from editoria.shots.errors import ShotError
from editoria.util.project import ProjectContext

VERDICTS = ("aceptado", "reintentar", "descartado")


def set_verdict(
    ctx: ProjectContext,
    shot_id: str,
    verdict: str,
    motivo: str,
    *,
    fondo: str = "",
    identidad: str = "",
    manos: str = "",
    sincronia: str = "",
) -> GenerationRecord:
    """Record a human verdict in registro_generaciones.csv.

    - ``aceptado`` needs an imported, conformed result on disk.
    - ``reintentar`` is refused once ``tool_limits.max_attempts`` is reached.
    The review columns (fondo, identidad, manos, sincronia) are only written when given.
    """
    sid = registry.normalize_id(shot_id)
    verdict = verdict.strip().lower()
    if verdict not in VERDICTS:
        raise ShotError(f"Veredicto inválido '{verdict}'. Usá: {' | '.join(VERDICTS)}.")
    if not motivo.strip():
        raise ShotError("El veredicto necesita un motivo (--motivo).")
    record = registry.get_record(ctx, sid)
    meta = registry.load_meta(ctx, sid)

    if verdict == "aceptado":
        result = ctx.root / record.archivo_resultado if record.archivo_resultado else None
        if result is None or not result.is_file():
            raise ShotError(
                f"{sid} no tiene un resultado importado en disco; no se puede aceptar. "
                "Importalo con 'editoria shots import'."
            )
    if verdict == "reintentar":
        max_attempts = ctx.load_config().tool_limits.max_attempts
        if max_attempts is not None and meta.attempt >= max_attempts:
            raise ShotError(
                f"{sid} ya es el intento {meta.attempt} de {max_attempts} permitidos "
                "(tool_limits.max_attempts). No se puede reintentar: descartá la toma y "
                "conservá el original."
            )

    changes = {"veredicto": verdict, "motivo": motivo.strip()}
    for column, value in (
        ("fondo", fondo),
        ("identidad", identidad),
        ("manos", manos),
        ("sincronia", sincronia),
    ):
        if value.strip():
            changes[column] = value.strip()
    return registry.update_record(ctx, sid, **changes)
