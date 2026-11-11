"""Reframe geometry shared by the renderer and QC (built on util.geometry.base_transform)."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from editoria.schemas import Box, Canvas, EditPlan, FaceTrack, VideoInterval
from editoria.util.geometry import BaseTransform, base_transform

EPS = 1e-6


class ZoomGuardError(ValueError):
    """P07: a reframe would magnify native pixels beyond the allowed factor."""


@dataclass(frozen=True)
class Crop:
    """Rectangle in SOURCE pixels."""

    x: int
    y: int
    w: int
    h: int


def _even(v: float) -> int:
    return max(2, round(v / 2.0) * 2)


def face_box_source(face: FaceTrack | None, t0: float = 0.0, t1: float | None = None) -> Box | None:
    """Median face box (source px) of the samples inside [t0, t1]; union box as fallback."""
    if face is None:
        return None
    boxes = [s.box for s in face.samples if s.box is not None and t0 <= s.t <= (t1 if t1 else 1e12)]
    if boxes:
        return Box(
            x=round(median(b.x for b in boxes)),
            y=round(median(b.y for b in boxes)),
            w=round(median(b.w for b in boxes)),
            h=round(median(b.h for b in boxes)),
        )
    if face.union_box is not None:
        return face.union_box
    all_boxes = [s.box for s in face.samples if s.box is not None]
    return all_boxes[0] if all_boxes else None


def scale_face(face: FaceTrack | None, src_w: int, src_h: int) -> FaceTrack | None:
    """Return ``face`` expressed in a (src_w x src_h) frame (FaceTrack may use another size)."""
    if face is None or (face.frame_w == src_w and face.frame_h == src_h) or not face.frame_w:
        return face
    sx, sy = src_w / face.frame_w, src_h / face.frame_h

    def conv(b: Box | None) -> Box | None:
        if b is None:
            return None
        return Box(x=round(b.x * sx), y=round(b.y * sy), w=round(b.w * sx), h=round(b.h * sy))

    return face.model_copy(
        update={
            "frame_w": src_w,
            "frame_h": src_h,
            "union_box": conv(face.union_box),
            "samples": [s.model_copy(update={"box": conv(s.box)}) for s in face.samples],
        }
    )


def base_for(src_w: int, src_h: int, canvas: Canvas, face: FaceTrack | None) -> BaseTransform:
    """The canvas fill used by the renderer (horizontal crops are centred on the face)."""
    return base_transform(src_w, src_h, canvas, face_box_source(face))


def native_scale(bt: BaseTransform, zoom: float) -> float:
    """Canvas pixels per native source pixel inside a reframe of ``zoom``."""
    return bt.scale * zoom


def zoom_violation(bt: BaseTransform, zoom: float | None, max_zoom: float) -> str | None:
    """P07 guard. A reframe (zoom > 1) may not magnify native pixels beyond ``max_zoom``.

    Returns a Spanish message when violated, ``None`` otherwise.
    """
    z = zoom or 1.0
    if z <= 1.0 + EPS:
        return None
    total = native_scale(bt, z)
    if total > max_zoom + 1e-3:
        return (
            f"zoom {z:.2f}× sobre una fuente escalada {bt.scale:.2f}× = {total:.2f}× sobre "
            f"píxeles nativos (máximo {max_zoom:.2f}×)"
        )
    return None


def anchor_source(
    iv: VideoInterval, bt: BaseTransform, face: FaceTrack | None
) -> tuple[float, float]:
    """Anchor point of a reframe in source pixels."""
    if iv.anchor == "point" and iv.point is not None:
        px, py = iv.point
        return bt.crop_x + px * bt.crop_w, bt.crop_y + py * bt.crop_h
    if iv.anchor in (None, "face"):
        fb = face_box_source(face, iv.in_, iv.out)
        if fb is not None:
            return fb.x + fb.w / 2, fb.y + fb.h / 2
    return bt.crop_x + bt.crop_w / 2, bt.crop_y + bt.crop_h / 2


def reframe_crop(bt: BaseTransform, zoom: float, anchor: tuple[float, float]) -> Crop:
    """Crop (source px) of a punch-in of ``zoom`` around ``anchor``, kept inside the base crop."""
    w = min(_even(bt.crop_w / zoom), bt.crop_w - bt.crop_w % 2)
    h = min(_even(bt.crop_h / zoom), bt.crop_h - bt.crop_h % 2)
    ax, ay = anchor
    x = min(max(ax - w / 2, bt.crop_x), bt.crop_x + bt.crop_w - w)
    y = min(max(ay - h / 2, bt.crop_y), bt.crop_y + bt.crop_h - h)
    return Crop(x=int(x) // 2 * 2, y=int(y) // 2 * 2, w=w, h=h)


def crop_to_canvas(box: Box, crop: Crop, canvas: Canvas) -> Box:
    s = canvas.width / crop.w
    return Box(
        x=round((box.x - crop.x) * s),
        y=round((box.y - crop.y) * s),
        w=round(box.w * s),
        h=round(box.h * s),
    )


def face_boxes_on_canvas(
    plan: EditPlan,
    face: FaceTrack | None,
    src_w: int,
    src_h: int,
    t0: float,
    t1: float,
) -> list[Box]:
    """Canvas-space face boxes visible during [t0, t1], including reframe magnification."""
    face = scale_face(face, src_w, src_h)
    fb = face_box_source(face, t0, t1)
    if fb is None:
        return []
    bt = base_for(src_w, src_h, plan.canvas, face)
    boxes = [bt.to_canvas(fb)]
    for iv in plan.video:
        if iv.method != "reframe" or iv.out <= t0 or iv.in_ >= t1:
            continue
        z = iv.zoom or 1.0
        crop = reframe_crop(bt, z, anchor_source(iv, bt, face))
        boxes.append(crop_to_canvas(fb, crop, plan.canvas))
    return boxes
