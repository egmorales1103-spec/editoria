"""Shared geometry: how the base video maps onto the 9:16 canvas.

Every module that converts source-pixel boxes (FaceTrack) into canvas boxes (captions,
QC, graphics placement) MUST use :func:`base_transform` so they agree with the renderer.
"""

from __future__ import annotations

from dataclasses import dataclass

from editoria.schemas import Box, Canvas, Zone


@dataclass(frozen=True)
class BaseTransform:
    """Crop (in source px) then uniform scale to fill the canvas."""

    crop_x: int
    crop_y: int
    crop_w: int
    crop_h: int
    scale: float  # canvas px per source px
    upscaled: bool  # True when scale > 1 (no new native detail)
    cropped_horizontal: bool  # True when a landscape source was cropped to 9:16

    def to_canvas(self, box: Box) -> Box:
        return Box(
            x=round((box.x - self.crop_x) * self.scale),
            y=round((box.y - self.crop_y) * self.scale),
            w=round(box.w * self.scale),
            h=round(box.h * self.scale),
        )


def base_transform(
    src_w: int, src_h: int, canvas: Canvas, face: Box | None = None
) -> BaseTransform:
    """Fill the canvas: crop the source to the canvas aspect (centred on the face horizontally
    when available, otherwise centred), then scale."""
    target_ar = canvas.width / canvas.height
    src_ar = src_w / src_h
    if abs(src_ar - target_ar) < 1e-3:
        cx, cy, cw, ch = 0, 0, src_w, src_h
    elif src_ar > target_ar:  # too wide -> crop width
        cw = round(src_h * target_ar)
        ch = src_h
        centre = face.x + face.w / 2 if face else src_w / 2
        cx = int(min(max(centre - cw / 2, 0), src_w - cw))
        cy = 0
    else:  # too tall -> crop height
        cw = src_w
        ch = round(src_w / target_ar)
        cx = 0
        cy = (src_h - ch) // 2
    scale = canvas.width / cw
    return BaseTransform(
        crop_x=cx,
        crop_y=cy,
        crop_w=cw,
        crop_h=ch,
        scale=scale,
        upscaled=scale > 1.0 + 1e-6,
        cropped_horizontal=src_ar > target_ar + 1e-3,
    )


def zone_box(zone: Zone, canvas: Canvas, w: int, h: int) -> Box:
    """Top-left placement of a w x h overlay inside ``zone``, respecting the safe area."""
    safe = canvas.safe_box()
    xs = {
        "left": safe.x,
        "center": safe.x + (safe.w - w) // 2,
        "right": safe.x2 - w,
    }
    ys = {
        "upper": safe.y,
        "middle": safe.y + (safe.h - h) // 2,
        "lower": safe.y2 - h,
    }
    table: dict[str, tuple[str, str]] = {
        "upper": ("center", "upper"),
        "middle": ("center", "middle"),
        "center": ("center", "middle"),
        "lower": ("center", "lower"),
        "upper_left": ("left", "upper"),
        "upper_right": ("right", "upper"),
        "lower_left": ("left", "lower"),
        "lower_right": ("right", "lower"),
    }
    if zone == "full":
        return Box(x=0, y=0, w=canvas.width, h=canvas.height)
    hx, vy = table[zone]
    return Box(x=xs[hx], y=ys[vy], w=w, h=h)
