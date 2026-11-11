"""ffmpeg based detectors: silences (silencedetect) and hard cuts (scene score)."""

from __future__ import annotations

import re
from pathlib import Path

from editoria.schemas import CutList, Interval, SilenceList
from editoria.util import ffmpeg

NOISE_DB = -35.0
MIN_SILENCE_S = 0.25
SCENE_THRESHOLD = 0.3

_SIL_START = re.compile(r"silence_start:\s*(-?\d+(?:\.\d+)?)")
_SIL_END = re.compile(r"silence_end:\s*(-?\d+(?:\.\d+)?)")
_PTS_TIME = re.compile(r"pts_time:\s*(\d+(?:\.\d+)?)")


def parse_silencedetect(stderr: str, duration: float) -> list[Interval]:
    """Parse silencedetect log lines into intervals; a trailing open silence ends at duration."""
    out: list[Interval] = []
    start: float | None = None
    for line in stderr.splitlines():
        if (m := _SIL_START.search(line)) is not None:
            start = max(float(m.group(1)), 0.0)
        elif (m := _SIL_END.search(line)) is not None and start is not None:
            out.append(Interval(start=round(start, 3), end=round(float(m.group(1)), 3)))
            start = None
    if start is not None and duration > start:
        out.append(Interval(start=round(start, 3), end=round(duration, 3)))
    return out


def detect_silences(
    video: Path,
    duration: float,
    *,
    has_audio: bool = True,
    noise_db: float = NOISE_DB,
    min_duration_s: float = MIN_SILENCE_S,
) -> SilenceList:
    if not has_audio:
        return SilenceList(noise_db=noise_db, min_duration_s=min_duration_s, silences=[])
    proc = ffmpeg.run(
        ["-i", str(video), "-vn", "-af", f"silencedetect=noise={noise_db}dB:d={min_duration_s}",
         "-f", "null", "-"]
    )  # fmt: skip
    return SilenceList(
        noise_db=noise_db,
        min_duration_s=min_duration_s,
        silences=parse_silencedetect(proc.stderr, duration),
    )


def parse_showinfo_times(stderr: str) -> list[float]:
    return [round(float(m.group(1)), 3) for m in _PTS_TIME.finditer(stderr)]


def detect_cuts(video: Path, threshold: float = SCENE_THRESHOLD) -> CutList:
    """Hard cuts: frames whose scene-change score exceeds ``threshold`` (timestamps in s)."""
    proc = ffmpeg.run(
        ["-i", str(video), "-an", "-vf", f"select='gt(scene,{threshold})',showinfo",
         "-f", "null", "-"]
    )  # fmt: skip
    times = sorted({t for t in parse_showinfo_times(proc.stderr) if t > 0})
    return CutList(method="select_scene", threshold=threshold, cuts=times)
