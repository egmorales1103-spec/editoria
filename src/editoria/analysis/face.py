"""Face zone: Haar cascade (OpenCV, optional extra) sampled every 0.5 s, with a fixed fallback.

All boxes are in SOURCE pixel coordinates (after rotation), as :class:`FaceTrack` requires.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from editoria.schemas import Box, FaceSample, FaceTrack
from editoria.util import ffmpeg

SAMPLE_EVERY_S = 0.5
DETECT_WIDTH = 540  # frames are downscaled to this width before detection


def estimated_box(frame_w: int, frame_h: int) -> Box:
    """Upper-centre zone where a talking head usually sits in a 9:16 reel.

    Sized from the 9:16 crop width, so it is also sensible for landscape sources.
    """
    crop_w = min(frame_w, round(frame_h * 9 / 16))
    w = round(crop_w * 0.37)
    h = round(w * 1.2)
    return Box(x=(frame_w - w) // 2, y=round(frame_h * 0.2), w=w, h=h)


def union(boxes: list[Box]) -> Box | None:
    if not boxes:
        return None
    x1 = min(b.x for b in boxes)
    y1 = min(b.y for b in boxes)
    x2 = max(b.x2 for b in boxes)
    y2 = max(b.y2 for b in boxes)
    return Box(x=x1, y=y1, w=x2 - x1, h=y2 - y1)


def estimated_track(frame_w: int, frame_h: int, duration: float) -> FaceTrack:
    box = estimated_box(frame_w, frame_h)
    n = int(duration / SAMPLE_EVERY_S) + 1
    samples = [FaceSample(t=round(i * SAMPLE_EVERY_S, 2), box=box) for i in range(n)]
    return FaceTrack(
        frame_w=frame_w, frame_h=frame_h, samples=samples, union_box=box, estimated=True
    )


def opencv_available() -> bool:
    """True when OpenCV with Haar cascades is importable (OpenCV 5 dropped them)."""
    try:
        import cv2
    except ImportError:
        return False
    return hasattr(cv2, "CascadeClassifier") and hasattr(getattr(cv2, "data", None), "haarcascades")


def detect_faces(video: Path, frame_w: int, frame_h: int, duration: float) -> FaceTrack:
    """Sample the video every 0.5 s and detect the largest frontal face in each frame.

    Falls back to :func:`estimated_track` (``estimated=True``) when OpenCV is not installed
    or no face is found in any sample.
    """
    if not opencv_available():
        return estimated_track(frame_w, frame_h, duration)
    import cv2

    cv: Any = cv2  # OpenCV 5 stubs lack the cascade API that opencv_available() verified
    cascade = cv.CascadeClassifier(
        str(Path(cv.data.haarcascades) / "haarcascade_frontalface_default.xml")
    )
    if cascade.empty():  # pragma: no cover - broken OpenCV install
        return estimated_track(frame_w, frame_h, duration)

    samples: list[FaceSample] = []
    with tempfile.TemporaryDirectory(prefix="editoria-faces-") as tmp:
        tmp_dir = Path(tmp)
        ffmpeg.run(
            ["-i", str(video), "-an", "-vf", f"fps={1 / SAMPLE_EVERY_S:g},scale={DETECT_WIDTH}:-2",
             "-q:v", "3", "f_%05d.jpg"],
            cwd=tmp_dir,
        )  # fmt: skip
        for i, frame in enumerate(sorted(tmp_dir.glob("f_*.jpg"))):
            img = cv2.imdecode(_read_bytes(frame), cv2.IMREAD_GRAYSCALE)
            box: Box | None = None
            if img is not None:
                scale = frame_w / img.shape[1]
                min_side = max(24, img.shape[1] // 12)
                found = cascade.detectMultiScale(
                    img, scaleFactor=1.1, minNeighbors=5, minSize=(min_side, min_side)
                )
                if len(found):
                    x, y, w, h = max(found, key=lambda r: int(r[2]) * int(r[3]))
                    box = Box(
                        x=round(int(x) * scale),
                        y=round(int(y) * scale),
                        w=round(int(w) * scale),
                        h=round(int(h) * scale),
                    )
            samples.append(FaceSample(t=round(i * SAMPLE_EVERY_S, 2), box=box))

    boxes = [s.box for s in samples if s.box is not None]
    if not boxes:
        return estimated_track(frame_w, frame_h, duration)
    return FaceTrack(
        frame_w=frame_w, frame_h=frame_h, samples=samples, union_box=union(boxes), estimated=False
    )


def _read_bytes(path: Path):  # type: ignore[no-untyped-def]
    import numpy as np

    return np.frombuffer(path.read_bytes(), dtype=np.uint8)
