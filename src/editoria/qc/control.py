"""DefaultQualityControl: §10 of the prompt + the QC rules of the policy table (section 6)."""

from __future__ import annotations

import importlib
import json
from collections.abc import Callable
from fractions import Fraction
from pathlib import Path

from editoria.qc.analysis import (
    VideoAnalysis,
    analyze_media,
    correlate_voice,
    count_clipped,
    is_faststart,
    new_spans,
)
from editoria.qc.captions import caption_boxes
from editoria.qc.report import write_report
from editoria.render.geometry import (
    base_for,
    face_boxes_on_canvas,
    scale_face,
    zoom_violation,
)
from editoria.render.media import MediaInfo, probe_media
from editoria.schemas import (
    EditPlan,
    EncodeSettings,
    Finding,
    QCCheck,
    QCReport,
    QCStatus,
    VoiceCheck,
)
from editoria.util import resources
from editoria.util.files import is_read_only, read_csv_rows, sha256_file
from editoria.util.project import VIDEO_FILE, ProjectContext

VoiceChecker = Callable[[Path, Path], VoiceCheck]
Linter = Callable[[EditPlan, ProjectContext], list[Finding]]

# Questions of §10 of the prompt (Spanish, verbatim intent).
Q1 = "¿El archivo exportado abre y reproduce completo, con imagen y audio?"
Q2 = "¿Conserva mis palabras, mi voz, el orden del mensaje y los cortes esenciales?"
Q3 = "¿Toda toma generada mantiene mi apariencia, el escenario y la sincronización visible?"
Q4 = "¿No hay objetos nuevos, fondo inestable, deformaciones, cuadros negros o parpadeos?"
Q5 = "¿Los subtítulos coinciden con el audio, están bien escritos y se leen en móvil?"
Q6 = "¿Los gráficos explican algo y respetan la marca sin fingir resultados?"
Q7 = "¿La voz se entiende y los efectos coinciden con la imagen?"
Q8 = "¿La duración y el formato corresponden al material entregado y al destino?"
Q9 = "¿Están identificados los archivos reales, los pendientes y las limitaciones?"
QUESTIONS = (Q1, Q2, Q3, Q4, Q5, Q6, Q7, Q8, Q9)

# Thresholds
SYNC_PASS_MS = 45.0
SYNC_WARN_MS = 100.0
SIM_FAIL = 0.3
SIM_WARN = 0.6
LUFS_TOL = 1.0
CLIP_FAIL = 10


def _q(rule: str, question: str) -> str:
    return f"{rule} · {question}" if rule else question


def _check(
    cid: str,
    rule: str,
    question: str,
    status: QCStatus,
    detail: str,
    evidence: list[str] | None = None,
) -> QCCheck:
    return QCCheck(
        id=cid,
        prompt_question=_q(rule, question),
        status=status,
        detail=detail,
        evidence=evidence or [],
    )


def _fmt_spans(spans: list[tuple[float, float]]) -> str:
    return ", ".join(f"{a:.2f}–{b:.2f}s" for a, b in spans)


def _default_linter() -> Linter | None:
    try:
        mod = importlib.import_module("editoria.policy")
    except ImportError:
        return None
    fn = getattr(mod, "lint_plan", None)
    return fn if callable(fn) else None


