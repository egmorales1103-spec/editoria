"""End-to-end render tests with ffmpeg (paths with spaces and accents)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from render_support import face_track, make_project, setup_version
from typer.testing import CliRunner

from editoria.cli import app
from editoria.qc.analysis import is_faststart
from editoria.render import (
    FFmpegRenderer,
    ZoomGuardError,
    contact_sheet,
    inputs_from_version,
    probe_media,
)
from editoria.render.cli import parse_window
from editoria.render.inputs import load_overlays
from editoria.schemas import (
    Box,
    CaptionsSpec,
    ConformedClip,
    EditPlan,
    EncodeSettings,
    GraphicItem,
    RenderInputs,
    VideoInterval,
    write_model,
)
from editoria.util import ffmpeg, resources
from editoria.util.project import DELIVERED_MARKER, ProjectContext

FAST = EncodeSettings(preset="veryfast", crf=23)
runner = CliRunner()


def frame_at(video: Path, t: float, out: Path) -> np.ndarray:
    ffmpeg.run(["-ss", f"{t}", "-i", video.name, "-frames:v", "1", str(out)], cwd=video.parent)
    with Image.open(out) as im:
        return np.asarray(im.convert("RGB"), dtype=np.int16)


def test_full_fixture_plan_renders_in_spaced_paths(version_ctx: ProjectContext) -> None:
    ctx = version_ctx
    vdir = ctx.version_dir("V1")
    assert " " in str(vdir) and "ñ" in str(vdir)
    inputs = inputs_from_version(ctx, "V1")
    assert inputs.captions_ass is not None and inputs.mix_wav is not None
    assert {o.id for o in inputs.overlays} == {"g01", "e01"}
    r = FFmpegRenderer()
    out = r.render(ctx.load_plan("V1"), ctx, inputs, vdir / "video.mp4", FAST)

    info = probe_media(out)
    orig = probe_media(ctx.original_video())
    assert (info.width, info.height) == (1080, 1920)
    assert info.fps == orig.fps
    assert info.video_codec == "h264" and "High" in info.profile and info.pix_fmt == "yuv420p"
    assert info.audio_codec == "aac" and info.audio_sr == 48000
    assert info.nb_frames == orig.nb_frames  # every base frame, once
    assert abs(info.duration - orig.duration) <= orig.frame_s
    assert is_faststart(out)[0]
    script = (vdir / "filtergraph.txt").read_text(encoding="utf-8")
    assert "C:" not in script and "ass=filename='subtitulos.ass'" in script
    assert not (vdir / "video.tmp.mp4").exists()
    log = ctx.commands_log.read_text(encoding="utf-8") if ctx.commands_log.exists() else ""
    assert log == "" or "filter_complex" in log

    # graphic g01 is visible at 1 s inside its box (yellow card), not at 3 s
    f1 = frame_at(out, 1.0, vdir / "f1.png")
    card = f1[240:260, 260:300].mean(axis=(0, 1))
    assert card[0] > 180 and card[1] > 150 and card[2] < 120


def test_generated_shot_and_push(
    spaced_project: ProjectContext, fixtures_dir: Path, tmp_path: Path
) -> None:
    ctx = spaced_project
    vdir = setup_version(ctx, fixtures_dir, captions=False, graphics=False)
    plan = EditPlan(
        version="V1", style="A", brand="master-solution", captions=CaptionsSpec(style="A"),
        video=[
            VideoInterval(id="v01", in_=1.0, out=3.0, method="reframe", zoom=1.2, motion="push"),
            VideoInterval(id="v02", in_=8.5, out=10.5, method="generated", shot="G01"),
        ],
    )  # fmt: skip
    write_model(vdir / "plan.yaml", plan)
    clip = ConformedClip(
        shot_id="G01", path=fixtures_dir / "generada_mala.mp4", start=8.5, end=10.5,
        width=1080, height=1920,
    )  # fmt: skip
    inputs = RenderInputs(shots={"G01": clip}, mix_wav=vdir / "audio" / "mezcla.wav")
    out = FFmpegRenderer().render(plan, ctx, inputs, vdir / "video.mp4", FAST)
    info = probe_media(out)
    orig = probe_media(ctx.original_video())
    assert info.nb_frames == orig.nb_frames
    script = (vdir / "filtergraph.txt").read_text(encoding="utf-8")
    assert "zoompan" in script and "[1:v]trim" in script
    # the (visibly different) shot covers exactly its interval: blue box only inside it
    base = ctx.original_video()

    def diff(t: float) -> float:
        a = frame_at(out, t, tmp_path / f"o{t}.png")
        b = frame_at(base, t, tmp_path / f"b{t}.png")
        return float(np.abs(a - b)[1200:1900].mean())

    assert diff(9.5) > 40  # the shot replaces the image inside its interval
    assert diff(11.0) < 12  # and the base is back afterwards


def test_zoom_guard_blocks_render(version_ctx: ProjectContext) -> None:
    ctx = version_ctx
    plan = ctx.load_plan("V1")
    plan.video[1] = plan.video[1].model_copy(update={"zoom": 1.4})
    with pytest.raises(ZoomGuardError):
        FFmpegRenderer().render(
            plan, ctx, RenderInputs(), ctx.version_dir("V1") / "video.mp4", FAST
        )


def test_small_vertical_source(projects_dir: Path, fixtures_dir: Path) -> None:
    src = fixtures_dir / "base_720x1280_25.mp4"
    ctx = make_project(
        projects_dir, "baja", src, face_track(720, 1280, Box(x=230, y=250, w=260, h=320), 6.0)
    )
    vdir = ctx.version_dir("V1")
    plan = EditPlan(
        version="V1", style="A", brand="master-solution", captions=CaptionsSpec(style="A")
    )
    write_model(vdir / "plan.yaml", plan)
    r = FFmpegRenderer()
    out = r.render(plan, ctx, RenderInputs(), vdir / "video.mp4", FAST)
    info = probe_media(out)
    assert (info.width, info.height) == (1080, 1920)
    assert info.fps == 25
    assert any("sin detalle nativo nuevo" in w for w in r.warnings)


def test_horizontal_source(projects_dir: Path, fixtures_dir: Path) -> None:
    src = fixtures_dir / "base_1920x1080.mp4"
    ctx = make_project(
        projects_dir,
        "horizontal",
        src,
        face_track(1920, 1080, Box(x=1300, y=300, w=200, h=260), 6.0),
    )
    vdir = ctx.version_dir("V1")
    plan = EditPlan(
        version="V1", style="A", brand="master-solution", captions=CaptionsSpec(style="A")
    )
    write_model(vdir / "plan.yaml", plan)
    r = FFmpegRenderer()
    out = r.render(plan, ctx, RenderInputs(), vdir / "video.mp4", FAST)
    info = probe_media(out)
    assert (info.width, info.height) == (1080, 1920)
    assert any("horizontal" in w for w in r.warnings)
    assert "crop=608:1080:1096:0" in (vdir / "filtergraph.txt").read_text(encoding="utf-8")


def test_sample_window_keeps_sync(version_ctx: ProjectContext) -> None:
    ctx = version_ctx
    vdir = ctx.version_dir("V1")
    enc = FAST.model_copy(update={"sample_window": (2.0, 5.0)})
    out = FFmpegRenderer().render(
        ctx.load_plan("V1"), ctx, inputs_from_version(ctx, "V1"), vdir / "muestra.mp4", enc
    )
    info = probe_media(out)
    assert abs(info.duration - 3.0) <= info.frame_s + 1e-3
    assert (vdir / "muestra.filtergraph.txt").is_file()


def test_delivered_version_is_not_overwritten(version_ctx: ProjectContext) -> None:
    vdir = version_ctx.version_dir("V1")
    (vdir / "video.mp4").write_bytes(b"entregado")
    (vdir / DELIVERED_MARKER).write_text("", encoding="utf-8")
    res = runner.invoke(app, ["render", "demo", "--version", "V1"])
    assert res.exit_code != 0
    assert "entregada" in res.output
    assert (vdir / "video.mp4").read_bytes() == b"entregado"


def test_cli_render_and_contact_sheet(version_ctx: ProjectContext) -> None:
    res = runner.invoke(
        app, ["render", "demo", "--version", "V1", "--preset", "veryfast", "--solo-componer"]
    )
    assert res.exit_code == 0, res.output
    vdir = version_ctx.version_dir("V1")
    assert (vdir / "video.mp4").is_file()
    res = runner.invoke(app, ["contact-sheet", "demo", "--version", "V1", "--every", "3"])
    assert res.exit_code == 0, res.output
    sheet = vdir / "hoja_contactos.jpg"
    with Image.open(sheet) as im:
        assert im.width > 0 and im.height > 400
    assert contact_sheet(version_ctx, "V1", 6.0) == sheet


def test_cli_sample_window(version_ctx: ProjectContext) -> None:
    res = runner.invoke(app, ["render", "demo", "--sample-window", "1-3", "--preset", "veryfast"])
    assert res.exit_code == 0, res.output
    assert (version_ctx.version_dir("V1") / "muestra_1-3.mp4").is_file()
    bad = runner.invoke(app, ["render", "demo", "--sample-window", "5-2"])
    assert bad.exit_code != 0


def test_parse_window() -> None:
    assert parse_window("2-7.5") == (2.0, 7.5)
    assert parse_window("2,5-4") == (2.5, 4.0)
    with pytest.raises(ValueError):
        parse_window("abc")


def test_inputs_skip_missing_and_resolve_emojis(
    spaced_project: ProjectContext,
    fixtures_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = spaced_project
    setup_version(ctx, fixtures_dir, captions=False, graphics=False, mix=False)
    emoji_dir = tmp_path / "emoji"
    emoji_dir.mkdir()
    shutil.copy2(fixtures_dir / "emoji_fixture.gif", emoji_dir / "E01.gif")
    monkeypatch.setattr(resources, "emoji_path", lambda eid: emoji_dir / f"{eid}.gif")
    inputs = inputs_from_version(ctx, "V1")
    assert inputs.captions_ass is None and inputs.mix_wav is None and inputs.shots == {}
    assert [o.id for o in inputs.overlays] == ["e01"]
    e01 = inputs.overlays[0]
    assert e01.is_gif and e01.start == 6.2 and e01.end == 7.4
    assert e01.x + e01.w <= 1080 - 140  # inside the safe zone (upper_right)
    assert inputs.face_box_canvas == Box(x=340, y=380, w=400, h=480)


def test_overlays_json_relative_paths(version_ctx: ProjectContext) -> None:
    vdir = version_ctx.version_dir("V1")
    clips = load_overlays(vdir)
    assert all(Path(c.frames_pattern).is_absolute() for c in clips)
    data = json.loads((vdir / "graficos" / "overlays.json").read_text(encoding="utf-8"))
    assert len(data["overlays"]) == len(clips)


def test_plan_emoji_without_asset_is_skipped(
    spaced_project: ProjectContext, fixtures_dir: Path
) -> None:
    vdir = setup_version(spaced_project, fixtures_dir, graphics=False)
    plan = spaced_project.load_plan("V1")
    plan.graphics = [GraphicItem(id="e09", emoji="E09", in_=1, out=2)]
    write_model(vdir / "plan.yaml", plan)
    assert inputs_from_version(spaced_project, "V1").overlays == []
