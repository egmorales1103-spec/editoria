"""Module interfaces (frozen at contracts-v0). Implementations live in each module.

Each module also exposes ``cli.register(app: typer.Typer) -> None``.
"""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path
from typing import Protocol, runtime_checkable

from editoria.schemas import (
    Box,
    BrandProfile,
    Canvas,
    CaptionArtifacts,
    ConformedClip,
    EditPlan,
    Emphasis,
    EncodeSettings,
    Finding,
    GraphicItem,
    MixResult,
    MixSpec,
    MusicSpec,
    OverlayClip,
    QCReport,
    RenderInputs,
    SfxCue,
    StylePreset,
    Transcript,
    VoiceCheck,
)
from editoria.util.project import ProjectContext


@runtime_checkable
class CaptionBuilder(Protocol):
    """A2. Writes subtitulos.ass/.srt/.vtt into out_dir. `avoid` boxes are canvas-space."""

    def build(
        self,
        transcript: Transcript,
        style: StylePreset,
        brand: BrandProfile,
        canvas: Canvas,
        avoid: list[Box],
        emphasis: list[Emphasis],
        out_dir: Path,
    ) -> CaptionArtifacts: ...


@runtime_checkable
class GraphicsRenderer(Protocol):
    """A3. Renders one template GraphicItem to an RGBA PNG sequence (%05d.png)."""

    def render(
        self, item: GraphicItem, brand: BrandProfile, canvas: Canvas, fps: Fraction, out_dir: Path
    ) -> OverlayClip: ...


@runtime_checkable
class AudioMixer(Protocol):
    """A4. Base audio + SFX (+ optional music) -> loudness-normalised WAV (48 kHz)."""

    def mix(
        self,
        base_video: Path,
        cues: list[SfxCue],
        music: MusicSpec | None,
        spec: MixSpec,
        out_wav: Path,
    ) -> MixResult: ...

    def check_voice(self, base_video: Path, final_media: Path) -> VoiceCheck: ...


@runtime_checkable
class ShotLibrary(Protocol):
    """A6. Only shots with verdict 'aceptado', conformed and silent."""

    def accepted(self, ctx: ProjectContext) -> dict[str, ConformedClip]: ...


@runtime_checkable
class PlanTools(Protocol):
    """A2. Draft a plan for a style and lint it against the policies (section 6)."""

    def draft(self, ctx: ProjectContext, style: StylePreset) -> EditPlan: ...

    def lint(self, plan: EditPlan, ctx: ProjectContext) -> list[Finding]: ...


@runtime_checkable
class Renderer(Protocol):
    """A5. Compose the final MP4 from plan + inputs. Never alters base timing or audio map."""

    def render(
        self,
        plan: EditPlan,
        ctx: ProjectContext,
        inputs: RenderInputs,
        out: Path,
        enc: EncodeSettings,
    ) -> Path: ...


@runtime_checkable
class QualityControl(Protocol):
    """A5. Writes <version>/qc/qc.json + qc.md and returns the report."""

    def run(self, ctx: ProjectContext, version: str) -> QCReport: ...


__all__ = [
    "AudioMixer",
    "CaptionBuilder",
    "GraphicsRenderer",
    "PlanTools",
    "QualityControl",
    "Renderer",
    "ShotLibrary",
]
