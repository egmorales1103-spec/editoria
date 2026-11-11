"""deliver: package of a version (owner: lead).

Lists ONLY files verified to exist (media checked with ffprobe); everything else is shown
as pending (P11). Every interval declares its method (P06). Attributions come from the
asset manifests (P17). No CapCut project is claimed (P22). Marks the version immutable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import typer

from editoria.schemas import (
    MAPA_COLUMNS,
    QC_STATUS_LABEL,
    AssetEntry,
    EditPlan,
    QCReport,
    Transcript,
    read_model,
)
from editoria.util import ffmpeg, log
from editoria.util.cli import fail, open_project
from editoria.util.ffmpeg import command_log
from editoria.util.files import fmt_ts, read_csv_rows, write_csv_rows
from editoria.util.log import read_jsonl
from editoria.util.project import (
    DELIVERED_MARKER,
    PLAN_FILE,
    TRANSCRIPT_FILE,
    VIDEO_FILE,
    ProjectContext,
)
from editoria.util.resources import load_external_manifest, load_sfx_manifest

METHOD_LABEL = {
    "original": "original",
    "reframe": "reencuadre (píxeles existentes)",
    "generated": "toma generada (revisada y aceptada)",
}
FEEDBACK_QUESTION = (
    "¿Qué querés ajustar en las tomas, el ritmo, los subtítulos, los gráficos o el sonido? "
    "Podés indicarme el minuto/segundo y el cambio."
)


class DeliveryError(RuntimeError):
    pass


@dataclass
class Inventory:
    delivered: list[tuple[str, str]] = field(default_factory=list)  # (label, relative path)
    pending: list[str] = field(default_factory=list)


def _valid_media(path: Path) -> bool:
    if not path.exists() or path.stat().st_size == 0:
        return False
    try:
        data = ffmpeg.probe(path)
    except Exception:
        return False
    return float(data.get("format", {}).get("duration", 0) or 0) > 0


def _rel(ctx: ProjectContext, p: Path) -> str:
    return p.relative_to(ctx.root).as_posix()


def _words_between(tr: Transcript | None, a: float, b: float) -> str:
    if tr is None:
        return ""
    return " ".join(w.text for w in tr.words if w.start < b and w.end > a)


def build_edit_map(ctx: ProjectContext, plan: EditPlan, duration: float) -> list[dict[str, str]]:
    tr = ctx.load_transcript() if ctx.analysis(TRANSCRIPT_FILE).exists() else None
    segs = ctx.load_segments().segments if ctx.analysis("segmentos.json").exists() else []
    intervals = plan.video or []
    if not intervals:
        from editoria.schemas import VideoInterval

        intervals = [VideoInterval(id="v01", in_=0.0, out=duration, method="original")]
    rows: list[dict[str, str]] = []
    for iv in intervals:
        a, b = iv.in_, iv.out
        seg = next((s for s in segs if s.start < b and s.end > a), None)
        graphics = [
            (g.template or f"emoji {g.emoji}") + f" ({g.id})"
            for g in plan.graphics
            if g.in_ < b and g.out > a
        ]
        cues = [f"{s.cue}@{s.at:.2f}" for s in plan.sfx if a <= s.at < b]
        archivo = VIDEO_FILE
        if iv.method == "generated" and iv.shot:
            archivo = f"{VIDEO_FILE} (toma {iv.shot})"
        rows.append(
            {
                "entrada": fmt_ts(a),
                "salida": fmt_ts(b),
                "frase_original": _words_between(tr, a, b),
                "intencion": seg.intent if seg else "",
                "visual": iv.method if iv.method != "reframe" else f"reencuadre x{iv.zoom or 1:g}",
                "metodo": iv.method,
                "referencia": seg.reference if seg else "",
                "archivo": archivo,
                "subtitulo": f"estilo {plan.captions.style}" if plan.captions.enabled else "no",
                "grafico": "; ".join(graphics),
                "sonido": "; ".join(cues),
                "estado": "ejecutado",
            }
        )
    return rows


def _attributions(plan: EditPlan) -> tuple[list[AssetEntry], list[str]]:
    sfx_m, ext_m = load_sfx_manifest(), load_external_manifest()
    used: list[AssetEntry] = []
    missing: list[str] = []
    for cue in plan.sfx:
        aid = f"{cue.cue}_{cue.variant or 1}"
        entry = sfx_m.get(aid)
        (used.append(entry) if entry else missing.append(f"SFX {aid}"))
    for g in plan.graphics:
        if g.emoji:
            entry = ext_m.get(g.emoji)
            (used.append(entry) if entry else missing.append(f"emoji {g.emoji}"))
    if plan.music:
        entry = sfx_m.get(plan.music.asset_id) or ext_m.get(plan.music.asset_id)
        (used.append(entry) if entry else missing.append(f"música {plan.music.asset_id}"))
    fonts = [a for a in ext_m.assets if a.kind == "font"]
    used.extend(fonts)
    uniq = {a.id: a for a in used}
    return list(uniq.values()), missing


def _attributions_md(entries: list[AssetEntry], missing: list[str]) -> str:
    lines = ["# Atribuciones", ""]
    if not entries:
        lines.append("Esta versión no usa recursos de terceros que requieran atribución.")
    for a in sorted(entries, key=lambda e: (e.kind, e.id)):
        text = a.attribution or f"{a.id} — {a.author} — {a.license}"
        url = f" ({a.license_url})" if a.license_url else ""
        lines.append(f"- **{a.id}** ({a.kind}): {text}. Licencia: {a.license}{url}.")
    if missing:
        lines += ["", "Recursos usados SIN licencia registrada (revisar antes de publicar):", ""]
        lines += [f"- {m}" for m in missing]
    lines += [
        "",
        "Herramientas: FFmpeg (binario externo), Chromium/Playwright para gráficos.",
        "",
    ]
    return "\n".join(lines)


def deliver(ctx: ProjectContext, version: str, force: bool = False) -> Path:
    vdir = ctx.version_dir(version)
    if ctx.is_delivered(version):
        raise DeliveryError(f"{version} ya fue entregada.")
    video = vdir / VIDEO_FILE
    if not _valid_media(video):
        raise DeliveryError(f"No hay un video verificable en {version}/video.mp4: no se entrega.")
    qc_path = vdir / "qc" / "qc.json"
    if not qc_path.exists():
        raise DeliveryError(f"Falta el QC de {version}. Ejecutá 'editoria qc' antes de entregar.")
    qc = read_model(qc_path, QCReport)
    if qc.has_fail and not force:
        raise DeliveryError(f"El QC de {version} tiene FAIL. Corregí o usá --forzar.")
    plan = read_model(vdir / PLAN_FILE, EditPlan)
    probe = ctx.load_probe()

    inv = Inventory()
    inv.delivered.append(("Video completo", _rel(ctx, video)))
    for ext in ("srt", "vtt", "ass"):
        p = vdir / f"subtitulos.{ext}"
        if p.exists():
            inv.delivered.append((f"Subtítulos {ext.upper()}", _rel(ctx, p)))
        elif plan.captions.enabled:
            inv.pending.append(f"Subtítulos {ext.upper()} no generados.")
    for sid in ("A", "B", "C"):
        p = ctx.proposals_dir / f"muestra_{sid}.mp4"
        if _valid_media(p):
            inv.delivered.append((f"Muestra {sid}", _rel(ctx, p)))
        else:
            inv.pending.append(f"Muestra {sid} no producida.")
    comp = ctx.proposals_dir / "comparativa_ABC.mp4"
    if _valid_media(comp):
        inv.delivered.append(("Comparativa A/B/C", _rel(ctx, comp)))
    prop_md = ctx.proposals_dir / "propuestas.md"
    if prop_md.exists():
        inv.delivered.append(("Propuestas y recomendación", _rel(ctx, prop_md)))
    for name, label in (
        ("hoja_contactos.jpg", "Hoja de contactos"),
        ("qc/qc.md", "Control de calidad"),
    ):
        p = vdir / name
        if p.exists():
            inv.delivered.append((label, _rel(ctx, p)))
    gdir = vdir / "graficos"
    if gdir.exists():
        inv.delivered.append(("Capas de gráficos (PNG con alfa)", _rel(ctx, gdir)))
    mix = vdir / "audio" / "mezcla.wav"
    if mix.exists():
        inv.delivered.append(("Mezcla de audio", _rel(ctx, mix)))
    inv.delivered.append(("Plan de edición (plan.yaml)", _rel(ctx, vdir / PLAN_FILE)))

    # accepted shots + correspondence
    registry = read_csv_rows(ctx.generations_registry)
    shot_lines: list[str] = []
    for iv in plan.video:
        if iv.method == "generated" and iv.shot:
            row = next((r for r in registry if r.get("id") == iv.shot), {})
            shot_lines.append(
                f"- {iv.shot}: {fmt_ts(iv.in_)}–{fmt_ts(iv.out)} del original "
                f"(veredicto: {row.get('veredicto', '¿?')}, archivo: "
                f"{row.get('archivo_resultado', '')})"
            )
    pending_shots = [r for r in registry if r.get("veredicto") in ("pendiente", "reintentar")]
    for r in pending_shots:
        inv.pending.append(f"Toma {r['id']} sin aceptar ({r['veredicto']}).")

    # edit map
    rows = build_edit_map(ctx, plan, probe.duration_s)
    edit_map = write_csv_rows(vdir / "mapa_edicion.csv", MAPA_COLUMNS, rows)
    inv.delivered.append(("Mapa de edición (CSV)", _rel(ctx, edit_map)))

    # attributions
    entries, missing = _attributions(plan)
    atr = vdir / "atribuciones.md"
    atr.write_text(_attributions_md(entries, missing), encoding="utf-8", newline="\n")
    inv.delivered.append(("Atribuciones", _rel(ctx, atr)))

    # pending items recorded during render
    render_json = vdir / "render.json"
    if render_json.exists():
        import json

        inv.pending.extend(json.loads(render_json.read_text(encoding="utf-8")).get("pending", []))

    credits = read_jsonl(ctx.credits_log)
    spent = sum(float(c.get("amount", 0) or 0) for c in credits)
    cfg = ctx.load_config()

    counts = qc.counts()
    lines = [
        f"# Resumen de entrega — {version}",
        "",
        f"Proyecto `{ctx.slug}` · estilo {plan.style} · duración {fmt_ts(probe.duration_s)} "
        f"(igual al VIDEO_BASE) · {plan.canvas.width}×{plan.canvas.height}.",
        "",
        "## Archivos entregados (verificados)",
        "",
        *[f"- {label}: `{path}`" for label, path in inv.delivered],
        "",
        "## Pendiente o no producido",
        "",
        *([f"- {p}" for p in inv.pending] or ["- Nada pendiente."]),
        "",
        "## Intervalos y método (original / reencuadre / generado)",
        "",
        "| Entrada | Salida | Método |",
        "|---|---|---|",
        *[
            f"| {fmt_ts(iv.in_)} | {fmt_ts(iv.out)} | {METHOD_LABEL[iv.method]} |"
            for iv in plan.video
        ],
        *(["| 00:00.00 | " + fmt_ts(probe.duration_s) + " | original |"] if not plan.video else []),
        "",
        "Los gráficos y emojis son recursos superpuestos: no modifican el escenario grabado.",
        "",
        "## Tomas generadas",
        "",
        *(shot_lines or ["- No se usaron tomas generadas."]),
        "",
        "## Control de calidad",
        "",
        "- " + " · ".join(f"{QC_STATUS_LABEL[k]}: {v}" for k, v in counts.items()),
        "- Identidad, fondo, labios y criterio estético quedan para REVISIÓN HUMANA.",
        "",
        "## Créditos",
        "",
        f"- Límite autorizado: {cfg.budget.limit if cfg.budget.limit is not None else 'sin límite'}"
        f" {cfg.budget.unit} · consumido: {spent:g} {cfg.budget.unit}.",
        "",
        "## Limitaciones",
        "",
        "- No se entrega un proyecto nativo de CapCut: se entregan medios, subtítulos, capas y "
        "un mapa de edición con tiempos como apoyo.",
        "- No se publicó nada ni se envió a terceros.",
        "",
        "## Siguiente paso",
        "",
        FEEDBACK_QUESTION,
        "",
    ]
    resumen = vdir / "resumen.md"
    resumen.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    (vdir / DELIVERED_MARKER).write_text(f"{version}\n", encoding="utf-8")
    return resumen


def register(app: typer.Typer) -> None:
    @app.command("deliver")
    def deliver_cmd(
        slug: str = typer.Argument(...),
        version: str = typer.Option("V1", "--version"),
        forzar: bool = typer.Option(False, "--forzar", help="Entregar aunque el QC tenga FAIL."),
    ) -> None:
        """Arma el paquete de entrega separando lo ejecutado de lo pendiente."""
        ctx = open_project(slug)
        with command_log(ctx.commands_log):
            try:
                path = deliver(ctx, version, force=forzar)
            except DeliveryError as exc:
                fail(str(exc))
        log.ok(f"{version} entregada. Resumen: {path}")
        log.info(FEEDBACK_QUESTION)
