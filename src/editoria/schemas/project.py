"""Project-level configuration and ingest/analysis artifacts."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import Field

from editoria.schemas.base import Box, Interval, Method, Model, Seconds, parse_fps


class Budget(Model):
    unit: str = "creditos"
    limit: float | None = None  # None = no authorised limit -> nothing paid may be submitted
    spent: float = 0.0

    @property
    def remaining(self) -> float | None:
        return None if self.limit is None else max(self.limit - self.spent, 0.0)


class ToolLimits(Model):
    higgsfield_max_clip_s: float | None = None  # None = "verificar en la herramienta"
    max_attempts: int | None = None


class ProjectConfig(Model):
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    brand: str = "master-solution"
    target: Literal["reels", "tiktok", "shorts"] = "reels"
    aspect: Literal["9:16"] = "9:16"
    proposal_mode: Literal["auto", "esperar"] = "auto"
    budget: Budget = Field(default_factory=Budget)
    tool_limits: ToolLimits = Field(default_factory=ToolLimits)
    original: str = ""  # relative path, e.g. "00_original/video_base.mp4"
    original_sha256: str = ""
    source_name: str = ""  # original filename as given by the user
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AudioInfo(Model):
    codec: str
    sr: int
    ch: int


class ProbeResult(Model):
    duration_s: Seconds
    width: int
    height: int
    fps: str  # fraction "30/1", "30000/1001"
    vfr: bool = False
    rotation: int = 0
    has_audio: bool
    audio: AudioInfo | None = None
    video_codec: str
    pix_fmt: str
    nb_frames: int | None = None
    warnings: list[str] = Field(default_factory=list)

    @property
    def fps_fraction(self):  # type: ignore[no-untyped-def]
        return parse_fps(self.fps)

    @property
    def display_width(self) -> int:
        return self.height if abs(self.rotation) % 180 == 90 else self.width

    @property
    def display_height(self) -> int:
        return self.width if abs(self.rotation) % 180 == 90 else self.height

    @property
    def is_vertical(self) -> bool:
        return self.display_height > self.display_width


class Word(Model):
    text: str
    start: Seconds
    end: Seconds
    prob: float = Field(ge=0, le=1)
    flagged: bool = False


class TranscriptSegment(Model):
    start: Seconds
    end: Seconds
    text: str
    first_word: int  # index into Transcript.words (inclusive)
    last_word: int  # inclusive


class Transcript(Model):
    language: str = "es"
    model: str
    words: list[Word]
    segments: list[TranscriptSegment] = Field(default_factory=list)
    audio_sha256: str = ""


class Segment(Model):
    """Editorial segment of the VIDEO_BASE (sentence/pause based). Roles filled by the director."""

    id: str
    start: Seconds
    end: Seconds
    text: str
    role: Literal["hook", "body", "example", "closing"] | None = None
    intent: str = ""
    visual: str = ""
    reference: str = ""
    method: Method | None = None


class SegmentList(Model):
    segments: list[Segment]


class SilenceList(Model):
    noise_db: float = -35.0
    min_duration_s: float = 0.25
    silences: list[Interval]


class CutList(Model):
    method: str = "scdet"
    threshold: float = 0.3
    cuts: list[Seconds]  # timestamps of hard cuts in the VIDEO_BASE


class FaceSample(Model):
    t: Seconds
    box: Box | None  # source-pixel coordinates; None = no face in that sample


class FaceTrack(Model):
    """Face boxes in SOURCE pixel coordinates (frame_w x frame_h, after rotation)."""

    frame_w: int
    frame_h: int
    samples: list[FaceSample] = Field(default_factory=list)
    union_box: Box | None = None
    estimated: bool = False  # True when no detector ran (fixed upper-centre zone)
