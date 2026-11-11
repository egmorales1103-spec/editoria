"""Value objects exchanged between modules at runtime (see editoria.contracts)."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field

from editoria.schemas.base import Box, Model, Seconds


class CaptionEvent(Model):
    start: Seconds
    end: Seconds
    text: str  # final text as displayed (case applied), lines joined with "\n"
    word_ids: list[int] = Field(default_factory=list)
    box: Box | None = None  # estimated canvas-space box of the rendered block
    editorial: bool = False


class CaptionArtifacts(Model):
    ass: Path
    srt: Path
    vtt: Path
    events: list[CaptionEvent] = Field(default_factory=list)


class OverlayClip(Model):
    """A rendered overlay to composite on the canvas."""

    id: str
    frames_pattern: Path  # e.g. .../g01/%05d.png (RGBA). For emojis: path to the .gif
    frame_count: int = 0
    fps: str = "30/1"
    x: int  # top-left on the canvas (px)
    y: int
    w: int
    h: int
    start: Seconds  # base timeline
    end: Seconds
    is_gif: bool = False
    labels: list[str] = Field(default_factory=list)  # e.g. ["Ejemplo"], ["Ilustración"]


class MixResult(Model):
    wav: Path
    lufs: float
    true_peak: float
    lra: float | None = None
    clipped_samples: int = 0
    voice_to_sfx_db: float | None = None


class VoiceCheck(Model):
    offset_ms: float
    similarity: float  # 0..1 normalised cross-correlation peak


class ConformedClip(Model):
    shot_id: str
    path: Path  # conformed, silent video matching canvas/fps/pix_fmt
    start: Seconds  # where it goes on the base timeline
    end: Seconds
    width: int
    height: int


class RenderInputs(Model):
    """Everything the compositor needs besides the plan and the base video."""

    captions_ass: Path | None = None
    fonts_dir: Path | None = None
    overlays: list[OverlayClip] = Field(default_factory=list)  # graphics + emojis
    mix_wav: Path | None = None  # None = use base audio untouched
    shots: dict[str, ConformedClip] = Field(default_factory=dict)
    face_box_canvas: Box | None = None


class EncodeSettings(Model):
    preset: str = "medium"  # samples: veryfast
    crf: int = 18
    audio_bitrate: str = "192k"
    audio_sr: int = 48000
    sample_window: tuple[Seconds, Seconds] | None = None
    max_zoom: float = 1.25  # P07 guard over native pixels
