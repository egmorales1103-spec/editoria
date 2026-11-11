"""Local models for shot packs and comparisons (stored next to the shot files)."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from editoria.schemas import Model, Seconds

Recommendation = Literal["estable", "revisar", "deriva"]


class ImportInfo(Model):
    """What was really received and how it was conformed (no invented data)."""

    received: str  # relative path of the stored raw copy
    received_sha256: str
    received_width: int
    received_height: int
    received_fps: str
    received_duration_s: Seconds
    received_had_audio: bool
    trimmed: bool = False
    conformed: str  # relative path of the conformed, silent clip
    width: int
    height: int
    fps: str


class ShotMeta(Model):
    """pack/<id>/meta.json: everything needed to import and compare a shot later."""

    id: str
    root: str  # id of the first attempt of this segment (== id for attempt 1)
    attempt: int = 1
    source: str  # relative path of the original video
    start: Seconds
    end: Seconds
    duration: Seconds
    fps: str
    width: int  # display size of the source segment
    height: int
    change: str
    prompt: str
    pack_dir: str  # relative path
    imported: ImportInfo | None = None


class CompareResult(Model):
    shot_id: str
    frames: int
    ssim_background: float  # area-weighted mean of the background SSIM (1.0 = identical)
    ssim_background_min: float  # worst region mean
    flicker: float  # RMS of the extra frame-to-frame luma change of the background (0-255)
    color_delta_e: float  # CIELAB distance between mean background colours
    t_motion: Seconds  # time (within the segment) of the frame with the most motion
    face_box_canvas: list[int] | None = None  # x, y, w, h of the dilated face box
    recommendation: Recommendation
    reasons: list[str] = Field(default_factory=list)
    sheet: str = ""
    metrics_file: str = ""
    side_by_side: str = ""
