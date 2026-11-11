"""Pure builder: EditPlan + RenderInputs -> ffmpeg inputs and a filtergraph script.

Layer order (bottom to top): base video (with reframes) -> generated shots -> graphics
(PNG sequences) -> emojis (GIF) -> ASS captions. The base timeline is never retimed: every
frame of the VIDEO_BASE is emitted once, in order, and the audio is the base audio or the
mix (never the audio of a generated shot).

Paths inside the graph are relative to ``cwd`` (the version folder): Windows + spaces +
accents break absolute paths in filter options, and libass cannot open non-ASCII paths.

Sample windows ``a-b`` seek in the INPUT (``-ss a -t b-a`` before the base and the mix), so
only the window is decoded. Sync is kept by restoring the original timeline right after the
base: ``setpts=PTS+a/TB`` (single segment) or after the concat of the clipped segments.
Every later layer (generated shots, graphics, emojis, ASS captions) keeps using
original-time timestamps unchanged; the final ``trim=start=a:end=b,setpts=PTS-STARTPTS``
brings the window back to 0, and the audio (seeked the same way) starts at 0 too. A
``push`` reframe that starts before ``a`` continues its zoom from the frame it would have
reached (``on`` offset), so the sample matches the full render.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

from editoria.render.geometry import (
    ZoomGuardError,
    anchor_source,
    base_for,
    reframe_crop,
    scale_face,
    zoom_violation,
)
from editoria.render.media import MediaInfo, rel_to
from editoria.schemas import (
    EditPlan,
    EncodeSettings,
    FaceTrack,
    OverlayClip,
    RenderInputs,
    VideoInterval,
    fps_str,
    parse_fps,
)
from editoria.util.ffmpeg import escape_filter_path

WARN_UPSCALE = (
    "La fuente ({w}×{h}) es menor que el lienzo {cw}×{ch}: se escala con lanczos, "
    "sin detalle nativo nuevo."
)
WARN_HORIZONTAL = (
    "La fuente es horizontal ({w}×{h}): se recorta a 9:16 {where}; se pierde el resto del cuadro."
)


class RenderError(RuntimeError):
    """User-facing (Spanish) render failure."""


@dataclass
class RenderGraph:
    input_args: list[str]
    script: str
    video_label: str
    audio_label: str | None
    duration: float
    fps: Fraction
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _Segment:
    start: float
    end: float | None  # None = until the end of the base
    iv: VideoInterval | None  # reframe interval, or None for the plain base
    skipped: float = 0.0  # seconds of the reframe cut off by a sample window (push offset)


def _t(x: float) -> str:
    """Seconds for ffmpeg options: fixed decimals, no exponent."""
    s = f"{x:.6f}".rstrip("0").rstrip(".")
    return s or "0"


def _intervals(plan: EditPlan, duration: float, warnings: list[str]) -> list[VideoInterval]:
    ivs = sorted(plan.video, key=lambda iv: iv.in_)
    out: list[VideoInterval] = []
    prev_end = 0.0
    for iv in ivs:
        if iv.in_ < prev_end - 1e-6:
            raise RenderError(
                f"El intervalo {iv.id} ({iv.in_:.2f}s) se superpone con el anterior: la pista "
                "de video no admite solapes (P04)."
            )
        if iv.in_ >= duration:
            warnings.append(f"El intervalo {iv.id} empieza después del final del video; se omite.")
            continue
        if iv.out > duration + 1e-3:
            warnings.append(
                f"El intervalo {iv.id} termina después del final ({duration:.2f}s); se recorta."
            )
            iv = iv.model_copy(update={"out": duration})
        out.append(iv)
        prev_end = iv.out
    return out


def _segments(ivs: list[VideoInterval], duration: float) -> list[_Segment]:
    """Contiguous cover of [0, duration]: reframes get their own segment, the rest is base."""
    segs: list[_Segment] = []
    cursor = 0.0
    for iv in ivs:
        if iv.method != "reframe":
            continue
        if iv.in_ > cursor + 1e-6:
            segs.append(_Segment(cursor, iv.in_, None))
        segs.append(_Segment(iv.in_, iv.out, iv))
        cursor = iv.out
    if cursor < duration - 1e-6 or not segs:
        segs.append(_Segment(cursor, None, None))
    else:
        last = segs[-1]
        segs[-1] = _Segment(last.start, None, last.iv)
    return segs


def _clip_segments(segs: list[_Segment], a: float, b: float) -> list[_Segment]:
    """Segments that touch the window [a, b], clipped to it (the last one stays open)."""
    out: list[_Segment] = []
    for seg in segs:
        end = seg.end if seg.end is not None else float("inf")
        if end <= a + 1e-6 or seg.start >= b - 1e-6:
            continue
        start = max(seg.start, a)
        new_end = seg.end if seg.end is not None and seg.end < b - 1e-6 else None
        out.append(_Segment(start, new_end, seg.iv, skipped=start - seg.start))
    if out and out[-1].end is not None:
        last = out[-1]
        out[-1] = _Segment(last.start, None, last.iv, last.skipped)
    return out


def _overlay_dims(ov: OverlayClip) -> str:
    return f"scale={ov.w}:{ov.h}:flags=lanczos,format=rgba"


def _ascii_rel(path: Path, cwd: Path, name: str, warnings: list[str]) -> str:
    """Relative path usable by libass; non-ASCII locations are copied into ``cwd``."""
    rel = rel_to(path, cwd)
    if rel.isascii():
        return rel
    target = cwd / name
    shutil.copyfile(path, target)
    warnings.append(f"Se copió {path.name} junto al video porque su ruta tiene acentos.")
    return target.name


def build_render_graph(
    plan: EditPlan,
    inputs: RenderInputs,
    base: MediaInfo,
    base_path: Path,
    cwd: Path,
    enc: EncodeSettings,
    face: FaceTrack | None = None,
) -> RenderGraph:
    """Assemble the ffmpeg input arguments and filtergraph for one render."""
    if not base.has_video or base.width <= 0:
        raise RenderError("El VIDEO_BASE no tiene una pista de video legible.")
    warnings: list[str] = []
    canvas = plan.canvas
    W, H = canvas.width, canvas.height
    fps = canvas.resolve_fps(base.fps)
    duration = base.duration
    face = scale_face(face, base.width, base.height)
    bt = base_for(base.width, base.height, canvas, face)

    if bt.upscaled:
        warnings.append(WARN_UPSCALE.format(w=base.width, h=base.height, cw=W, ch=H))
    if bt.cropped_horizontal:
        where = "centrado en el rostro" if face is not None else "centrado (sin datos de rostro)"
        warnings.append(WARN_HORIZONTAL.format(w=base.width, h=base.height, where=where))

    # sample window: seek in the input, keep original-time timestamps inside the graph
    a, b = 0.0, duration
    windowed = enc.sample_window is not None
    if enc.sample_window is not None:
        a, b = enc.sample_window
        b = min(b, duration)
        if not 0 <= a < b:
            raise RenderError(f"Ventana de muestra inválida: {a}-{b}.")
    seek = ["-ss", _t(a)] if a > 0 else []
    seek += ["-t", _t(b - a)] if windowed else []
    shift = f"setpts=PTS+{_t(a)}/TB," if a > 0 else ""

    ivs = _intervals(plan, duration, warnings)
    for iv in ivs:
        if iv.method == "reframe":
            msg = zoom_violation(bt, iv.zoom, enc.max_zoom)
            if msg:
                raise ZoomGuardError(f"Reencuadre {iv.id} rechazado (P07): {msg}.")

    args: list[str] = [*seek, "-i", rel_to(base_path, cwd)]
    n_inputs = 1
    lines: list[str] = []

    full = bt.crop_x == 0 and bt.crop_y == 0 and bt.crop_w == base.width
    full = full and bt.crop_h == base.height
    base_crop = "" if full else f"crop={bt.crop_w}:{bt.crop_h}:{bt.crop_x}:{bt.crop_y},"
    finish = f"scale={W}:{H}:flags=lanczos,setsar=1,format=yuv420p"

    # 1) base + reframes -------------------------------------------------------------
    segs = _segments(ivs, duration)
    if windowed:
        segs = _clip_segments(segs, a, b)
    if len(segs) == 1 and segs[0].iv is None:
        lines.append(f"[0:v]{shift}{base_crop}{finish},fps={fps_str(fps)}[v0]")
    else:
        names = [f"[s{i}]" for i in range(len(segs))]
        lines.append(f"[0:v]{shift}split={len(segs)}{''.join(names)}")
        for i, seg in enumerate(segs):
            trim = f"trim=start={_t(seg.start)}"
            if seg.end is not None:
                trim += f":end={_t(seg.end)}"
            chain = f"{base_crop}{finish}"
            if seg.iv is not None:
                iv = seg.iv
                z = iv.zoom or 1.0
                anchor = anchor_source(iv, bt, face)
                if iv.motion == "push":
                    seg_end = min(iv.out, duration)
                    n = max(2, round((seg_end - iv.in_) * float(fps)))
                    ax = anchor[0] - bt.crop_x
                    ay = anchor[1] - bt.crop_y
                    k0 = round(seg.skipped * float(fps))  # frames cut off by the window
                    on = f"(on+{k0})" if k0 > 0 else "on"
                    zexpr = f"1+{z - 1:.6f}*min({on}/{n - 1}\\,1)"
                    xexpr = f"max(0\\,min(iw-iw/zoom\\,{ax:.2f}-iw/zoom/2))"
                    yexpr = f"max(0\\,min(ih-ih/zoom\\,{ay:.2f}-ih/zoom/2))"
                    chain = (
                        f"{base_crop}zoompan=z='{zexpr}':x='{xexpr}':y='{yexpr}'"
                        f":d=1:s={W}x{H}:fps={fps_str(fps)},setsar=1,format=yuv420p"
                    )
                else:
                    c = reframe_crop(bt, z, anchor)
                    chain = f"crop={c.w}:{c.h}:{c.x}:{c.y},{finish}"
            lines.append(f"[s{i}]{trim},setpts=PTS-STARTPTS,{chain}[g{i}]")
        concat_in = "".join(f"[g{i}]" for i in range(len(segs)))
        lines.append(f"{concat_in}concat=n={len(segs)}:v=1:a=0,{shift}fps={fps_str(fps)}[v0]")
    cur = "v0"
    step = 0

    def nxt() -> str:
        nonlocal step
        step += 1
        return f"v{step}"

    # 2) generated shots (silent overlays of conformed clips) ----------------------------
    for iv in ivs:
        if iv.method != "generated":
            continue
        clip = inputs.shots.get(iv.shot or "")
        if clip is None:
            raise RenderError(
                f"La toma generada '{iv.shot}' del intervalo {iv.id} no está aceptada o no se "
                "encontró (P05). Usá material original o aceptá la toma con 'shots verdict'."
            )
        if iv.out <= a + 1e-6 or iv.in_ >= b - 1e-6:
            continue  # outside the sample window
        offset = max(0.0, iv.in_ - clip.start)
        d = iv.out - iv.in_
        k = n_inputs
        args += ["-i", rel_to(clip.path, cwd)]
        n_inputs += 1
        lines.append(
            f"[{k}:v]trim=start={_t(offset)}:duration={_t(d)},setpts=PTS-STARTPTS+{_t(iv.in_)}/TB,"
            f"{finish},fps={fps_str(fps)}[sh{k}]"
        )
        out = nxt()
        lines.append(f"[{cur}][sh{k}]overlay=0:0:eof_action=pass[{out}]")
        cur = out

    # 3) graphics, then 4) emojis ---------------------------------------------------------
    overlays = sorted(inputs.overlays, key=lambda o: (o.is_gif, o.start))
    for ov in overlays:
        src = Path(ov.frames_pattern)
        if ov.is_gif:
            if not src.is_file():
                warnings.append(f"Falta el emoji {ov.id} ({src.name}); se omite.")
                continue
        elif not src.parent.is_dir() or not any(src.parent.glob("*.png")):
            warnings.append(f"Falta la secuencia del gráfico {ov.id}; se omite.")
            continue
        start = max(0.0, ov.start)
        end = min(ov.end, duration)
        if end <= start:
            warnings.append(f"El gráfico {ov.id} queda fuera del video; se omite.")
            continue
        if end <= a + 1e-6 or start >= b - 1e-6:
            continue  # outside the sample window
        d = end - start
        k = n_inputs
        if ov.is_gif:
            args += ["-ignore_loop", "0", "-t", _t(d + 1.0), "-i", rel_to(src, cwd)]
        else:
            args += ["-framerate", fps_str(parse_fps(ov.fps)), "-i", rel_to(src, cwd)]
        n_inputs += 1
        lines.append(
            f"[{k}:v]trim=duration={_t(d)},setpts=PTS-STARTPTS+{_t(start)}/TB,"
            f"{_overlay_dims(ov)}[o{k}]"
        )
        out = nxt()
        lines.append(
            f"[{cur}][o{k}]overlay=x={ov.x}:y={ov.y}:eof_action=pass"
            f":enable='between(t\\,{_t(start)}\\,{_t(end)})'[{out}]"
        )
        cur = out

    # 5) captions (ASS, last) ------------------------------------------------------------
    if inputs.captions_ass is not None and plan.captions.enabled:
        ass = Path(inputs.captions_ass)
        if not ass.is_file():
            warnings.append(f"No existe {ass.name}; el video sale sin subtítulos.")
        else:
            rel = _ascii_rel(ass, cwd, "_render_subtitulos.ass", warnings)
            opts = f"filename={escape_filter_path(rel)}"
            if inputs.fonts_dir is not None and Path(inputs.fonts_dir).is_dir():
                frel = rel_to(inputs.fonts_dir, cwd)
                if frel.isascii():
                    opts += f":fontsdir={escape_filter_path(frel)}"
                else:
                    warnings.append("La carpeta de fuentes tiene acentos; libass usará el sistema.")
            else:
                warnings.append("Sin carpeta de fuentes local: libass usará fuentes del sistema.")
            out = nxt()
            lines.append(f"[{cur}]ass={opts}[{out}]")
            cur = out

    # sample window + final label ------------------------------------------------------
    if windowed:
        lines.append(f"[{cur}]trim=start={_t(a)}:end={_t(b)},setpts=PTS-STARTPTS[vout]")
    else:
        lines.append(f"[{cur}]null[vout]")

    # audio: the mix or the base audio, never a generated shot ---------------------------
    audio_label: str | None = None
    src_a: str | None = None
    if inputs.mix_wav is not None and Path(inputs.mix_wav).is_file():
        args += [*seek, "-i", rel_to(inputs.mix_wav, cwd)]
        src_a = f"{n_inputs}:a"
        n_inputs += 1
    else:
        if inputs.mix_wav is not None:
            warnings.append("No se encontró la mezcla; se usa el audio del VIDEO_BASE.")
        if base.has_audio:
            src_a = "0:a"
        else:
            warnings.append("El VIDEO_BASE no tiene audio y no hay mezcla: el video sale mudo.")
    if src_a is not None:
        lines.append(
            f"[{src_a}]aresample={enc.audio_sr},"
            f"aformat=sample_rates={enc.audio_sr}:channel_layouts=stereo,"
            f"apad,atrim=start=0:end={_t(b - a)},asetpts=PTS-STARTPTS[aout]"  # inputs seeked
        )
        audio_label = "aout"

    script = ";\n".join(lines) + "\n"
    return RenderGraph(
        input_args=args,
        script=script,
        video_label="vout",
        audio_label=audio_label,
        duration=b - a,
        fps=fps,
        warnings=warnings,
    )
