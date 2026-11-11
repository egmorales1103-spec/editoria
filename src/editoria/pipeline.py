"""End-to-end orchestration (owner: lead): propose, render of a version, run.

Order inside a render (section 7, Ola 2): lint -> captions -> graphics -> audio mix ->
compose -> qc. The render refuses when the linter reports an ERROR or when the version
was already rendered/delivered (P20). `run` always stops after V1 (§11 of the prompt).
"""

from __future__ import annotations

import contextlib
import json
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

import typer

from editoria.schemas import (
    Box,
    CaptionArtifacts,
    EditPlan,
    EncodeSettings,
    Finding,
    MixResult,
    OverlayClip,
    ProbeResult,
    QCReport,
    RenderInputs,
    StylePreset,
    read_model,
    to_data,
    write_model,
)
from editoria.util import log
from editoria.util.cli import fail, open_project
from editoria.util.ffmpeg import command_log
from editoria.util.ffmpeg import run as ffmpeg_run
from editoria.util.files import fmt_ts
from editoria.util.geometry import base_transform
from editoria.util.project import (
    PLAN_FILE,
    PROBE_FILE,
    SEGMENTS_FILE,
    TRANSCRIPT_FILE,
    VIDEO_FILE,
    ProjectContext,
)
from editoria.util.resources import emoji_path, font_family_dir

STYLES: tuple[str, ...] = ("A", "B", "C")
STYLE_NAMES = {"A": "Claridad profesional", "B": "Explicación visual", "C": "Ritmo y personalidad"}
SAMPLE_MIN_S, SAMPLE_MAX_S = 5.0, 10.0
FEEDBACK_QUESTION = (
    "¿Qué querés ajustar en las tomas, el ritmo, los subtítulos, los gráficos o el sonido? "
    "Podés indicarme el minuto/segundo y el cambio."
)


class PipelineError(RuntimeError):
    """User-facing (Spanish) pipeline failure."""


# --------------------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------------------
def parse_window(text: str | None) -> tuple[float, float] | None:
    if not text:
        return None
    try:
        a, b = (float(x) for x in text.replace("–", "-").split("-", 1))
    except ValueError as exc:
        raise PipelineError(f"Ventana inválida '{text}': usá a-b en segundos (ej. 2-9).") from exc
    if b <= a:
        raise PipelineError(f"Ventana inválida '{text}': el fin debe ser mayor que el inicio.")
    return a, b


def choose_window(ctx: ProjectContext, duration: float) -> tuple[float, float]:
    """Sample window for proposals: the hook segment widened to 5–10 s (or the whole video)."""
    if duration <= SAMPLE_MAX_S:
        return 0.0, round(duration, 3)
    start = 0.0
    if ctx.analysis(SEGMENTS_FILE).exists():
        segs = ctx.load_segments().segments
        hook = next((s for s in segs if s.role == "hook"), segs[0] if segs else None)
        if hook is not None:
            start = hook.start
    start = max(0.0, min(start, duration - SAMPLE_MIN_S))
    end = min(duration, start + SAMPLE_MAX_S)
    if end - start < SAMPLE_MIN_S:
        start = max(0.0, end - SAMPLE_MIN_S)
    return round(start, 3), round(end, 3)


def _overlaps(a0: float, a1: float, b0: float, b1: float) -> bool:
    return a0 < b1 and b0 < a1


def restrict_to_window(plan: EditPlan, window: tuple[float, float]) -> EditPlan:
    """Keep only graphics/SFX that touch the window (cheaper sample renders)."""
    a, b = window
    return plan.model_copy(
        update={
            "graphics": [g for g in plan.graphics if _overlaps(g.in_, g.out, a, b)],
            "sfx": [s for s in plan.sfx if a <= s.at <= b],
            "window": window,
        }
    )


def face_box_canvas(ctx: ProjectContext, plan: EditPlan, probe: ProbeResult) -> Box | None:
    face = ctx.load_face()
    if face is None or face.union_box is None:
        return None
    tr = base_transform(probe.display_width, probe.display_height, plan.canvas, face.union_box)
    return tr.to_canvas(face.union_box)


def emoji_overlays(plan: EditPlan) -> tuple[list[OverlayClip], list[str]]:
    """Emoji items -> GIF overlays (geometry from render.inputs). Missing GIFs are reported."""
    from editoria.render.inputs import emoji_overlays as _render_emojis

    missing = [
        f"{g.id}: falta {emoji_path(str(g.emoji)).name} (ejecutá scripts/fetch_assets.py)"
        for g in plan.graphics
        if g.is_emoji and not emoji_path(str(g.emoji)).exists()
    ]
    return _render_emojis(plan, set(), plan.canvas), missing