class DefaultQualityControl:
    """Implements :class:`editoria.contracts.QualityControl`.

    ``voice_checker(base, final)`` defaults to a cross-correlation fallback; ``linter`` to
    ``editoria.policy.lint_plan`` when available (both injectable).
    """

    def __init__(
        self,
        voice_checker: VoiceChecker | None = None,
        linter: Linter | None = None,
    ) -> None:
        self.voice_checker: VoiceChecker = voice_checker or correlate_voice
        self.linter = linter if linter is not None else _default_linter()

    # ------------------------------------------------------------------------------------
    def run(self, ctx: ProjectContext, version: str) -> QCReport:
        vdir = ctx.version_dir(version)
        checks: list[QCCheck] = []
        plan: EditPlan | None = None
        try:
            plan = ctx.load_plan(version)
        except Exception as exc:
            checks.append(_check("plan", "", Q9, "FAIL", f"No se pudo leer plan.yaml: {exc}"))

        original = ctx.original_video()
        orig = probe_media(original)
        video = vdir / VIDEO_FILE

        checks.append(self._original_hash(ctx, original))
        if not video.is_file():
            checks.append(_check("decode", "", Q1, "FAIL", f"No existe {VIDEO_FILE} en {version}."))
        else:
            try:
                checks += self._media_checks(ctx, plan, video, original, orig)
            except Exception as exc:  # report, never crash the whole QC
                checks.append(
                    _check("media", "", Q1, "FAIL", f"No se pudo analizar el video: {exc}")
                )
        if plan is not None:
            checks.append(self._zoom_guard(ctx, plan, orig))
            checks.append(self._captions(ctx, plan, vdir, orig, video))
            checks.append(self._shots(ctx, plan))
            checks.append(self._licenses(plan))
            if self.linter is not None:
                checks.append(self._lint(ctx, plan))
        checks.append(self._deliverables(vdir))
        checks += self._human(plan)

        report = QCReport(version=version, checks=checks)
        report.summary = summarize(report)
        write_report(report, vdir / "qc")
        return report

    # ---- media ---------------------------------------------------------------------------
    def _media_checks(
        self,
        ctx: ProjectContext,
        plan: EditPlan | None,
        video: Path,
        original: Path,
        orig: MediaInfo,
    ) -> list[QCCheck]:
        out: list[QCCheck] = []
        try:
            info = probe_media(video)
        except Exception as exc:
            return [_check("decode", "", Q1, "FAIL", f"ffprobe no pudo leer el video: {exc}")]
        ana = analyze_media(video, audio=info.has_audio, duration=info.duration)
        out.append(self._decode(info, orig, ana))
        out.append(self._format(plan, info, orig))
        out.append(self._faststart(video))
        out.append(self._duration(info, orig))
        ref = analyze_media(original, audio=False, duration=orig.duration)
        out += self._black_freeze(ana, ref)
        out.append(self._loudness(ctx, plan, video, info, orig, ana))
        out.append(self._voice(original, video, info, orig))
        return out

    def _decode(self, info: MediaInfo, orig: MediaInfo, ana: VideoAnalysis) -> QCCheck:
        problems = []
        if not info.has_video:
            problems.append("sin pista de video")
        if orig.has_audio and not info.has_audio:
            problems.append("sin pista de audio (el original tiene audio)")
        ev = ana.decode_errors[:10]
        if ana.decode_errors:
            problems.append(f"{len(ana.decode_errors)} errores de decodificación")
        if problems:
            return _check("decode", "", Q1, "FAIL", "; ".join(problems), ev)
        audio = "con audio" if info.has_audio else "sin audio (el original tampoco tiene)"
        return _check(
            "decode",
            "",
            Q1,
            "PASS",
            f"Se decodificó completo ({info.duration:.2f}s) sin errores, {audio}.",
        )

    def _format(self, plan: EditPlan | None, info: MediaInfo, orig: MediaInfo) -> QCCheck:
        w = plan.canvas.width if plan else 1080
        h = plan.canvas.height if plan else 1920
        want_fps = plan.canvas.resolve_fps(orig.fps) if plan else orig.fps
        issues = []
        if info.video_codec != "h264":
            issues.append(f"códec de video {info.video_codec} (se espera h264)")
        if "high" not in info.profile.lower():
            issues.append(f"perfil {info.profile or '?'} (se espera High)")
        if info.pix_fmt != "yuv420p":
            issues.append(f"pix_fmt {info.pix_fmt} (se espera yuv420p)")
        if (info.width, info.height) != (w, h):
            issues.append(f"resolución {info.width}×{info.height} (se espera {w}×{h})")
        if abs(float(info.fps) - float(want_fps)) > 0.01:
            issues.append(f"FPS {_fps(info.fps)} (se espera {_fps(want_fps)})")
        if info.has_audio:
            if info.audio_codec != "aac":
                issues.append(f"códec de audio {info.audio_codec} (se espera aac)")
            if info.audio_sr != 48000:
                issues.append(f"audio a {info.audio_sr} Hz (se espera 48000)")
        ev = [
            f"video: {info.video_codec} {info.profile} {info.pix_fmt} {info.width}×{info.height} "
            f"@ {_fps(info.fps)}",
            f"audio: {info.audio_codec or '-'} {info.audio_sr or '-'} Hz "
            f"{info.audio_channels or '-'} canales",
        ]
        if issues:
            return _check("format", "P19", Q8, "FAIL", "; ".join(issues), ev)
        return _check("format", "P19", Q8, "PASS", "MP4 H.264 High/yuv420p, AAC 48 kHz, 9:16.", ev)

    def _faststart(self, video: Path) -> QCCheck:
        ok, atoms = is_faststart(video)
        ev = [" → ".join(f"{k}@{off}" for k, off in atoms[:8])]
        if ok:
            return _check("faststart", "P19", Q8, "PASS", "moov antes de mdat (+faststart).", ev)
        return _check("faststart", "P19", Q8, "FAIL", "moov no está antes de mdat.", ev)

    def _duration(self, info: MediaInfo, orig: MediaInfo) -> QCCheck:
        frame = orig.frame_s
        diff = abs(info.duration - orig.duration)
        ev = [
            f"original {orig.duration:.3f}s · final {info.duration:.3f}s · "
            f"diferencia {diff * 1000:.1f} ms · 1 cuadro = {frame * 1000:.1f} ms"
        ]
        if diff <= frame + 1e-3:
            return _check(
                "duration", "P04", Q8, "PASS", "Duración igual al original (±1 cuadro).", ev
            )
        return _check(
            "duration",
            "P04",
            Q8,
            "FAIL",
            f"La duración difiere {diff:.3f}s del original (más de 1 cuadro).",
            ev,
        )

    def _black_freeze(self, ana: VideoAnalysis, ref: VideoAnalysis) -> list[QCCheck]:
        nb = new_spans(ana.black, ref.black)
        ev_b = [
            f"final: {_fmt_spans(ana.black) or 'ninguno'}",
            f"original: {_fmt_spans(ref.black) or 'ninguno'}",
        ]
        black = (
            _check("black", "", Q4, "FAIL", f"Cuadros negros nuevos: {_fmt_spans(nb)}.", ev_b)
            if nb
            else _check("black", "", Q4, "PASS", "Sin cuadros negros nuevos.", ev_b)
        )
        nf = new_spans(ana.freeze, ref.freeze)
        ev_f = [
            f"final: {_fmt_spans(ana.freeze) or 'ninguno'}",
            f"original: {_fmt_spans(ref.freeze) or 'ninguno'}",
        ]
        freeze = (
            _check(
                "freeze",
                "",
                Q4,
                "WARN",
                f"Imagen congelada nueva: {_fmt_spans(nf)}. Revisá esos tramos.",
                ev_f,
            )
            if nf
            else _check("freeze", "", Q4, "PASS", "Sin congelamientos nuevos.", ev_f)
        )
        return [black, freeze]

    def _loudness(
        self,
        ctx: ProjectContext,
        plan: EditPlan | None,
        video: Path,
        info: MediaInfo,
        orig: MediaInfo,
        ana: VideoAnalysis,
    ) -> QCCheck:
        if not info.has_audio:
            status: QCStatus = "FAIL" if orig.has_audio else "PASS"
            return _check("loudness", "P18", Q7, status, "El video final no tiene audio.")
        target = plan.mix.target_lufs if plan else -14.0
        tp_max = plan.mix.true_peak_db if plan else -1.0
        clipped = count_clipped(video)
        ev = [
            f"integrado {ana.lufs} LUFS (objetivo {target}) · LRA {ana.lra} LU · "
            f"true peak {ana.true_peak} dBTP (máx. {tp_max}) · muestras saturadas {clipped}"
        ]
        mix_json = video.parent / "audio" / "mezcla.json"
        if mix_json.is_file():
            try:
                mj = json.loads(mix_json.read_text(encoding="utf-8"))
                if mj.get("voice_to_sfx_db") is not None:
                    ev.append(f"relación voz/SFX: {mj['voice_to_sfx_db']} dB (mezcla.json)")
            except ValueError:
                pass
        fails, warns = [], []
        if clipped > CLIP_FAIL:
            fails.append(f"{clipped} muestras saturadas (clipping)")
        elif clipped:
            warns.append(f"{clipped} muestras al máximo")
        if ana.true_peak is not None:
            if ana.true_peak > 0.0:
                fails.append(f"true peak {ana.true_peak:.1f} dBTP > 0")
            elif ana.true_peak > tp_max + 0.3:
                warns.append(f"true peak {ana.true_peak:.1f} dBTP sobre el máximo {tp_max}")
        if ana.lufs is None:
            warns.append("no se pudo medir la sonoridad")
        elif abs(ana.lufs - target) > LUFS_TOL:
            warns.append(f"sonoridad {ana.lufs:.1f} LUFS lejos del objetivo {target:.1f}")
        if fails:
            return _check("loudness", "P18", Q7, "FAIL", "; ".join(fails + warns), ev)
        if warns:
            return _check("loudness", "P18", Q7, "WARN", "; ".join(warns), ev)
        return _check(
            "loudness", "P18", Q7, "PASS", "Sonoridad, true peak y clipping en rango.", ev
        )

    def _voice(self, original: Path, video: Path, info: MediaInfo, orig: MediaInfo) -> QCCheck:
        if not orig.has_audio:
            return _check("voice_sync", "P03", Q2, "PASS", "El original no tiene audio: no aplica.")
        if not info.has_audio:
            return _check("voice_sync", "P03", Q2, "FAIL", "El video final no tiene la voz.")
        vc = self.voice_checker(original, video)
        ev = [f"desfase {vc.offset_ms:+.1f} ms · similitud {vc.similarity:.3f}"]
        off = abs(vc.offset_ms)
        if vc.similarity < SIM_FAIL:
            return _check(
                "voice_sync", "P03", Q2, "FAIL", "La voz del final no coincide con la original.", ev
            )
        if off > SYNC_WARN_MS:
            return _check(
                "voice_sync", "P03", Q2, "FAIL", f"Desfase de voz de {vc.offset_ms:+.0f} ms.", ev
            )
        if off > SYNC_PASS_MS or vc.similarity < SIM_WARN:
            return _check(
                "voice_sync",
                "P03",
                Q2,
                "WARN",
                f"Desfase {vc.offset_ms:+.0f} ms / similitud {vc.similarity:.2f}: revisar.",
                ev,
            )
        return _check(
            "voice_sync", "P03", Q2, "PASS", "La voz original está presente y sincronizada.", ev
        )

    # ---- project rules ------------------------------------------------------------------
    def _original_hash(self, ctx: ProjectContext, original: Path) -> QCCheck:
        digest = sha256_file(original)
        expected = set()
        try:
            cfg_hash = ctx.load_config().original_sha256
            if cfg_hash:
                expected.add(cfg_hash.lower())
        except Exception:
            pass
        sha_file = ctx.original_sha256_path()
        if sha_file.is_file():
            first = sha_file.read_text(encoding="utf-8").split()
            if first:
                expected.add(first[0].lower())
        ev = [f"sha256 actual {digest}", *(f"registrado {e}" for e in sorted(expected))]
        if not expected:
            return _check("original_hash", "P01", Q2, "WARN", "No hay hash registrado.", ev)
        if any(e != digest for e in expected):
            return _check(
                "original_hash",
                "P01",
                Q2,
                "FAIL",
                "El VIDEO_BASE fue alterado (hash distinto).",
                ev,
            )
        if not is_read_only(original):
            return _check(
                "original_hash",
                "P01",
                Q2,
                "WARN",
                "Hash correcto, pero el original no es de solo lectura.",
                ev,
            )
        return _check("original_hash", "P01", Q2, "PASS", "El VIDEO_BASE está intacto.", ev)

    def _zoom_guard(self, ctx: ProjectContext, plan: EditPlan, orig: MediaInfo) -> QCCheck:
        face = scale_face(ctx.load_face(), orig.width, orig.height)
        bt = base_for(orig.width, orig.height, plan.canvas, face)
        max_native = EncodeSettings().max_zoom
        try:
            style_max = ctx.load_style(plan.style).reframe.max_zoom
        except Exception:
            style_max = max_native
        fails, warns, ev = [], [], []
        if bt.upscaled:
            warns.append(
                f"fuente {orig.width}×{orig.height} escalada {bt.scale:.2f}×: "
                "sin detalle nativo nuevo"
            )
        if bt.cropped_horizontal:
            warns.append("fuente horizontal recortada a 9:16")
        for iv in plan.video:
            if iv.method != "reframe":
                continue
            z = iv.zoom or 1.0
            ev.append(f"{iv.id}: zoom {z:.2f}× · {bt.scale * z:.2f}× sobre píxeles nativos")
            msg = zoom_violation(bt, z, max_native)
            if msg:
                fails.append(f"{iv.id}: {msg}")
            elif z > style_max + 1e-6:
                warns.append(f"{iv.id}: zoom {z:.2f}× supera el del estilo ({style_max:.2f}×)")
        if fails:
            return _check("zoom_guard", "P07", Q4, "FAIL", "; ".join(fails + warns), ev)
        if warns:
            return _check("zoom_guard", "P07", Q4, "WARN", "; ".join(warns), ev)
        return _check("zoom_guard", "P07", Q4, "PASS", "Reencuadres dentro del límite de zoom.", ev)

    def _captions(
        self, ctx: ProjectContext, plan: EditPlan, vdir: Path, orig: MediaInfo, video: Path
    ) -> QCCheck:
        if not plan.captions.enabled:
            return _check("captions", "P12", Q5, "PASS", "Subtítulos desactivados en el plan.")
        boxes, source = caption_boxes(vdir, plan.canvas)
        if not boxes:
            return _check(
                "captions", "P12", Q5, "FAIL", "No hay subtitulos.ass ni subtitulos.json."
            )
        safe = plan.canvas.safe_box()
        face = ctx.load_face()
        duration = orig.duration
        fails, warns, ev = [], [], [f"fuente: {source} ({len(boxes)} eventos)"]
        for cb in boxes:
            tag = f"{cb.start:.2f}–{cb.end:.2f}s «{cb.text[:40]}»"
            b = cb.box
            on_face = [
                f
                for f in face_boxes_on_canvas(plan, face, orig.width, orig.height, cb.start, cb.end)
                if f.intersects(b)
            ]
            if on_face:
                fails.append(f"{tag} tapa el rostro")
                ev.append(f"{tag}: caja {b.x},{b.y} {b.w}×{b.h} vs rostro {on_face[0]}")
            inside = b.x >= safe.x and b.y >= safe.y and b.x2 <= safe.x2 and b.y2 <= safe.y2
            if not inside:
                msg = f"{tag} sale de la zona segura"
                vertical = b.y < safe.y or b.y2 > safe.y2
                if cb.estimated and not vertical:
                    warns.append(msg + " (estimado)")
                else:
                    fails.append(msg)
                ev.append(f"{tag}: caja {b.x},{b.y} {b.w}×{b.h} vs zona segura {safe}")
            if cb.end > duration + 0.05:
                warns.append(f"{tag} termina después del final del video")
        if fails:
            return _check("captions", "P12", Q5, "FAIL", "; ".join(fails[:6]), ev[:20])
        if warns:
            return _check("captions", "P12", Q5, "WARN", "; ".join(warns[:6]), ev[:20])
        return _check(
            "captions",
            "P12",
            Q5,
            "PASS",
            "Subtítulos dentro de la zona segura y fuera del rostro.",
            ev,
        )

    def _shots(self, ctx: ProjectContext, plan: EditPlan) -> QCCheck:
        used = [iv for iv in plan.video if iv.method == "generated"]
        if not used:
            return _check("shots_accepted", "P05", Q3, "PASS", "No se usan tomas generadas.")
        rows = {r.get("id", ""): r for r in read_csv_rows(ctx.generations_registry)}
        bad, ev = [], []
        for iv in used:
            row = rows.get(iv.shot or "")
            verdict = (row or {}).get("veredicto", "")
            ev.append(f"{iv.id} → {iv.shot}: {verdict or 'sin registro'}")
            if verdict != "aceptado":
                bad.append(f"{iv.shot} ({verdict or 'sin registro'})")
        if bad:
            return _check(
                "shots_accepted", "P05", Q3, "FAIL", f"Tomas no aceptadas: {', '.join(bad)}.", ev
            )
        return _check(
            "shots_accepted", "P05", Q3, "PASS", "Todas las tomas usadas están aceptadas.", ev
        )

    def _licenses(self, plan: EditPlan) -> QCCheck:
        manifests = [resources.load_sfx_manifest(), resources.load_external_manifest()]

        def licensed(asset_id: str) -> bool:
            for m in manifests:
                entry = m.get(asset_id)
                if entry is not None and entry.license.strip():
                    return True
            return False

        used: list[str] = [f"{c.cue}_{c.variant or 1}" for c in plan.sfx]
        used += [str(g.emoji) for g in plan.graphics if g.is_emoji]
        if plan.music is not None:
            used.append(plan.music.asset_id)
        used = sorted(set(used))
        if not used:
            return _check("licenses", "P17", Q6, "PASS", "No se usan SFX, emojis ni música.")
        missing = [a for a in used if not licensed(a)]
        ev = [f"usados: {', '.join(used)}"]
        if missing:
            return _check(
                "licenses",
                "P17",
                Q6,
                "FAIL",
                f"Recursos sin licencia registrada: {', '.join(missing)}.",
                ev,
            )
        return _check("licenses", "P17", Q6, "PASS", "Todos los recursos tienen licencia.", ev)

    def _lint(self, ctx: ProjectContext, plan: EditPlan) -> QCCheck:
        assert self.linter is not None
        try:
            findings = self.linter(plan, ctx)
        except Exception as exc:
            return _check("plan_lint", "", Q6, "WARN", f"No se pudo ejecutar el linter: {exc}")
        ev = [f"{f.severity} {f.id}: {f.message}" for f in findings][:20]
        if any(f.severity == "ERROR" for f in findings):
            return _check("plan_lint", "", Q6, "FAIL", "El plan tiene errores de política.", ev)
        if findings:
            return _check("plan_lint", "", Q6, "WARN", "El plan tiene avisos de política.", ev)
        return _check("plan_lint", "", Q6, "PASS", "El plan pasa el linter de políticas.")

    def _deliverables(self, vdir: Path) -> QCCheck:
        expected = [
            VIDEO_FILE,
            "plan.yaml",
            "subtitulos.srt",
            "subtitulos.vtt",
            "subtitulos.ass",
            "filtergraph.txt",
            "hoja_contactos.jpg",
        ]
        present = [n for n in expected if (vdir / n).is_file()]
        pending = [n for n in expected if n not in present]
        ev = [
            f"reales: {', '.join(present) or 'ninguno'}",
            f"pendientes: {', '.join(pending) or 'ninguno'}",
        ]
        if VIDEO_FILE not in present:
            return _check("deliverables", "P11", Q9, "FAIL", "Falta el video final.", ev)
        if "subtitulos.srt" not in present and "subtitulos.vtt" not in present:
            return _check("deliverables", "P11", Q9, "WARN", "Faltan los subtítulos SRT/VTT.", ev)
        return _check(
            "deliverables", "P11", Q9, "PASS", "Archivos reales y pendientes identificados.", ev
        )

    def _human(self, plan: EditPlan | None) -> list[QCCheck]:
        generated = bool(plan and any(iv.method == "generated" for iv in plan.video))
        reframes = bool(plan and any(iv.method == "reframe" for iv in plan.video))
        extra = " Incluye tomas generadas: revisalas cuadro a cuadro." if generated else ""
        where = [
            w for w, used in (("reencuadres", reframes), ("tomas generadas", generated)) if used
        ]
        lips_where = f" en {' y '.join(where)}" if where else ""
        checks = [
            _check(
                "identity",
                "P24",
                Q3,
                "HUMAN",
                "Confirmar rostro, piel, cabello, ropa y gestos sin cambios ni embellecimiento."
                + extra,
            ),
            _check(
                "background",
                "P08",
                Q4,
                "HUMAN",
                "Confirmar fondo idéntico: objetos, luz, colores y sin deformaciones." + extra,
            ),
            _check(
                "lips",
                "P03",
                Q3,
                "HUMAN",
                f"Confirmar sincronía visible de labios{lips_where}." + extra,
            ),
            _check(
                "aesthetic",
                "",
                Q6,
                "HUMAN",
                "Criterio estético: ritmo, jerarquía visual, marca, ortografía de subtítulos y "
                "que los gráficos expliquen sin fingir resultados.",
            ),
        ]
        if generated:
            checks.append(
                _check(
                    "generated_shots",
                    "P24",
                    Q3,
                    "HUMAN",
                    "Hay tomas generadas: revisión humana obligatoria de identidad, fondo "
                    "y labios.",
                )
            )
        return checks


def _fps(f: Fraction) -> str:
    return f"{float(f):.3f}".rstrip("0").rstrip(".")


def summarize(report: QCReport) -> str:
    c = report.counts()
    text = f"PASS {c['PASS']} · WARN {c['WARN']} · FAIL {c['FAIL']} · REVISIÓN HUMANA {c['HUMAN']}"
    if report.has_fail:
        return f"Hay fallas: no entregar. {text}"
    return f"Sin fallas automáticas; falta la revisión humana. {text}"
