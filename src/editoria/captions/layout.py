"""Caption placement on the canvas: safe zone, stable position and face avoidance."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from editoria.schemas import Box, Canvas, CaptionStyle, FaceTrack, VideoInterval
from editoria.util.geometry import base_transform

LINE_HEIGHT = 1.18  # line pitch as a fraction of the font size
AVOID_MARGIN = 24  # px kept between captions and an avoided box


def char_width(style: CaptionStyle) -> float:
    """Average glyph advance (px) for size estimates. Bold/upper text is wider."""
    factor = 0.56 if style.case != "upper" else 0.66
    if style.weight >= 800:
        factor += 0.04
    return style.size * factor


def block_size(lines: Sequence[str], style: CaptionStyle) -> tuple[int, int]:
    widest = max((len(line) for line in lines), default=0)
    pad = int(2 * style.outline + style.shadow) + 4
    w = int(widest * char_width(style)) + 2 * pad
    h = int(max(len(lines), 1) * style.size * LINE_HEIGHT) + 2 * pad
    return w, h


def box_at(cx: int, cy: int, w: int, h: int) -> Box:
    return Box(x=cx - w // 2, y=cy - h // 2, w=w, h=h)


@dataclass(frozen=True)
class Placement:
    cx: int
    cy: int
    relocated: bool = False
    warning: str | None = None


def _clamp_cy(cy: float, h: int, safe: Box) -> int:
    lo = safe.y + h / 2
    hi = safe.y2 - h / 2
    if lo > hi:
        return int(safe.y + safe.h / 2)
    return int(min(max(cy, lo), hi))


def stable_placement(style: CaptionStyle, canvas: Canvas, avoid: Sequence[Box]) -> Placement:
    """One position for every event: the style's preferred height clamped to the safe zone,
    moved to the nearest free height when the full-size block would hit an avoided box."""
    safe = canvas.safe_box()
    cx = safe.x + safe.w // 2
    w = safe.w  # worst case: full-width block
    h = int(style.max_lines * style.size * LINE_HEIGHT) + int(2 * style.outline) + 8
    preferred = _clamp_cy(style.position_y * canvas.height, h, safe)
    obstacles = [b.dilate(AVOID_MARGIN) for b in avoid if b.w > 0 and b.h > 0]

    def free(cy: int) -> bool:
        blk = box_at(cx, cy, w, h)
        return not any(blk.intersects(o) for o in obstacles)

    if free(preferred):
        return Placement(cx, preferred)
    candidates: set[int] = set()
    for o in obstacles:
        candidates.add(_clamp_cy(o.y2 + h / 2 + 1, h, safe))
        candidates.add(_clamp_cy(o.y - h / 2 - 1, h, safe))
    candidates.add(_clamp_cy(safe.y2 - h / 2, h, safe))
    candidates.add(_clamp_cy(safe.y + h / 2, h, safe))
    for cy in sorted(candidates, key=lambda c: abs(c - preferred)):
        if free(cy):
            return Placement(cx, cy, relocated=True)
    # Nothing is free: keep the lowest safe position (least likely to cover the face).
    return Placement(
        cx,
        _clamp_cy(safe.y2 - h / 2, h, safe),
        relocated=True,
        warning="No hay una posición de subtítulos libre del rostro dentro de la zona segura.",
    )


def union(boxes: Iterable[Box]) -> Box | None:
    bs = [b for b in boxes if b.w > 0 and b.h > 0]
    if not bs:
        return None
    x, y = min(b.x for b in bs), min(b.y for b in bs)
    x2, y2 = max(b.x2 for b in bs), max(b.y2 for b in bs)
    return Box(x=x, y=y, w=x2 - x, h=y2 - y)


def _zoomed(box: Box, zoom: float, centre: tuple[float, float]) -> Box:
    cx, cy = centre
    x = cx + (box.x - cx) * zoom
    y = cy + (box.y - cy) * zoom
    return Box(x=round(x), y=round(y), w=round(box.w * zoom), h=round(box.h * zoom))


def face_avoid_boxes(
    face: FaceTrack | None, canvas: Canvas, video: Sequence[VideoInterval] = ()
) -> list[Box]:
    """Face boxes in canvas space (via base_transform), including reframe zooms."""
    if face is None:
        return []
    src = face.union_box or union(s.box for s in face.samples if s.box is not None)
    if src is None:
        return []
    tr = base_transform(face.frame_w, face.frame_h, canvas, src)
    base = tr.to_canvas(src)
    out = [base]
    for iv in video:
        if iv.method != "reframe" or not iv.zoom or iv.zoom <= 1.0:
            continue
        if iv.anchor == "point" and iv.point is not None:
            centre = (iv.point[0] * canvas.width, iv.point[1] * canvas.height)
        elif iv.anchor == "center":
            centre = (canvas.width / 2, canvas.height / 2)
        else:
            centre = (base.x + base.w / 2, base.y + base.h / 2)
        out.append(_zoomed(base, iv.zoom, centre))
    return out
