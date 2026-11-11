"""``probe``: metadata, integrity and warnings of the VIDEO_BASE (writes 01_analisis/probe.json)."""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path
from statistics import median
from typing import Any

from editoria.schemas import AudioInfo, ProbeResult, fps_str, parse_fps, write_model
from editoria.util import ffmpeg
from editoria.util.project import PROBE_FILE, ProjectContext

CORRUPTION_PREFIX = "Posible corrupción"
MIN_WIDTH = 1080
VFR_RATE_TOLERANCE = 0.02  # relative difference between r_frame_rate and avg_frame_rate
VFR_GAP_FACTOR = 1.5  # a frame gap this much longer than the median means variable timing


def _fraction(text: Any) -> Fraction | None:
    try:
        frac = parse_fps(str(text))
    except (ValueError, ZeroDivisionError):
        return None
    return frac if frac > 0 else None


def _rotation(stream: dict[str, Any]) -> int:
    """Display rotation in degrees (0/90/180/270, counter-clockwise as ffmpeg reports it)."""
    raw: Any = None
    for side in stream.get("side_data_list", []) or []:
        if "rotation" in side:
            raw = side["rotation"]
            break
    if raw is None:
        raw = (stream.get("tags") or {}).get("rotate")
    try:
        return int(round(float(raw))) % 360 if raw is not None else 0
    except (TypeError, ValueError):
        return 0


def _frame_gaps_vary(path: Path) -> bool:
    """True when presentation timestamps are irregular (dropped/variable frames)."""
    proc = ffmpeg.run(
        [
            "-v", "error", "-select_streams", "v:0",
            "-show_entries", "packet=pts_time", "-of", "csv=p=0", str(path),
        ],
        tool="ffprobe",
        check=False,
    )  # fmt: skip
    times: list[float] = []
    for line in proc.stdout.splitlines():
        try:
            times.append(float(line.strip().rstrip(",")))
        except ValueError:
            continue
    times.sort()
    gaps = [b - a for a, b in zip(times, times[1:], strict=False) if b - a > 1e-6]
    if len(gaps) < 3:
        return False
    return max(gaps) > VFR_GAP_FACTOR * median(gaps)


def build_probe(data: dict[str, Any], *, irregular_timestamps: bool = False) -> ProbeResult:
    """Turn ffprobe JSON into a :class:`ProbeResult` (without decode check or warnings).

    VFR means the declared rates disagree or the caller saw irregular frame timestamps.
    """
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if video is None:
        raise ValueError("El archivo no tiene pista de video.")
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)

    r_rate = _fraction(video.get("r_frame_rate"))
    avg_rate = _fraction(video.get("avg_frame_rate"))
    rates_differ = bool(
        r_rate and avg_rate and abs(float(r_rate - avg_rate)) / float(r_rate) > VFR_RATE_TOLERANCE
    )
    vfr = rates_differ or irregular_timestamps
    rate = (avg_rate if rates_differ else r_rate) or avg_rate or r_rate or Fraction(30)

    duration = float(data.get("format", {}).get("duration") or video.get("duration") or 0.0)
    frames = str(video.get("nb_frames", ""))
    return ProbeResult(
        duration_s=duration,
        width=int(video["width"]),
        height=int(video["height"]),
        fps=fps_str(rate),
        vfr=vfr,
        rotation=_rotation(video),
        has_audio=audio is not None,
        audio=AudioInfo(
            codec=str(audio.get("codec_name", "")),
            sr=int(audio.get("sample_rate") or 0),
            ch=int(audio.get("channels") or 0),
        )
        if audio
        else None,
        video_codec=str(video.get("codec_name", "")),
        pix_fmt=str(video.get("pix_fmt", "")),
        nb_frames=int(frames) if frames.isdigit() else None,
    )


def decode_errors(path: Path) -> list[str]:
    """Decode the whole file (``-v error -f null -``) and return the error lines, if any."""
    proc = ffmpeg.run(["-v", "error", "-i", str(path), "-f", "null", "-"], check=False)
    lines = [ln.strip() for ln in proc.stderr.splitlines() if ln.strip()]
    if proc.returncode != 0 and not lines:
        lines = [f"ffmpeg terminó con código {proc.returncode}"]
    return lines


def make_warnings(result: ProbeResult, errors: list[str] | None = None) -> list[str]:
    """Spanish warnings for the issues the pipeline cares about."""
    out: list[str] = []
    if errors:
        sample = errors[0][:120]
        out.append(
            f"{CORRUPTION_PREFIX}: el decodificador reportó {len(errors)} error(es) "
            f"(p. ej. «{sample}»). Volvé a exportar el video desde CapCut."
        )
    if result.vfr:
        out.append(
            "El video tiene velocidad de cuadros variable (VFR): puede desincronizar subtítulos "
            "y gráficos. Convertilo a velocidad constante antes de editar."
        )
    if result.rotation:
        out.append(
            f"El video trae metadatos de rotación ({result.rotation}°): se usa la orientación "
            f"visible ({result.display_width}x{result.display_height})."
        )
    if not result.is_vertical:
        out.append(
            f"El video es horizontal ({result.display_width}x{result.display_height}): para "
            "llenar el lienzo 9:16 se recorta el centro y se amplía; se pierde encuadre y detalle."
        )
    if result.display_width < MIN_WIDTH:
        out.append(
            f"El ancho es {result.display_width} px (< {MIN_WIDTH}): los reencuadres y el zoom "
            "tendrán menos detalle nativo."
        )
    if not result.has_audio:
        out.append(
            "El video no tiene pista de audio: no hay voz para transcribir ni audio base "
            "sobre el cual mezclar."
        )
    return out


def probe_file(path: Path) -> ProbeResult:
    """Probe an arbitrary media file (no project needed): metadata + integrity + warnings."""
    result = build_probe(ffmpeg.probe(path), irregular_timestamps=_frame_gaps_vary(path))
    result.warnings = make_warnings(result, decode_errors(path))
    return result


def probe_project(ctx: ProjectContext) -> ProbeResult:
    """Probe the project's original and write ``01_analisis/probe.json``."""
    with ffmpeg.command_log(ctx.commands_log):
        result = probe_file(ctx.original_video())
    write_model(ctx.analysis(PROBE_FILE), result)
    return result


def has_corruption(result: ProbeResult) -> bool:
    return any(w.startswith(CORRUPTION_PREFIX) for w in result.warnings)
