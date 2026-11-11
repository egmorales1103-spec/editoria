"""Delivered versions are immutable, fonts reach libass, sample windows keep sync,
and the same plan always produces the same filtergraph."""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from typer.testing import CliRunner

from editoria.cli import app
from editoria.qc.analysis import correlate_voice
from editoria.render import FFmpegRenderer, RenderError, contact_sheet, inputs_from_version
from editoria.render.filtergraph import build_render_graph
from editoria.render.media import probe_media
from editoria.schemas import EncodeSettings
from editoria.util import ffmpeg, resources
from editoria.util.project import DELIVERED_MARKER, ProjectContext

FAST = EncodeSettings(preset="veryfast", crf=23)
runner = CliRunner()


def deliver_marker(ctx: ProjectContext, version: str = "V1") -> Path:
    vdir = ctx.version_dir(version)
    (vdir / DELIVERED_MARKER).write_text(version, encoding="utf-8")
    return vdir


# ---- immutability of delivered versions ---------------------------------------------------
@pytest.mark.parametrize(
    "extra",
    [[], ["--sample-window", "1-3"], ["--solo-componer"]],
    ids=["completo", "muestra", "solo-componer"],
)
def test_cli_render_refuses_delivered_version_for_any_output(
    version_ctx: ProjectContext, extra: list[str]
) -> None:
    vdir = deliver_marker(version_ctx)
    before = sorted(p.name for p in vdir.iterdir())
    res = runner.invoke(app, ["render", "demo", "--version", "V1", "--preset", "veryfast", *extra])
    assert res.exit_code != 0
    assert "entregada" in res.output and "inmutable" in res.output
    assert sorted(p.name for p in vdir.iterdir()) == before  # nothing written


def test_renderer_refuses_outputs_inside_a_delivered_version(version_ctx: ProjectContext) -> None:
    ctx = version_ctx
    vdir = deliver_marker(ctx)
    for out in (vdir / "video.mp4", vdir / "muestras" / "m.mp4"):
        with pytest.raises(RenderError, match="entregada"):
            FFmpegRenderer().render(ctx.load_plan("V1"), ctx, inputs_from_version(ctx, "V1"), out,
                                    FAST)  # fmt: skip
        assert not out.exists()
    with pytest.raises(RenderError, match="00_original"):
        FFmpegRenderer().render(
            ctx.load_plan("V1"), ctx, inputs_from_version(ctx, "V1"),
            ctx.original_dir / "otro.mp4", FAST,
        )  # fmt: skip


def test_contact_sheet_refuses_delivered_version(version_ctx: ProjectContext) -> None:
    ctx = version_ctx
    vdir = ctx.version_dir("V1")
    FFmpegRenderer().render(
        ctx.load_plan("V1"), ctx, inputs_from_version(ctx, "V1"), vdir / "video.mp4",
        FAST.model_copy(update={"preset": "ultrafast", "crf": 30}),
    )  # fmt: skip
    deliver_marker(ctx)
    res = runner.invoke(app, ["contact-sheet", "demo", "--version", "V1"])
    assert res.exit_code != 0 and "entregada" in res.output
    with pytest.raises(PermissionError, match="entregada"):
        contact_sheet(ctx, "V1", 2.0)
    assert not (vdir / "hoja_contactos.jpg").exists()


# ---- fonts: libass gets the family folder -------------------------------------------------
def _any_ttf() -> Path | None:
    cands = [resources.fonts_dir() / "Inter"]
    cands += [Path(r"C:\Windows\Fonts"), Path("/usr/share/fonts"), Path("/System/Library/Fonts")]
    for d in cands:
        if d.is_dir():
            found = sorted(p for p in d.rglob("*.ttf"))
            if found:
                return found[0]
    return None


