"""Director preview: middle frame PNG + short MP4 of a template over a grey 9:16 canvas."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

from PIL import Image

from editoria.graphics.renderer import FRAME_PATTERN, FRAME_START, PlaywrightGraphicsRenderer
from editoria.schemas import BrandProfile, Canvas, OverlayClip, Zone, fps_str
from editoria.util import ffmpeg

GREY = (128, 128, 128)
FRAMES_SUBDIR = "cuadros"


@dataclass(frozen=True)
class PreviewResult:
    clip: OverlayClip
    mid_png: Path
    mp4: Path
    ms_per_frame: float


def compose_on_grey(clip: OverlayClip, frame_png: Path, canvas: Canvas, out: Path) -> Path:
    bg = Image.new("RGB", (canvas.width, canvas.height), GREY)
    with Image.open(frame_png) as raw:
        im = raw.convert("RGBA")
        bg.paste(im, (clip.x, clip.y), im)
    out.parent.mkdir(parents=True, exist_ok=True)
    bg.save(out)
    return out


def encode_preview(clip: OverlayClip, canvas: Canvas, out_dir: Path, mp4_name: str) -> Path:
    """Overlay the PNG sequence on a grey canvas with ffmpeg (cwd + relative paths)."""
    fps = fps_str(Fraction(clip.fps))
    dur = clip.end - clip.start
    frames_rel = Path(FRAMES_SUBDIR) / FRAME_PATTERN
    ffmpeg.run(
        [
            "-f",
            "lavfi",
            "-i",
            f"color=c=0x808080:s={canvas.width}x{canvas.height}:r={fps}:d={dur:.3f}",
            "-framerate",
            fps,
            "-start_number",
            str(FRAME_START),
            "-i",
            frames_rel.as_posix(),
            "-filter_complex",
            f"[0:v][1:v]overlay=x={clip.x}:y={clip.y}:format=auto:eof_action=pass,format=yuv420p",
            "-frames:v",
            str(clip.frame_count),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-movflags",
            "+faststart",
            mp4_name,
        ],
        cwd=out_dir,
    )
    return out_dir / mp4_name


def preview_template(
    template_id: str,
    params: dict[str, Any],
    out_dir: Path,
    *,
    brand: BrandProfile,
    canvas: Canvas | None = None,
    fps: Fraction = Fraction(30),
    duration: float | None = None,
    zone: Zone | None = None,
    renderer: PlaywrightGraphicsRenderer | None = None,
) -> PreviewResult:
    canvas = canvas or Canvas()
    out_dir = Path(out_dir)
    own = renderer is None
    r = renderer or PlaywrightGraphicsRenderer()
    try:
        clip = r.render_template(
            template_id,
            params,
            brand=brand,
            canvas=canvas,
            fps=fps,
            out_dir=out_dir / FRAMES_SUBDIR,
            duration=duration,
            zone=zone,
        )
        ms = r.last_stats.ms_per_frame if r.last_stats else 0.0
    finally:
        if own:
            r.close()
    mid = FRAME_START + clip.frame_count // 2
    mid_png = compose_on_grey(
        clip,
        out_dir / FRAMES_SUBDIR / f"{mid:05d}.png",
        canvas,
        out_dir / f"{template_id}_medio.png",
    )
    mp4 = encode_preview(clip, canvas, out_dir, f"{template_id}_preview.mp4")
    return PreviewResult(clip, mid_png, mp4, ms)
