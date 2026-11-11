"""``shots pack``: segment, anchor frames, prompt and manual steps for Higgsfield."""

from __future__ import annotations

from pathlib import Path

from editoria.schemas import GenerationRecord
from editoria.shots import registry
from editoria.shots.budget import BudgetStatus, budget_status
from editoria.shots.errors import ShotError
from editoria.shots.media import extract_frame, video_info
from editoria.shots.models import ShotMeta
from editoria.shots.prompts import NEGATIVE_CONSTRAINTS, build_prompt, risky_hints
from editoria.util import ffmpeg
from editoria.util.project import ProjectContext

MIN_SEGMENT_S = 0.2  # sanity floor (a few frames); tool limits come from proyecto.yaml
SEGMENT_FILE = "segmento.mp4"
ANCHORS = (
    ("inicio", "ancla_inicio.png"),
    ("medio", "ancla_medio.png"),
    ("fin", "ancla_fin.png"),
)


def _fmt(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _budget_line(status: BudgetStatus) -> str:
    if status.limit is None:
        return (
            "SIN LÍMITE AUTORIZADO en proyecto.yaml (budget.limit). "
            "No ejecutes nada que consuma créditos hasta tener ese dato."
        )
    return (
        f"límite {status.limit:g} {status.unit}, gastado {status.spent:g}, "
        f"restante {status.remaining:g}"
    )


def render_pack_md(
    slug: str,
    meta: ShotMeta,
    max_clip_s: float | None,
    max_attempts: int | None,
    status: BudgetStatus,
    warnings: list[str],
) -> str:
    clip = (
        f"{max_clip_s:g} s (de proyecto.yaml)"
        if max_clip_s is not None
        else "verificar en la herramienta (proyecto.yaml no lo define)"
    )
    attempts = (
        f"{max_attempts} (de proyecto.yaml)"
        if max_attempts is not None
        else "verificar (proyecto.yaml no lo define)"
    )
    lines = [
        f"# Paquete {meta.id} — proyecto {slug}",
        "",
        f"Intento {meta.attempt} de la toma {meta.root}. "
        "Preparado para ejecutarse a mano en Higgsfield; todavía **no se generó nada**.",
        "",
        "## Segmento",
        "",
        f"- Origen: `{meta.source}` (solo lectura)",
        f"- Entrada / salida: {_fmt(meta.start)} s – {_fmt(meta.end)} s "
        f"(duración {_fmt(meta.duration)} s)",
        f"- Formato del segmento: {meta.width}×{meta.height}, {meta.fps} fps",
        f"- Cambio pedido: {meta.change}",
        "",
        "## Límites de la herramienta",
        "",
        f"- Duración máxima del clip: {clip}",
        f"- Intentos máximos: {attempts}",
        f"- Créditos: {_budget_line(status)}",
        "- Costo estimado: lo muestra la herramienta antes de ejecutar; anotalo tal cual. "
        "EditorIA no lo calcula ni lo inventa.",
        "",
    ]
    if warnings:
        lines += ["## Advertencias", ""] + [f"- {w}" for w in warnings] + [""]
    lines += [
        "## Archivos de este paquete",
        "",
        f"- `{SEGMENT_FILE}`: segmento con audio, re-codificado con precisión (CRF 16). "
        "Es lo único que se sube.",
        "- `ancla_inicio.png`, `ancla_medio.png`, `ancla_fin.png`: fotogramas de referencia "
        "(un fotograma sirve de ancla visual; no conserva el movimiento ni el habla).",
        "- `prompt.txt`: prompt principal y restricciones negativas.",
        "",
        "## Prompt principal",
        "",
        "```text",
        meta.prompt,
        "```",
        "",
        "## Restricciones negativas",
        "",
        "Si la herramienta tiene un campo de restricciones negativas, pegá esto ahí:",
        "",
        "```text",
        NEGATIVE_CONSTRAINTS,
        "```",
        "",
        "Si no existe ese campo, agregá al final del prompt principal: "
        f"`Avoid: {NEGATIVE_CONSTRAINTS}.`",
        "",
        "## Pasos manuales",
        "",
        "1. Abrí https://higgsfield.ai/ y comprobá qué funciones de edición o generación admite "
        "tu cuenta HOY. Preferí video a video si admite la transformación; no asumas nombres "
        "de modelos ni botones.",
        f"2. Subí únicamente `{SEGMENT_FILE}` de este paquete (no el video completo ni carpetas).",
        "3. Pegá el prompt y las restricciones. Pedí UN solo cambio sutil de encuadre.",
        "4. Antes de ejecutar mirá el costo que muestra la herramienta y comprobá que cabe en "
        "el límite autorizado (`editoria shots budget <slug>`). Nunca compres planes ni créditos.",
        "5. Ejecutá y descargá el resultado. Anotá, tal como los muestra la herramienta: "
        "función/modelo real, ajustes y costo. No inventes semilla, costo ni parámetros.",
        "6. Importá el archivo: "
        f'`editoria shots import {slug} {meta.id} <archivo> --funcion "..." '
        '--ajustes "..." --costo <n>`.',
        f"7. Compará: `editoria shots compare {slug} {meta.id}` y mirá la hoja a velocidad normal "
        "y cuadro a cuadro: rostro, manos, bordes, objetos, sombras y boca.",
        f"8. Decidí: `editoria shots verdict {slug} {meta.id} aceptado|reintentar|descartado "
        '--motivo "..."`. Ante duda visible, se conserva el original.',
        "",
        "## Recordatorios",
        "",
        "- El audio del resultado se descarta: manda el audio del VIDEO_BASE.",
        "- Si hay labios visibles y no coinciden con el audio original, la toma se rechaza.",
        "- Un zoom digital no prueba una perspectiva nueva; si no hace falta generar, "
        "usá reencuadre.",
        "- Los prompts expresan el objetivo; no garantizan que el modelo lo cumpla.",
        "",
    ]
    return "\n".join(lines)


def pack_shot(
    ctx: ProjectContext,
    start: float,
    end: float,
    change: str,
    retry_of: str | None = None,
) -> ShotMeta:
    """Create the pack of a new shot (or a retry of ``retry_of``) and its 'pendiente' row."""
    with ffmpeg.command_log(ctx.commands_log):
        return _pack_shot(ctx, start, end, change, retry_of)


def _pack_shot(
    ctx: ProjectContext, start: float, end: float, change: str, retry_of: str | None
) -> ShotMeta:
    if not change.strip():
        raise ShotError("Indicá el cambio de encuadre pedido con --cambio.")
    cfg = ctx.load_config()
    limits = cfg.tool_limits
    duration = round(end - start, 6)
    if start < 0 or duration < MIN_SEGMENT_S:
        raise ShotError(
            f"Segmento inválido ({start}–{end} s): la entrada debe ser ≥ 0 y la duración "
            f"de al menos {MIN_SEGMENT_S} s."
        )
    src = ctx.original_video()
    info = video_info(src)
    if end > info.duration + 1e-6:
        raise ShotError(
            f"La salida ({end} s) supera la duración del VIDEO_BASE ({info.duration:.2f} s)."
        )
    max_clip = limits.higgsfield_max_clip_s
    if max_clip is not None and duration > max_clip + 1e-6:
        raise ShotError(
            f"El segmento dura {duration:g} s y el límite de la herramienta en proyecto.yaml "
            f"(tool_limits.higgsfield_max_clip_s) es {max_clip:g} s. Elegí uno más corto."
        )

    root, attempt = "", 1
    if retry_of:
        parent = registry.get_record(ctx, retry_of)
        parent_meta = registry.load_meta(ctx, parent.id)
        if parent.veredicto != "reintentar":
            raise ShotError(
                f"{parent.id} tiene veredicto '{parent.veredicto}'; solo se puede reintentar una "
                "toma con veredicto 'reintentar'."
            )
        root, attempt = parent_meta.root, parent_meta.attempt + 1
        if limits.max_attempts is not None and attempt > limits.max_attempts:
            raise ShotError(
                f"Se alcanzó el máximo de intentos ({limits.max_attempts}) para este segmento. "
                "Conservá el original o descartá la toma."
            )

    shot_id = registry.next_shot_id(ctx)
    pdir = registry.pack_dir(ctx, shot_id)
    pdir.mkdir(parents=True, exist_ok=True)
    seg = pdir / SEGMENT_FILE

    # Precise cut: input seeking + re-encode (never stream copy).
    ffmpeg.run(
        [
            "-ss", f"{start:.6f}", "-i", src, "-t", f"{duration:.6f}",
            "-map", "0:v:0", "-map", "0:a:0?",
            "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            seg,
        ]
    )  # fmt: skip
    seg_info = video_info(seg)
    fps = float(seg_info.fps)
    times = {
        "inicio": 0.0,
        "medio": seg_info.duration / 2,
        "fin": max(seg_info.duration - 1.5 / fps, 0.0),
    }
    for key, name in ANCHORS:
        extract_frame(seg, times[key], pdir / name)

    prompt = build_prompt(change)
    (pdir / "prompt.txt").write_text(
        f"{prompt}\n\n--- Restricciones negativas ---\n{NEGATIVE_CONSTRAINTS}\n",
        encoding="utf-8",
        newline="\n",
    )
    meta = ShotMeta(
        id=shot_id,
        root=root or shot_id,
        attempt=attempt,
        source=registry.rel(ctx, src),
        start=start,
        end=end,
        duration=duration,
        fps=f"{seg_info.fps.numerator}/{seg_info.fps.denominator}",
        width=seg_info.width,
        height=seg_info.height,
        change=change.strip(),
        prompt=prompt,
        pack_dir=registry.rel(ctx, pdir),
    )
    registry.save_meta(ctx, meta)

    warnings = [
        f"El cambio pedido contiene «{h}»: la sección 5 del prompt maestro lo excluye "
        "(fondo, órbitas, relighting, outpainting, ropa). Reformulalo como una variación sutil."
        for h in risky_hints(change)
    ]
    pack_md = render_pack_md(
        ctx.slug, meta, max_clip, limits.max_attempts, budget_status(ctx), warnings
    )
    (pdir / "pack.md").write_text(pack_md, encoding="utf-8", newline="\n")

    records = registry.load_registry(ctx)
    records.append(
        GenerationRecord(
            id=shot_id,
            archivo_origen=meta.source,
            entrada=_fmt(start),
            salida=_fmt(end),
            prompt=prompt,
            veredicto="pendiente",
        )
    )
    registry.save_registry(ctx, records)
    return meta


def pack_files(ctx: ProjectContext, shot_id: str) -> list[Path]:
    pdir = registry.pack_dir(ctx, shot_id)
    return [pdir / n for n in (SEGMENT_FILE, *(a for _, a in ANCHORS), "prompt.txt", "pack.md")]
