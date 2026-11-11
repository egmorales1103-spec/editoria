"""Base model and shared primitive types for all EditorIA schemas."""

from __future__ import annotations

from fractions import Fraction
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Seconds = float


class Model(BaseModel):
    """Strict base: unknown keys are errors, aliases and field names both accepted."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Box(Model):
    """Axis-aligned rectangle in pixels. The coordinate space is stated by the owner field."""

    x: int
    y: int
    w: int = Field(ge=0)
    h: int = Field(ge=0)

    @property
    def x2(self) -> int:
        return self.x + self.w

    @property
    def y2(self) -> int:
        return self.y + self.h

    def intersects(self, other: Box) -> bool:
        return not (
            self.x2 <= other.x or other.x2 <= self.x or self.y2 <= other.y or other.y2 <= self.y
        )

    def dilate(self, px: int) -> Box:
        return Box(x=self.x - px, y=self.y - px, w=self.w + 2 * px, h=self.h + 2 * px)


class Interval(Model):
    start: Seconds = Field(ge=0)
    end: Seconds = Field(ge=0)

    @property
    def duration(self) -> float:
        return self.end - self.start


def parse_fps(value: str | float | int | Fraction) -> Fraction:
    """Parse '30000/1001', '30', 29.97 or a Fraction into a Fraction."""
    if isinstance(value, Fraction):
        return value
    if isinstance(value, int | float):
        return Fraction(value).limit_denominator(1001)
    text = str(value).strip()
    if "/" in text:
        num, den = text.split("/", 1)
        return Fraction(int(num), int(den))
    return Fraction(text).limit_denominator(1001)


def fps_str(value: Fraction) -> str:
    return f"{value.numerator}/{value.denominator}"


class SafeZone(Model):
    """Margins (px, at canvas resolution) kept free of captions: platform UI lives there."""

    top: int = 220
    bottom: int = 420
    left: int = 60
    right: int = 140


class Canvas(Model):
    width: int = 1080
    height: int = 1920
    fps: str = "source"
    safe: SafeZone = Field(default_factory=SafeZone)

    @field_validator("fps", mode="before")
    @classmethod
    def _fps(cls, v: object) -> str:
        if v is None or v == "source":
            return "source"
        return fps_str(parse_fps(v))  # type: ignore[arg-type]

    def resolve_fps(self, source_fps: str | Fraction) -> Fraction:
        return parse_fps(source_fps) if self.fps == "source" else parse_fps(self.fps)

    def safe_box(self) -> Box:
        s = self.safe
        return Box(
            x=s.left,
            y=s.top,
            w=self.width - s.left - s.right,
            h=self.height - s.top - s.bottom,
        )


Zone = Literal[
    "upper",
    "middle",
    "lower",
    "center",
    "upper_left",
    "upper_right",
    "lower_left",
    "lower_right",
    "full",
]

Method = Literal["original", "reframe", "generated"]
Verdict = Literal["pendiente", "aceptado", "reintentar", "descartado"]
Severity = Literal["ERROR", "WARN"]
QCStatus = Literal["PASS", "WARN", "FAIL", "HUMAN"]
