"""Media facts the renderer and QC need, read through :func:`editoria.util.ffmpeg.probe`."""

from __future__ import annotations

import os
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

from editoria.schemas import parse_fps
from editoria.util import ffmpeg


@dataclass(frozen=True)
class MediaInfo:
    """Display-oriented facts of a media file (rotation already applied to width/height)."""

    path: Path
    width: int
    height: int
    fps: Fraction
    duration: float  # video stream duration (falls back to container duration)
    format_duration: float
    has_video: bool
    has_audio: bool
    video_codec: str = ""
    profile: str = ""
    pix_fmt: str = ""
    audio_codec: str = ""
    audio_sr: int = 0
    audio_channels: int = 0
    nb_frames: int | None = None

    @property
    def frame_s(self) -> float:
        return float(1 / self.fps) if self.fps else 1 / 30


def _rotation(stream: dict[str, Any]) -> int:
    tags = stream.get("tags", {}) or {}
    if "rotate" in tags:
        try:
            return int(float(tags["rotate"]))
        except ValueError:
            return 0
    for side in stream.get("side_data_list", []) or []:
        if "rotation" in side:
            try:
                return int(float(side["rotation"]))
            except (TypeError, ValueError):
                return 0
    return 0


def _stream_fps(stream: dict[str, Any]) -> Fraction:
    for key in ("avg_frame_rate", "r_frame_rate"):
        value = str(stream.get(key) or "0/0")
        if value not in {"0/0", "0", ""}:
            try:
                fr = parse_fps(value)
            except (ValueError, ZeroDivisionError):
                continue
            if fr > 0:
                return fr
    return Fraction(30, 1)


def probe_media(path: Path | str) -> MediaInfo:
    """Probe ``path`` (relative paths are resolved against its folder, as cwd)."""
    p = Path(path)
    data = ffmpeg.probe(p.name, cwd=p.parent if p.parent != Path() else None)
    streams = data.get("streams", []) or []
    fmt = data.get("format", {}) or {}
    v = next((s for s in streams if s.get("codec_type") == "video"), None)
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)
    fmt_dur = float(fmt.get("duration") or 0.0)
    if v is None:
        return MediaInfo(
            path=p,
            width=0,
            height=0,
            fps=Fraction(0, 1),
            duration=fmt_dur,
            format_duration=fmt_dur,
            has_video=False,
            has_audio=a is not None,
            audio_codec=str(a.get("codec_name", "")) if a else "",
            audio_sr=int(a.get("sample_rate") or 0) if a else 0,
            audio_channels=int(a.get("channels") or 0) if a else 0,
        )
    w, h = int(v.get("width") or 0), int(v.get("height") or 0)
    if abs(_rotation(v)) % 180 == 90:
        w, h = h, w
    vdur = float(v.get("duration") or 0.0) or fmt_dur
    nb = v.get("nb_frames")
    return MediaInfo(
        path=p,
        width=w,
        height=h,
        fps=_stream_fps(v),
        duration=vdur,
        format_duration=fmt_dur,
        has_video=True,
        has_audio=a is not None,
        video_codec=str(v.get("codec_name", "")),
        profile=str(v.get("profile", "")),
        pix_fmt=str(v.get("pix_fmt", "")),
        audio_codec=str(a.get("codec_name", "")) if a else "",
        audio_sr=int(a.get("sample_rate") or 0) if a else 0,
        audio_channels=int(a.get("channels") or 0) if a else 0,
        nb_frames=int(nb) if nb and str(nb).isdigit() and int(nb) > 0 else None,
    )


def rel_to(path: Path | str, cwd: Path) -> str:
    """Path of ``path`` relative to ``cwd`` with forward slashes (absolute if on another drive)."""
    p = Path(path)
    try:
        rel = os.path.relpath(p.resolve(), cwd.resolve())
    except ValueError:  # different drive on Windows
        return p.resolve().as_posix()
    return Path(rel).as_posix()
