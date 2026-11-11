"""EditPlan: the declarative `plan.yaml` (schema editoria/plan@1)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from editoria.schemas.base import Canvas, Method, Model, Seconds, Zone

PLAN_SCHEMA_ID: Literal["editoria/plan@1"] = "editoria/plan@1"


class VideoInterval(Model):
    """Interval on the VIDEO_BASE timeline. `in`/`out` are seconds of the base video."""

    id: str
    in_: Seconds = Field(alias="in", ge=0)
    out: Seconds = Field(ge=0)
    method: Method
    zoom: float | None = Field(default=None, ge=1.0)  # reframe only
    anchor: Literal["face", "center", "point"] | None = None
    point: tuple[float, float] | None = None  # normalised (0..1) when anchor == "point"
    motion: Literal["cut", "push"] | None = None  # punch-in or slow push (zoompan)
    shot: str | None = None  # generated only: id in registro_generaciones.csv (e.g. G01)

    @model_validator(mode="after")
    def _check(self) -> VideoInterval:
        if self.out <= self.in_:
            raise ValueError(f"{self.id}: 'out' debe ser mayor que 'in'")
        if self.method == "generated" and not self.shot:
            raise ValueError(f"{self.id}: method 'generated' exige 'shot'")
        if self.anchor == "point" and self.point is None:
            raise ValueError(f"{self.id}: anchor 'point' exige 'point'")
        return self


class Emphasis(Model):
    word: int = Field(ge=0)  # index into Transcript.words
    color: str | None = None  # brand token or #RRGGBB; None = style highlight


class EditorialTitle(Model):
    """Text that is NOT what is being said. Must use a distinct style (P13)."""

    text: str
    in_: Seconds = Field(alias="in", ge=0)
    out: Seconds
    zone: Zone = "upper"


class CaptionsSpec(Model):
    style: Literal["A", "B", "C"]
    emphasis: list[Emphasis] = Field(default_factory=list)
    editorial_titles: list[EditorialTitle] = Field(default_factory=list)
    enabled: bool = True


class GraphicItem(Model):
    """A template-based motion graphic OR an animated emoji overlay (exactly one)."""

    id: str
    template: str | None = None
    emoji: str | None = None  # E01..E06 (assets/emoji/<id>.gif)
    in_: Seconds = Field(alias="in", ge=0)
    out: Seconds
    zone: Zone = "upper"
    params: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check(self) -> GraphicItem:
        if (self.template is None) == (self.emoji is None):
            raise ValueError(f"{self.id}: indicá exactamente uno de 'template' o 'emoji'")
        if self.out <= self.in_:
            raise ValueError(f"{self.id}: 'out' debe ser mayor que 'in'")
        return self

    @property
    def is_emoji(self) -> bool:
        return self.emoji is not None


class SfxCue(Model):
    cue: str  # pop | click | whoosh | ding | teclado | impacto_suave
    at: Seconds = Field(ge=0)
    gain_db: float = -14.0
    ref: str | None = None  # id of the graphic / interval it accents
    variant: int | None = None  # 1-based variant; None = first


class MusicSpec(Model):
    path: str
    asset_id: str  # must exist in a manifest with a licence (P17)
    gain_db: float = -20.0


class MixSpec(Model):
    target_lufs: float = -14.0
    true_peak_db: float = -1.0
    duck_db: float = -10.0


class EditPlan(Model):
    schema_: Literal["editoria/plan@1"] = Field(default=PLAN_SCHEMA_ID, alias="schema")
    version: str = Field(pattern=r"^V\d+$")
    style: Literal["A", "B", "C"]
    brand: str
    canvas: Canvas = Field(default_factory=Canvas)
    video: list[VideoInterval] = Field(default_factory=list)
    captions: CaptionsSpec
    graphics: list[GraphicItem] = Field(default_factory=list)
    sfx: list[SfxCue] = Field(default_factory=list)
    music: MusicSpec | None = None
    mix: MixSpec = Field(default_factory=MixSpec)
    notes: str = ""
    window: tuple[Seconds, Seconds] | None = None  # proposals: sample window on the base
