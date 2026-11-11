"""``shots import``: validate a result from the tool and conform it (silent, canvas, FPS)."""

from __future__ import annotations

import shutil
from pathlib import Path

from editoria.schemas import Canvas, parse_fps
from editoria.shots import registry
from editoria.shots.budget import record_credit
from editoria.shots.errors import ShotError
from editoria.shots.media import conform_filter, encode_silent, scaled_face, video_info
from editoria.shots.models import ImportInfo, ShotMeta
from editoria.util import ffmpeg
from editoria.util.files import sha256_file
from editoria.util.project import ProjectContext

ASPECT_TOLERANCE = 0.015  # relative difference allowed between result and segment aspect
CONFORMED_NAME = "conformado.mp4"
RECEIVED_STEM = "recibido"


def import_shot(
    ctx: ProjectContext,
    shot_id: str,
    file: Path,
    *,
    funcion: str = "",
    ajustes: str = "",
    costo: float | None = None,
    replace: bool = False,
    canvas: Canvas | None = None,
) -> ShotMeta:
    """Validate and conform ``file`` as the result of ``shot_id``.

    Rejects (ShotError) a different aspect or a result shorter than the segment; trims a longer
    one; always drops the audio (P03). Only data actually reported is stored.
    """
    with ffmpeg.command_log(ctx.commands_log):
        return _import_shot(ctx, shot_id, file, funcion, ajustes, costo, replace, canvas)


def _import_shot(
    ctx: ProjectContext,
    shot_id: str,
    file: Path,
    funcion: str,
    ajustes: str,
    costo: float | None,
    replace: bool,
    canvas: Canvas | None,
) -> ShotMeta:
    canvas = canvas or Canvas()
    sid = registry.normalize_id(shot_id)
    record = registry.get_record(ctx, sid)
    meta = registry.load_meta(ctx, sid)
    file = Path(file)
    if not file.is_file():
        raise ShotError(f"No existe el archivo '{file}'.")
    if meta.imported is not None and not replace:
        raise ShotError(
            f"{sid} ya tiene un resultado importado. Usá --reemplazar para reemplazarlo "
            "(el veredicto vuelve a 'pendiente') o preparé un reintento con "
            "'shots pack --reintento-de'."
        )
    if record.veredicto == "aceptado" and not replace:
        raise ShotError(f"{sid} ya fue aceptada; no se modifica.")

    info = video_info(file)

    # Aspect must match the segment that was sent (a different aspect is not a framing variation).
    seg_ar = meta.width / meta.height
    res_ar = info.width / info.height
    if abs(res_ar - seg_ar) / seg_ar > ASPECT_TOLERANCE:
        raise ShotError(
            f"El resultado ({info.width}×{info.height}) tiene otro aspecto que el segmento "
            f"enviado ({meta.width}×{meta.height}). Se rechaza: pedí a la herramienta la misma "
            "proporción que el original."
        )

    # Duration: shorter is rejected, longer is trimmed to the segment.
    frame = 1.0 / float(info.fps)
    tolerance = 1.5 * frame
    if info.duration < meta.duration - tolerance:
        raise ShotError(
            f"El resultado dura {info.duration:.2f} s y el segmento {meta.duration:.2f} s. "
            "Un resultado más corto no cubre el intervalo: se rechaza (reintentá la generación)."
        )
    trimmed = info.duration > meta.duration + tolerance
    pad = max(meta.duration - info.duration, 0.0) + frame if info.duration < meta.duration else 0.0

    fps = parse_fps(meta.fps)
    face = ctx.load_face()
    face_box = face.union_box if face else None
    face_frame = (face.frame_w, face.frame_h) if face else None
    vf = conform_filter(info, canvas, fps, scaled_face(info, face_box, face_frame), pad_s=pad)

    rdir = registry.results_dir(ctx, sid)
    rdir.mkdir(parents=True, exist_ok=True)
    received = rdir / f"{RECEIVED_STEM}{file.suffix.lower() or '.mp4'}"
    for old in rdir.glob(f"{RECEIVED_STEM}.*"):
        old.unlink()
    shutil.copy2(file, received)
    conformed = rdir / CONFORMED_NAME
    encode_silent(received, conformed, vf, meta.duration, fps)

    out = video_info(conformed)
    if out.has_audio:  # defensive: P03
        conformed.unlink(missing_ok=True)
        raise ShotError("El clip conformado conservó audio; se descarta (P03).")
    if (out.width, out.height) != (canvas.width, canvas.height) or out.pix_fmt != "yuv420p":
        raise ShotError(
            f"El conformado quedó en {out.width}×{out.height} {out.pix_fmt}; "
            f"se esperaba {canvas.width}×{canvas.height} yuv420p."
        )

    meta = meta.model_copy(
        update={
            "imported": ImportInfo(
                received=registry.rel(ctx, received),
                received_sha256=sha256_file(received),
                received_width=info.width,
                received_height=info.height,
                received_fps=f"{info.fps.numerator}/{info.fps.denominator}",
                received_duration_s=round(info.duration, 4),
                received_had_audio=info.has_audio,
                trimmed=trimmed,
                conformed=registry.rel(ctx, conformed),
                width=out.width,
                height=out.height,
                fps=meta.fps,
            )
        }
    )
    registry.save_meta(ctx, meta)

    changes = {
        "archivo_resultado": registry.rel(ctx, conformed),
        "funcion_modelo_real": funcion.strip(),
        "ajustes_mostrados": ajustes.strip(),
        "costo_mostrado": f"{costo:g}" if costo is not None else "",
        "veredicto": "pendiente",
        "motivo": "",
    }
    registry.update_record(ctx, sid, **changes)
    if costo is not None:
        record_credit(ctx, costo, f"{sid}: importado (costo informado por el usuario)")
    return meta
