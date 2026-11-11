"""ffmpeg helpers for shots (everything goes through editoria.util.ffmpeg)."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

from editoria.schemas import Box, Canvas, parse_fps
from editoria.shots.errors import ShotError
from editoria.util import ffmpeg
from editoria.util.geometry import base_transform


@dataclass(frozen=True)
class VideoInfo:
    width: int  # display size (rotation applied)
    height: int
    fps: Fraction
    duration: float
    has_audio: bool
    pix_fmt: str
    nb_frames: int | None


def _rotation(stream: dict[str, Any]) -> int:
    for sd in stream.get("side_data_list", []) or []:
        if "rotation" in sd:
            return round(float(sd["rotation"]))
    rot = (stream.get("tags") or {}).get("rotate")
    return int(rot) if rot not in (None, "") else 0


def video_info(path: Path) -> VideoInfo:
    """First video stream facts; raises ShotError when the file is not a readable video."""
    try:
        data = ffmpeg.probe(path)
    except ffmpeg.FFmpegError as exc:
        raise ShotError(f"No se pudo leer '{path.name}' como video: {exc}") from exc
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if video is None or not video.get("width"):
        raise ShotError(f"'{path.name}' no contiene una pista de video.")
    w, h = int(video["width"]), int(video["height"])
    if abs(_rotation(video)) % 180 == 90:
        w, h = h, w
    fps_txt = video.get("avg_frame_rate") or "0/0"
    if fps_txt in ("0/0", "0"):
        fps_txt = video.get("r_frame_rate") or "0/0"
    fps = parse_fps(fps_txt) if fps_txt not in ("0/0", "0") else Fraction(0)
    nb = int(video["nb_frames"]) if str(video.get("nb_frames", "")).isdigit() else None
    dur = float(video.get("duration") or 0.0)
    if dur <= 0:
        dur = float(data.get("format", {}).get("duration") or 0.0)
    if dur <= 0 and nb and fps:
        dur = float(nb / fps)
    if fps <= 0 or dur <= 0:
        raise ShotError(f"'{path.name}' no tiene duración o FPS legibles.")
    return VideoInfo(
        width=w,
        height=h,
        fps=fps,
        duration=dur,
        has_audio=any(s.get("codec_type") == "audio" for s in streams),
        pix_fmt=str(video.get("pix_fmt", "")),
        nb_frames=nb,
    )


def scaled_face(
    info: VideoInfo, face_union: Box | None, face_frame: tuple[int, int] | None
) -> Box | None:
    """Face box (given in ``face_frame`` pixels) rescaled to the clip's own pixel size."""
    if face_union is None or not face_frame:
        return None
    sx, sy = info.width / face_frame[0], info.height / face_frame[1]
    return Box(
        x=round(face_union.x * sx),
        y=round(face_union.y * sy),
        w=round(face_union.w * sx),
        h=round(face_union.h * sy),
    )


def conform_filter(
    info: VideoInfo,
    canvas: Canvas,
    fps: Fraction,
    face: Box | None = None,
    pad_s: float = 0.0,
) -> str:
    """Filter chain that makes ``info`` fill the canvas exactly like the base video does.

    ``face`` must be in the clip's own pixels (see :func:`scaled_face`); it only matters when a
    landscape clip is cropped to 9:16 around the face (util.geometry.base_transform).
    """
    bt = base_transform(info.width, info.height, canvas, face)
    parts = [f"fps={fps.numerator}/{fps.denominator}"]
    if pad_s > 0:
        parts.append(f"tpad=stop_mode=clone:stop_duration={pad_s:.4f}")
    if (bt.crop_w, bt.crop_h) != (info.width, info.height):
        parts.append(f"crop={bt.crop_w}:{bt.crop_h}:{bt.crop_x}:{bt.crop_y}")
    parts += [f"scale={canvas.width}:{canvas.height}:flags=lanczos", "setsar=1", "format=yuv420p"]
    return ",".join(parts)


def encode_silent(
    src: Path,
    dst: Path,
    vf: str,
    duration: float,
    fps: Fraction,
    crf: int = 16,
) -> None:
    """Re-encode video only (no audio stream: P03), exact ``duration``, H.264 yuv420p."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg.run(
        [
            "-i", src,
            "-vf", vf,
            "-an", "-sn", "-dn",
            "-t", f"{duration:.6f}",
            "-c:v", "libx264", "-preset", "medium", "-crf", str(crf),
            "-pix_fmt", "yuv420p",
            "-r", f"{fps.numerator}/{fps.denominator}",
            "-movflags", "+faststart",
            dst,
        ]
    )  # fmt: skip


def extract_frame(src: Path, t: float, dst: Path, width: int | None = None) -> None:
    """Save the frame at ``t`` seconds (image format from ``dst`` suffix)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    args: list[str | Path] = ["-ss", f"{max(t, 0.0):.4f}", "-i", src, "-frames:v", "1"]
    if width:
        args += ["-vf", f"scale={width}:-2:flags=lanczos"]
    if dst.suffix.lower() in {".jpg", ".jpeg"}:
        args += ["-q:v", "2"]
    args.append(dst)
    ffmpeg.run(args)
    if not dst.exists():
        raise ShotError(f"No se pudo extraer un fotograma de '{src.name}' en t={t:.2f}s.")
