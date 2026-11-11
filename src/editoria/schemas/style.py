"""Style presets (A/B/C) and brand profiles."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from editoria.schemas.base import Model


class CaptionStyle(Model):
    font: str = "Inter"
    weight: int = 700
    size: int = 64  # px at 1080x1920
    case: Literal["upper", "lower", "sentence", "as_is"] = "as_is"
    words_per_event: int = Field(default=4, ge=1)
    max_chars_line: int = Field(default=24, ge=4)
    max_lines: int = Field(default=2, ge=1, le=3)
    max_cps: float = Field(default=17.0, gt=0)  # characters per second
    highlight: str = "accent"  # brand colour token (primary|accent|text|bg) or #RRGGBB
    outline: float = 3.0
    shadow: float = 1.0
    animation: Literal["pop", "fade", "none"] = "pop"
    position_y: float = Field(default=0.68, ge=0, le=1)  # caption block centre, fraction of H


class GraphicsPolicy(Model):
    allowed_templates: list[str] = Field(default_factory=list)
    max_simultaneous: int = Field(default=1, ge=0)


class SfxPolicy(Model):
    max_per_10s: int = Field(default=2, ge=0)
    min_spacing_s: float = Field(default=1.5, ge=0)
    allowed_cues: list[str] = Field(default_factory=list)


class ReframePolicy(Model):
    cadence_s: float = Field(default=6.0, gt=0)
    max_zoom: float = Field(default=1.15, ge=1.0)


class StylePreset(Model):
    id: Literal["A", "B", "C"]
    name: str
    description: str = ""
    references: list[str] = Field(default_factory=list)  # R01..R09 / W01..W25
    captions: CaptionStyle = Field(default_factory=CaptionStyle)
    editorial_titles: CaptionStyle | None = None  # must differ from captions (P13)
    graphics: GraphicsPolicy = Field(default_factory=GraphicsPolicy)
    sfx: SfxPolicy = Field(default_factory=SfxPolicy)
    reframe: ReframePolicy = Field(default_factory=ReframePolicy)


class BrandColors(Model):
    primary: str = "#111111"
    accent: str = "#FFD400"
    text: str = "#FFFFFF"
    bg: str = "#000000"

    def resolve(self, token: str) -> str:
        """Return a #RRGGBB colour from a token (primary|accent|text|bg) or a literal hex."""
        if token.startswith("#"):
            return token
        return str(getattr(self, token))


class BrandFonts(Model):
    heading: str = "Inter"
    body: str = "Inter"


class BrandProfile(Model):
    name: str
    colors: BrandColors = Field(default_factory=BrandColors)
    fonts: BrandFonts = Field(default_factory=BrandFonts)
    logo: str | None = None
    provisional: bool = True
    glossary: list[str] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(default_factory=list)
    voice_notes: str = ""