@dataclass
class BuildReport:
    """What was actually produced for a render (feeds resumen.md / P11)."""

    captions: CaptionArtifacts | None = None
    overlays: list[OverlayClip] = field(default_factory=list)
    mix: MixResult | None = None
    shots: list[str] = field(default_factory=list)
    pending: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)

    def to_json(self) -> dict[str, object]:
        return {
            "captions": bool(self.captions),
            "overlays": [o.id for o in self.overlays],
            "mix": to_data(self.mix) if self.mix else None,
            "shots": self.shots,
            "pending": self.pending,
            "findings": [to_data(f) for f in self.findings],
        }


def _lint(plan: EditPlan, ctx: ProjectContext) -> list[Finding]:
    from editoria.policy import lint_plan

    return lint_plan(plan, ctx)


def write_overlays(path: Path, items: list[OverlayClip]) -> None:
    """overlays.json with frame paths relative to its folder (the project stays movable)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for o in items:
        data = to_data(o)
        with contextlib.suppress(ValueError):
            data["frames_pattern"] = o.frames_pattern.relative_to(path.parent).as_posix()
        rows.append(data)
    path.write_text(json.dumps({"overlays": rows}, ensure_ascii=False, indent=2), encoding="utf-8")


def build_inputs(
    ctx: ProjectContext, plan: EditPlan, work: Path, style: StylePreset
) -> tuple[RenderInputs, BuildReport]:
    """captions -> graphics -> audio mix, written under ``work``. Failures of optional stages
    (graphics engine, missing emoji) degrade to warnings recorded as pending."""
    from editoria.audio import FFmpegAudioMixer
    from editoria.captions import AssCaptionBuilder
    from editoria.captions.layout import face_avoid_boxes
    from editoria.shots import ProjectShotLibrary

    rep = BuildReport()
    probe = ctx.load_probe()
    brand = ctx.load_brand()
    fps: Fraction = plan.canvas.resolve_fps(probe.fps)
    face = face_box_canvas(ctx, plan, probe)
    work.mkdir(parents=True, exist_ok=True)
    # libass scans fontsdir non-recursively: one helper resolves it for every render path.
    font_family = ctx.load_style(plan.captions.style).captions.font
    fonts = font_family_dir(font_family) or font_family_dir(brand.fonts.body)

    # 1. captions
    if plan.captions.enabled:
        cap_style = ctx.load_style(plan.captions.style)
        cuts = ctx.load_cuts()
        builder = AssCaptionBuilder(fonts_dir=fonts)
        rep.captions = builder.build(
            ctx.load_transcript(),
            cap_style,
            brand,
            plan.canvas,
            face_avoid_boxes(ctx.load_face(), plan.canvas, plan.video),
            plan.captions.emphasis,
            work,
            cuts=cuts.cuts if cuts else (),
            editorial_titles=plan.captions.editorial_titles,
            duration=probe.duration_s,
        )
        for w in builder.warnings:
            log.warn(w)
        events_json = work / "subtitulos.json"
        if not events_json.exists():
            events_json.write_text(
                json.dumps([to_data(e) for e in rep.captions.events], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    # 2. graphics (templates) + emojis
    template_items = [g for g in plan.graphics if not g.is_emoji]
    if template_items:
        try:
            from editoria.graphics import PlaywrightGraphicsRenderer

            with PlaywrightGraphicsRenderer() as renderer:
                for item in template_items:
                    try:  # a failing template only drops that item
                        rep.overlays.append(
                            renderer.render(
                                item, brand, plan.canvas, fps, work / "graficos" / item.id
                            )
                        )
                    except Exception as exc:
                        msg = f"Gráfico {item.id} ({item.template}) no renderizado: {exc}"
                        log.warn(msg)
                        rep.pending.append(msg)
        except Exception as exc:  # engine missing: degrade, never hide
            msg = f"Gráficos no renderizados (motor no disponible): {exc}"
            log.warn(msg)
            rep.pending.append(msg)
        if rep.overlays:
            write_overlays(work / "graficos" / "overlays.json", rep.overlays)
    emojis, missing = emoji_overlays(plan)
    rep.overlays.extend(emojis)
    for m in missing:
        log.warn(m)
        rep.pending.append(f"Emoji no incluido — {m}")

    # 3. audio
    if probe.has_audio:
        rep.mix = FFmpegAudioMixer(music_root=ctx.root).mix(
            ctx.original_video(), plan.sfx, plan.music, plan.mix, work / "audio" / "mezcla.wav"
        )
        write_model(work / "audio" / "mezcla.json", rep.mix)
    else:
        rep.pending.append("El VIDEO_BASE no tiene audio: no hay mezcla ni SFX.")

    # 4. accepted shots
    shots = ProjectShotLibrary().accepted(ctx)
    used = {iv.shot for iv in plan.video if iv.method == "generated" and iv.shot}
    rep.shots = sorted(used & set(shots))

    inputs = RenderInputs(
        captions_ass=rep.captions.ass if rep.captions else None,
        fonts_dir=fonts,
        overlays=rep.overlays,
        mix_wav=rep.mix.wav if rep.mix else None,
        shots={k: v for k, v in shots.items() if k in used},
        face_box_canvas=face,
    )
    return inputs, rep


# --------------------------------------------------------------------------------------
# render of a version
# --------------------------------------------------------------------------------------
def run_qc(ctx: ProjectContext, version: str) -> QCReport:
    from editoria.audio import FFmpegAudioMixer
    from editoria.qc import DefaultQualityControl

    mixer = FFmpegAudioMixer()
    return DefaultQualityControl(voice_checker=mixer.check_voice, linter=_lint).run(ctx, version)


def render_version(
    ctx: ProjectContext, version: str, enc: EncodeSettings | None = None
) -> tuple[Path, QCReport]:
    """lint -> captions -> graphics -> mix -> compose -> qc for 04_versiones/<version>/."""
    from editoria.policy import has_errors
    from editoria.render import FFmpegRenderer

    vdir = ctx.version_dir(version)
    plan_path = vdir / PLAN_FILE
    if not plan_path.exists():
        raise PipelineError(f"Falta {version}/plan.yaml. Creá el plan antes de renderizar.")
    if ctx.is_delivered(version):
        raise PipelineError(f"{version} ya fue entregada y es inmutable. Usá 'version new'.")
    # A rendered but undelivered version may be re-rendered (the renderer replaces the file
    # atomically); only delivered versions are immutable (P20).
    plan = read_model(plan_path, EditPlan)
    findings = _lint(plan, ctx)
    for f in findings:
        where = f" @ {fmt_ts(f.t)}" if f.t is not None else ""
        el = f" [{f.element}]" if f.element else ""
        (log.error if f.severity == "ERROR" else log.warn)(f"{f.id}{el}{where}: {f.message}")
    if has_errors(findings):
        raise PipelineError("El plan tiene errores de política: corregilos antes de renderizar.")

    style = ctx.load_style(plan.style)
    inputs, rep = build_inputs(ctx, plan, vdir, style)
    rep.findings = findings
    out = FFmpegRenderer().render(plan, ctx, inputs, vdir / VIDEO_FILE, enc or EncodeSettings())
    try:  # the QC and the reviewer read the contact sheet
        from editoria.render import contact_sheet

        contact_sheet(ctx, version, 2.0)
    except Exception as exc:
        rep.pending.append(f"Hoja de contactos no generada: {exc}")
    (vdir / "render.json").write_text(
        json.dumps(rep.to_json(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return out, run_qc(ctx, version)


# --------------------------------------------------------------------------------------
# proposals
# --------------------------------------------------------------------------------------
@dataclass
class Proposal:
    style: str
    plan_path: Path
    sample: Path | None
    pending: list[str]


def recommend(ctx: ProjectContext) -> tuple[str, str]:
    """Deterministic default recommendation; the creative director may override it."""
    tr = ctx.load_transcript() if ctx.analysis(TRANSCRIPT_FILE).exists() else None
    text = " ".join(w.text for w in tr.words) if tr else ""
    if any(ch.isdigit() for ch in text):
        return "B", (
            "el video menciona cifras o pasos concretos: una explicación visual con gráficos "
            "los vuelve más claros sin inventar datos."
        )
    return "A", (
        "es contenido de negocio y tecnología para responsables de empresa: subtítulos limpios "
        "y apoyos discretos priorizan la claridad y la voz."
    )


def propose(ctx: ProjectContext, window: tuple[float, float] | None = None) -> Path:
    """Exactly three proposals (A, B, C) on the same passage (P10) + comparativa_ABC.mp4."""
    from editoria.planning import DefaultPlanTools
    from editoria.policy import has_errors
    from editoria.render import FFmpegRenderer

    probe = ctx.load_probe()
    win = window or choose_window(ctx, probe.duration_s)
    tools = DefaultPlanTools()
    out_dir = ctx.proposals_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    proposals: list[Proposal] = []
    for sid in STYLES:
        style = ctx.load_style(sid)
        plan = tools.draft(ctx, style).model_copy(update={"window": win})
        plan_path = write_model(out_dir / f"plan_{sid}.yaml", plan)
        pending: list[str] = []
        sample: Path | None = None
        if has_errors(tools.lint(plan, ctx)):
            pending.append("El borrador no pasa el linter; muestra no renderizada.")
        else:
            work = out_dir / f"trabajo_{sid}"  # kept between runs: graphics cache lives here
            sample_plan = restrict_to_window(plan, win)
            inputs, rep = build_inputs(ctx, sample_plan, work, style)
            pending.extend(rep.pending)
            sample = FFmpegRenderer().render(
                sample_plan,
                ctx,
                inputs,
                out_dir / f"muestra_{sid}.mp4",
                EncodeSettings(preset="veryfast", crf=20, sample_window=win),
            )
        proposals.append(Proposal(sid, plan_path, sample, pending))

    comparativa = _comparativa(out_dir, proposals)
    rec, why = recommend(ctx)
    path = out_dir / "propuestas.md"
    path.write_text(
        _proposals_md(ctx, proposals, win, comparativa, rec, why), encoding="utf-8", newline="\n"
    )
    (out_dir / "recomendacion.json").write_text(
        json.dumps({"style": rec, "motivo": why, "window": list(win)}, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def _comparativa(out_dir: Path, proposals: list[Proposal]) -> Path | None:
    samples = [p.sample for p in proposals]
    if any(s is None or not s.exists() for s in samples):
        return None
    out = out_dir / "comparativa_ABC.mp4"
    graph = (
        "[0:v]scale=360:640,setsar=1[a];[1:v]scale=360:640,setsar=1[b];"
        "[2:v]scale=360:640,setsar=1[c];[a][b][c]hstack=inputs=3[v]"
    )
    inputs: list[str] = []
    for s in samples:
        inputs += ["-i", Path(str(s)).name]
    ffmpeg_run(
        [
            *inputs,
            "-filter_complex", graph, "-map", "[v]", "-map", "0:a?",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", out.name,
        ],
        cwd=out_dir,
    )  # fmt: skip
    return out


def _proposals_md(
    ctx: ProjectContext,
    proposals: list[Proposal],
    win: tuple[float, float],
    comparativa: Path | None,
    rec: str,
    why: str,
) -> str:
    keys = ("concepto", "refs", "metodo", "subs", "graf", "sonido", "muestra", "limites")
    rows: dict[str, list[str]] = {k: [] for k in keys}
    for p in proposals:
        st = ctx.load_style(p.style)
        plan = read_model(p.plan_path, EditPlan)
        methods = sorted({iv.method for iv in plan.video}) or ["original"]
        tpls = sorted({g.template or f"emoji {g.emoji}" for g in plan.graphics}) or ["—"]
        cues = sorted({s.cue for s in plan.sfx}) or ["—"]
        rows["concepto"].append(st.description or st.name)
        rows["refs"].append(", ".join(st.references) or "—")
        rows["metodo"].append(" / ".join(methods))
        rows["subs"].append(
            f"{st.captions.font} {st.captions.weight}, {st.captions.case}, "
            f"{st.captions.words_per_event} palabras, anim. {st.captions.animation}"
        )
        rows["graf"].append(", ".join(tpls))
        rows["sonido"].append(", ".join(cues))
        rows["muestra"].append(
            f"`muestra_{p.style}.mp4`" if p.sample else "no producida (ver limitaciones)"
        )
        rows["limites"].append("; ".join(p.pending) or "sin tomas generadas; render local")

    def row(label: str, key: str) -> str:
        return f"| {label} | " + " | ".join(c.replace("|", "/") for c in rows[key]) + " |"

    a, b = win
    return "\n".join(
        [
            "# Tres propuestas para el mismo video",
            "",
            f"Pasaje comparado en las tres muestras: {fmt_ts(a)}–{fmt_ts(b)} del VIDEO_BASE.",
            "",
            "| Campo | " + " | ".join(f"{s} — {STYLE_NAMES[s]}" for s in STYLES) + " |",
            "|---|---|---|---|",
            row("Concepto adaptado al contenido", "concepto"),
            "| Momento del VIDEO_BASE | " + " | ".join([f"{fmt_ts(a)}–{fmt_ts(b)}"] * 3) + " |",
            row("Referencias R / W", "refs"),
            row("Toma y método: original / reencuadre / generado", "metodo"),
            row("Sistema de subtítulos", "subs"),
            row("Gráfico o animación distintiva", "graf"),
            row("Sonido asociado", "sonido"),
            row("Archivo de muestra real, si existe", "muestra"),
            row("Complejidad y limitaciones", "limites"),
            "",
            "Comparativa lado a lado (A | B | C): "
            + (f"`{comparativa.name}`" if comparativa else "no producida (falta alguna muestra)."),
            "",
            f"Propuesta recomendada: **{rec} — {STYLE_NAMES[rec]}**",
            "",
            f"Motivo concreto: {why}",
            "",
            "Regla de avance: montar V1 con la recomendada, salvo instrucción expresa del "
            "usuario para esperar una elección previa (`proposal_mode: esperar`).",
            "",
        ]
    )


# --------------------------------------------------------------------------------------
# run (end to end, stops after V1)
# --------------------------------------------------------------------------------------
def run_project(
    ctx: ProjectContext, backend: str = "whisper", model: str = "large-v3-turbo"
) -> str:
    """probe -> transcribe -> analyze -> propose -> V1 -> deliver. Returns a status message."""
    from editoria.analysis import analyze_project
    from editoria.deliver import deliver
    from editoria.ingest import probe_project, transcribe_project
    from editoria.planning import DefaultPlanTools

    if not ctx.analysis(PROBE_FILE).exists():
        probe_project(ctx)
    if not ctx.analysis(TRANSCRIPT_FILE).exists():
        transcribe_project(ctx, model=model, backend=backend)
    if not ctx.analysis(SEGMENTS_FILE).exists():
        analyze_project(ctx)
    if not (ctx.proposals_dir / "propuestas.md").exists():
        propose(ctx)
    if ctx.load_config().proposal_mode == "esperar":
        return (
            "Propuestas listas en 03_propuestas/propuestas.md. proposal_mode = esperar: "
            "elegí A, B o C antes de montar V1."
        )
    if ctx.versions():
        return "Ya existe una versión. Tras V1 se espera feedback (skill aplicar-feedback)."
    rec = json.loads((ctx.proposals_dir / "recomendacion.json").read_text(encoding="utf-8"))
    plan = (
        DefaultPlanTools()
        .draft(ctx, ctx.load_style(rec["style"]))
        .model_copy(
            update={
                "version": "V1",
                "window": None,
                "notes": f"Propuesta {rec['style']} recomendada: {rec['motivo']}",
            }
        )
    )
    write_model(ctx.version_dir("V1") / PLAN_FILE, plan)
    _, report = render_version(ctx, "V1")
    if report.has_fail:
        return "V1 renderizada, pero el QC tiene FAIL: revisá 04_versiones/V1/qc/qc.md."
    deliver(ctx, "V1")
    return "V1 entregada en 04_versiones/V1/. " + FEEDBACK_QUESTION


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------
def register(app: typer.Typer) -> None:
    @app.command("propose")
    def propose_cmd(
        slug: str = typer.Argument(...),
        window: str | None = typer.Option(None, "--window", help="a-b en segundos"),
    ) -> None:
        """Tres muestras A/B/C sobre el mismo pasaje + comparativa."""
        ctx = open_project(slug)
        with command_log(ctx.commands_log):
            try:
                path = propose(ctx, parse_window(window))
            except PipelineError as exc:
                fail(str(exc))
        log.ok(f"Propuestas: {path}")

    @app.command("run")
    def run_cmd(
        slug: str = typer.Argument(...),
        backend: str = typer.Option("whisper", "--backend", help="whisper | fixture"),
        model: str = typer.Option("large-v3-turbo", "--model"),
    ) -> None:
        """Punta a punta; se detiene siempre tras V1."""
        ctx = open_project(slug)
        with command_log(ctx.commands_log):
            try:
                msg = run_project(ctx, backend=backend, model=model)
            except PipelineError as exc:
                fail(str(exc))
        log.info(msg)