def test_inputs_pass_the_font_family_folder_and_libass_loads_it(
    version_ctx: ProjectContext, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ttf = _any_ttf()
    if ttf is None:
        pytest.skip("no hay ninguna fuente TTF disponible")
    fonts = tmp_path / "fuentes"
    (fonts / "Inter").mkdir(parents=True)
    shutil.copy2(ttf, fonts / "Inter" / "Inter-Regular.ttf")
    monkeypatch.setattr(resources, "fonts_dir", lambda: fonts)

    ctx = version_ctx
    inputs = inputs_from_version(ctx, "V1")
    assert inputs.fonts_dir == fonts / "Inter"  # not the root: libass does not recurse

    vdir = ctx.version_dir("V1")
    base = ctx.original_video()
    graph = build_render_graph(
        ctx.load_plan("V1"), inputs, probe_media(base), base, vdir, FAST, face=ctx.load_face()
    )
    ass_opts = next(ln for ln in graph.script.splitlines() if "ass=filename=" in ln)
    opts = ass_opts[ass_opts.index("ass=") : ass_opts.rindex("[")]
    assert "fontsdir=" in opts
    proc = ffmpeg.run(
        ["-v", "debug", "-f", "lavfi", "-i", "color=c=black:s=1080x1920:d=0.5", "-vf", opts,
         "-frames:v", "1", "-f", "null", "-"],
        cwd=vdir,
    )  # fmt: skip
    assert "Inter-Regular.ttf" in proc.stderr and "fopen failed" not in proc.stderr


# ---- determinism ---------------------------------------------------------------------------
def test_same_plan_writes_the_same_filtergraph(version_ctx: ProjectContext) -> None:
    ctx = version_ctx
    vdir = ctx.version_dir("V1")
    enc = FAST.model_copy(update={"sample_window": (1.0, 2.0), "preset": "ultrafast"})
    scripts = []
    for _ in range(2):
        FFmpegRenderer().render(
            ctx.load_plan("V1"), ctx, inputs_from_version(ctx, "V1"), vdir / "m.mp4", enc
        )
        scripts.append((vdir / "m.filtergraph.txt").read_bytes())
    assert scripts[0] == scripts[1]


# ---- sample windows seek in the input without breaking sync ---------------------------------
def _frame(video: Path, t: float, out: Path) -> np.ndarray:
    ffmpeg.run(["-ss", f"{t}", "-i", video.name, "-frames:v", "1", str(out)], cwd=video.parent)
    with Image.open(out) as im:
        return np.asarray(im.convert("RGB"), dtype=np.int16)


def test_sample_window_matches_the_full_render(version_ctx: ProjectContext, tmp_path: Path) -> None:
    """Window 1–7 s crosses a graphic, a reframe, captions and an emoji: every layer and the
    audio must line up with the same instants of the full render."""
    ctx = version_ctx
    vdir = ctx.version_dir("V1")
    a, b = 1.0, 7.0
    full = FFmpegRenderer().render(
        ctx.load_plan("V1"), ctx, inputs_from_version(ctx, "V1"), vdir / "video.mp4", FAST
    )
    renderer = FFmpegRenderer()
    sample = renderer.render(
        ctx.load_plan("V1"), ctx, inputs_from_version(ctx, "V1"), vdir / "muestra.mp4",
        FAST.model_copy(update={"sample_window": (a, b)}),
    )  # fmt: skip
    assert renderer.last_graph is not None and "-ss" in renderer.last_graph.input_args
    info = probe_media(sample)
    assert abs(info.duration - (b - a)) <= info.frame_s + 1e-3
    for t in (0.5, 2.0, 2.9, 5.6):  # g01 + caption, reframe, reframe end, emoji + caption
        s = _frame(sample, t, tmp_path / f"s{t}.png")
        f = _frame(full, a + t, tmp_path / f"f{t}.png")
        assert float(np.abs(s - f).mean()) < 4.0, t
    # audio: same as the window of the full render, no offset
    ref = tmp_path / "ref.wav"
    ffmpeg.run(["-ss", f"{a}", "-t", f"{b - a}", "-i", full.name, "-vn", str(ref)], cwd=vdir)
    vc = correlate_voice(ref, sample)
    assert abs(vc.offset_ms) <= 2.0 and vc.similarity > 0.9
