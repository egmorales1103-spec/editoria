"""Render one frame per style with ffmpeg/libass over the fixture (path with spaces + ñ)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from editoria.captions import AssCaptionBuilder
from editoria.schemas import Canvas, EditorialTitle, Emphasis, Transcript, read_model
from editoria.util import ffmpeg, resources

T_FRAME = 1.9  # "automatizar" is spoken (1.82-2.16): caption + karaoke highlight on screen


def _frame(video: Path, out_dir: Path, name: str, vf: str | None) -> np.ndarray:
    args: list[str | Path] = ["-i", video, "-ss", f"{T_FRAME}"]
    if vf:
        args += ["-vf", vf]
    args += ["-frames:v", "1", name]
    ffmpeg.run(args, cwd=out_dir)  # cwd + relative names: safe with spaces/accents on Windows
    return np.asarray(Image.open(out_dir / name).convert("RGB"), dtype=np.int16)


@pytest.mark.parametrize("style_id", ["A", "B", "C"])
def test_render_frame_has_caption_pixels(
    tmp_path: Path, fixtures_dir: Path, spaced_video: Path, style_id: str
) -> None:
    out = tmp_path / "carpeta con espacios" / f"subtítulos {style_id}"
    transcript = read_model(fixtures_dir / "transcript_fixture.json", Transcript)
    builder = AssCaptionBuilder(fonts_dir=resources.fonts_dir())
    arts = builder.build(
        transcript,
        resources.load_style(style_id),
        resources.load_brand("master-solution"),
        Canvas(),
        [],
        [Emphasis(word=4)],
        out,
        cuts=[4.0, 7.85],
        editorial_titles=[EditorialTitle(text="Tres claves", in_=1.0, out=3.0)],
        duration=12.0,
    )
    assert arts.ass.parent == out
    fonts = resources.fonts_dir()
    vf = f"subtitles=f={arts.ass.name}"
    if fonts.is_dir():
        vf += f":fontsdir={ffmpeg.escape_filter_path(fonts)}"
    plain = _frame(spaced_video, out, "sin.png", None)
    subbed = _frame(spaced_video, out, "con.png", vf)
    assert plain.shape == subbed.shape == (1920, 1080, 3)

    diff = np.abs(subbed - plain).sum(axis=2) > 60
    caption = next(e for e in arts.events if not e.editorial and e.start <= T_FRAME < e.end)
    assert caption.box is not None
    b = caption.box
    region = diff[max(b.y - 40, 0) : b.y2 + 40, max(b.x - 40, 0) : b.x2 + 40]
    assert region.sum() > 2000, f"sin píxeles de subtítulo en {b}"
    # the editorial title (boxed, upper zone) is also drawn
    title = next(e for e in arts.events if e.editorial)
    assert title.box is not None
    tb = title.box
    assert diff[tb.y : tb.y2, tb.x : tb.x2].sum() > 2000
    # nothing is drawn in the bottom platform-UI margin
    safe = Canvas().safe_box()
    assert diff[safe.y2 + 10 :, :].sum() == 0
