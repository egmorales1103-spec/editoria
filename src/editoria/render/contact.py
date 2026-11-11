"""Contact sheet: frames every N seconds plus the edges of every insert and graphic."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from editoria.render.media import probe_media
from editoria.schemas import EditPlan
from editoria.util import ffmpeg
from editoria.util.files import fmt_ts
from editoria.util.project import VIDEO_FILE, ProjectContext

CONTACT_SHEET_FILE = "hoja_contactos.jpg"
THUMB_W = 216
THUMB_H = 384
LABEL_H = 44
COLUMNS = 6


@dataclass(frozen=True)
class Mark:
    t: float
    label: str


def sheet_marks(plan: EditPlan | None, duration: float, every: float) -> list[Mark]:
    """Regular marks every ``every`` s plus in/out edges of inserts and graphics (sorted)."""
    if every <= 0:
        raise ValueError("--every debe ser mayor que 0.")
    marks: dict[float, str] = {}
    t = 0.0
    while t < duration - 1e-6:
        marks[round(t, 3)] = ""
        t += every
    if plan is not None:
        edges: list[tuple[float, float, str]] = [
            (iv.in_, iv.out, f"{iv.id} {iv.method}") for iv in plan.video if iv.method != "original"
        ]
        edges += [(g.in_, g.out, g.id) for g in plan.graphics]
        last = max(duration - 0.05, 0.0)
        for a, b, name in edges:
            for tt, tag in ((a, "entra"), (b - 0.05, "sale")):
                key = round(min(max(tt, 0.0), last), 3)
                marks[key] = f"{marks.get(key, '')} {name} {tag}".strip()
    return [Mark(t, lbl) for t, lbl in sorted(marks.items())]


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default()


def build_sheet(video: Path, marks: list[Mark], out: Path, fps: float) -> Path:
    """Extract one thumbnail per mark (single ffmpeg pass) and tile them with timestamps."""
    frames = sorted({max(0, round(m.t * fps)) for m in marks})
    by_frame: dict[int, list[Mark]] = {}
    for m in marks:
        by_frame.setdefault(max(0, round(m.t * fps)), []).append(m)
    with tempfile.TemporaryDirectory(prefix="editoria_cs_") as tmp:
        tmpdir = Path(tmp)
        expr = "+".join(f"eq(n\\,{n})" for n in frames)
        ffmpeg.run(
            [
                "-i", video.name,
                "-vf", f"select='{expr}',scale={THUMB_W}:{THUMB_H}",
                "-fps_mode", "passthrough", str(tmpdir / "%05d.png"),
            ],
            cwd=video.parent,
        )  # fmt: skip
        thumbs = sorted(tmpdir.glob("*.png"))
        rows = max(1, -(-len(thumbs) // COLUMNS))
        cols = min(COLUMNS, max(1, len(thumbs)))
        sheet = Image.new("RGB", (cols * THUMB_W, rows * (THUMB_H + LABEL_H)), (24, 24, 24))
        draw = ImageDraw.Draw(sheet)
        font_t, font_l = _font(18), _font(13)
        for i, (thumb, n) in enumerate(zip(thumbs, frames, strict=False)):
            x = (i % COLUMNS) * THUMB_W
            y = (i // COLUMNS) * (THUMB_H + LABEL_H)
            with Image.open(thumb) as im:
                sheet.paste(im.convert("RGB"), (x, y))
            group = by_frame.get(n, [])
            stamp = fmt_ts(group[0].t if group else n / fps)
            label = " · ".join(m.label for m in group if m.label)
            draw.text((x + 6, y + THUMB_H + 3), stamp, fill=(255, 255, 255), font=font_t)
            if label:
                draw.text((x + 6, y + THUMB_H + 24), label[:34], fill=(255, 212, 0), font=font_l)
        out.parent.mkdir(parents=True, exist_ok=True)
        sheet.save(out, quality=88)
    return out


def contact_sheet(ctx: ProjectContext, version: str, every: float) -> Path:
    """Write ``<version>/hoja_contactos.jpg`` from the rendered ``video.mp4``."""
    vdir = ctx.version_dir(version)
    video = vdir / VIDEO_FILE
    if not video.is_file():
        raise FileNotFoundError(f"No existe {VIDEO_FILE} en {version}. Ejecutá 'editoria render'.")
    info = probe_media(video)
    plan_path = vdir / "plan.yaml"
    plan = ctx.load_plan(version) if plan_path.is_file() else None
    marks = sheet_marks(plan, info.duration, every)
    return build_sheet(video, marks, vdir / CONTACT_SHEET_FILE, float(info.fps))
