"""Pure filtergraph / geometry tests (no encoding)."""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

import pytest

from editoria.render.contact import sheet_marks
from editoria.render.filtergraph import RenderError, RenderGraph, build_render_graph
from editoria.render.geometry import (
    ZoomGuardError,
    base_for,
    face_boxes_on_canvas,
    reframe_crop,
    zoom_violation,
)
from editoria.render.media import MediaInfo
from editoria.schemas import (
    Box,
    Canvas,
    CaptionsSpec,
    ConformedClip,
    EditPlan,
    EncodeSettings,
    FaceSample,
    FaceTrack,
    OverlayClip,
    RenderInputs,
    VideoInterval,
)

FACE = Box(x=340, y=380, w=400, h=480)


def media(w: int = 1080, h: int = 1920, fps: int = 30, dur: float = 12.0) -> MediaInfo:
    return MediaInfo(
        path=Path("video_base.mp4"), width=w, height=h, fps=Fraction(fps), duration=dur,
        format_duration=dur, has_video=True, has_audio=True,
    )  # fmt: skip


def face(w: int = 1080, h: int = 1920, box: Box = FACE) -> FaceTrack:
    return FaceTrack(frame_w=w, frame_h=h, samples=[FaceSample(t=0, box=box)], union_box=box)


def plan(*video: VideoInterval) -> EditPlan:
    return EditPlan(
        version="V1", style="A", brand="master-solution", video=list(video),
        captions=CaptionsSpec(style="A"),
    )  # fmt: skip


def build(
    p: EditPlan,
    tmp: Path,
    inputs: RenderInputs | None = None,
    base: MediaInfo | None = None,
    enc: EncodeSettings | None = None,
    fc: FaceTrack | None = None,
) -> RenderGraph:
    return build_render_graph(
        p, inputs or RenderInputs(), base or media(), tmp / "video_base.mp4", tmp,
        enc or EncodeSettings(), face=fc if fc is not None else face(),
    )  # fmt: skip


def test_plain_base_has_no_split(tmp_path: Path) -> None:
    g = build(plan(), tmp_path)
    assert "split" not in g.script
    assert "fps=30/1[v0]" in g.script
    assert g.audio_label == "aout" and "[0:a]" in g.script
    assert g.duration == pytest.approx(12.0)


def test_reframe_cut_segments_cover_the_timeline(tmp_path: Path) -> None:
    p = plan(
        VideoInterval(id="v01", in_=0, out=2.4, method="original"),
        VideoInterval(id="v02", in_=2.4, out=4.0, method="reframe", zoom=1.15, anchor="face"),
    )
    g = build(p, tmp_path)
    assert "split=3" in g.script
    assert "trim=start=0:end=2.4" in g.script
    assert "trim=start=2.4:end=4," in g.script
    assert "trim=start=4," in g.script  # last segment open-ended: no frame lost
    assert "concat=n=3" in g.script
    assert "crop=940:1670:70:0" in g.script


def test_push_uses_zoompan_with_source_fps(tmp_path: Path) -> None:
    p = plan(VideoInterval(id="v02", in_=2, out=4, method="reframe", zoom=1.2, motion="push"))
    g = build(p, tmp_path)
    assert "zoompan=" in g.script and "fps=30/1" in g.script and ":d=1:" in g.script


def test_zoom_guard_rejects_over_max(tmp_path: Path) -> None:
    p = plan(VideoInterval(id="v02", in_=2, out=4, method="reframe", zoom=1.3))
    with pytest.raises(ZoomGuardError, match="P07"):
        build(p, tmp_path)


def test_zoom_guard_counts_native_pixels_of_small_sources(tmp_path: Path) -> None:
    p = plan(VideoInterval(id="v02", in_=1, out=2, method="reframe", zoom=1.1))
    with pytest.raises(ZoomGuardError):
        build(p, tmp_path, base=media(720, 1280, 25, 6.0), fc=face(720, 1280))
    bt = base_for(1080, 1920, Canvas(), None)
    assert zoom_violation(bt, 1.25, 1.25) is None
    assert zoom_violation(bt, None, 1.25) is None


def test_overlapping_intervals_are_rejected(tmp_path: Path) -> None:
    p = plan(
        VideoInterval(id="a", in_=0, out=3, method="original"),
        VideoInterval(id="b", in_=2, out=4, method="reframe", zoom=1.1),
    )
    with pytest.raises(RenderError, match="superpone"):
        build(p, tmp_path)


def test_generated_needs_accepted_clip_and_never_maps_its_audio(tmp_path: Path) -> None:
    p = plan(VideoInterval(id="v04", in_=8.5, out=10.5, method="generated", shot="G01"))
    with pytest.raises(RenderError, match="P05"):
        build(p, tmp_path)
    clip = ConformedClip(
        shot_id="G01", path=tmp_path / "g01.mp4", start=8.5, end=10.5, width=1080, height=1920
    )
    mix = tmp_path / "mezcla.wav"
    mix.write_bytes(b"RIFF")
    g = build(p, tmp_path, RenderInputs(shots={"G01": clip}, mix_wav=mix))
    assert "[1:v]trim=start=0:duration=2" in g.script
    assert "overlay=0:0:eof_action=pass" in g.script
    assert "[1:a]" not in g.script and "[0:a]" not in g.script
    assert "[2:a]aresample" in g.script  # the mix
    assert g.input_args[g.input_args.index("g01.mp4") - 1] == "-i"


def test_layer_order_and_relative_paths(tmp_path: Path) -> None:
    gdir = tmp_path / "graficos" / "g01"
    gdir.mkdir(parents=True)
    (gdir / "00001.png").write_bytes(b"")
    gif = tmp_path / "graficos" / "e01.gif"
    gif.write_bytes(b"GIF")
    ass = tmp_path / "subtitulos.ass"
    ass.write_text("[Script Info]\n", encoding="utf-8")
    inputs = RenderInputs(
        captions_ass=ass,
        overlays=[
            OverlayClip(id="e01", frames_pattern=gif, x=740, y=220, w=200, h=200, start=6.2,
                        end=7.4, is_gif=True),
            OverlayClip(id="g01", frames_pattern=gdir / "%05d.png", x=240, y=220, w=600,
                        h=200, start=0.3, end=1.8),
        ],
    )  # fmt: skip
    g = build(plan(), tmp_path, inputs)
    s = g.script
    assert s.index("overlay=x=240") < s.index("overlay=x=740") < s.index("ass=filename=")
    assert "ass=filename='subtitulos.ass'" in s
    assert "graficos/g01/%05d.png" in g.input_args
    assert "-ignore_loop" in g.input_args
    assert "eof_action=pass" in s and "setpts=PTS-STARTPTS+0.3/TB" in s
    media_args = [a for a in g.input_args if a.endswith((".png", ".gif", ".mp4"))]
    assert all(":" not in a for a in media_args)  # relative, never C:/...


def test_missing_overlay_files_are_skipped_with_warning(tmp_path: Path) -> None:
    inputs = RenderInputs(
        overlays=[
            OverlayClip(id="g09", frames_pattern=tmp_path / "nada" / "%05d.png", x=0, y=0,
                        w=10, h=10, start=0, end=1),
        ]
    )  # fmt: skip
    g = build(plan(), tmp_path, inputs)
    assert "overlay" not in g.script
    assert any("g09" in w for w in g.warnings)


def test_sample_window_trims_video_and_audio(tmp_path: Path) -> None:
    g = build(plan(), tmp_path, enc=EncodeSettings(sample_window=(2.0, 5.0)))
    # seek in the input (only the window is decoded) ...
    assert g.input_args[:5] == ["-ss", "2", "-t", "3", "-i"]
    # ... and restore the original timeline before any layer, then cut the window back to 0
    assert g.script.startswith("[0:v]setpts=PTS+2/TB,")
    assert "trim=start=2:end=5,setpts=PTS-STARTPTS[vout]" in g.script
    assert "atrim=start=0:end=3" in g.script  # the audio inputs are seeked as well
    assert g.duration == pytest.approx(3.0)


def test_sample_window_from_zero_does_not_seek(tmp_path: Path) -> None:
    g = build(plan(), tmp_path, enc=EncodeSettings(sample_window=(0.0, 4.0)))
    assert g.input_args[:3] == ["-t", "4", "-i"]
    assert "setpts=PTS+" not in g.script


def test_sample_window_seeks_the_mix_and_clips_segments(tmp_path: Path) -> None:
    p = plan(
        VideoInterval(id="v01", in_=0, out=2.4, method="original"),
        VideoInterval(id="v02", in_=2.4, out=4.0, method="reframe", zoom=1.15, anchor="face"),
        VideoInterval(id="v03", in_=6.0, out=9.0, method="reframe", zoom=1.1, anchor="face"),
    )
    mix = tmp_path / "mezcla.wav"
    mix.write_bytes(b"RIFF")
    g = build(p, tmp_path, RenderInputs(mix_wav=mix), enc=EncodeSettings(sample_window=(3.0, 7.0)))
    mix_at = g.input_args.index("mezcla.wav")
    assert g.input_args[mix_at - 5 : mix_at] == ["-ss", "3", "-t", "4", "-i"]
    assert "split=3" in g.script  # v01 (before the window) is not decoded at all
    assert "trim=start=3:end=4," in g.script
    assert "trim=start=4:end=6," in g.script
    assert "trim=start=6," in g.script  # the last segment stays open-ended
    assert "concat=n=3:v=1:a=0,setpts=PTS+3/TB,fps=30/1[v0]" in g.script


def test_sample_window_continues_push_zoom(tmp_path: Path) -> None:
    p = plan(VideoInterval(id="v02", in_=2, out=4, method="reframe", zoom=1.2, motion="push"))
    full = build(p, tmp_path)
    assert "min(on/59" in full.script
    g = build(p, tmp_path, enc=EncodeSettings(sample_window=(3.0, 5.0)))
    assert "min((on+30)/59" in g.script  # 1 s (30 frames) of the push already happened


def test_sample_window_skips_layers_outside_it(tmp_path: Path) -> None:
    gdir = tmp_path / "graficos" / "g01"
    gdir.mkdir(parents=True)
    (gdir / "00001.png").write_bytes(b"")
    gif = tmp_path / "graficos" / "e01.gif"
    gif.write_bytes(b"GIF")
    inputs = RenderInputs(
        overlays=[
            OverlayClip(id="g01", frames_pattern=gdir / "%05d.png", x=240, y=220, w=600,
                        h=200, start=0.3, end=1.8),
            OverlayClip(id="e01", frames_pattern=gif, x=740, y=220, w=200, h=200, start=6.2,
                        end=7.4, is_gif=True),
        ],
    )  # fmt: skip
    g = build(plan(), tmp_path, inputs, enc=EncodeSettings(sample_window=(5.0, 8.0)))
    assert "graficos/g01/%05d.png" not in g.input_args
    assert "graficos/e01.gif" in g.input_args
    # layers keep their original-time offsets (the timeline is restored after the base)
    assert "setpts=PTS-STARTPTS+6.2/TB" in g.script
    assert r"between(t\,6.2\,7.4)" in g.script


def test_same_plan_gives_the_same_graph(tmp_path: Path) -> None:
    p = plan(
        VideoInterval(id="v01", in_=0, out=2.4, method="original"),
        VideoInterval(id="v02", in_=2.4, out=4.0, method="reframe", zoom=1.15, motion="push"),
    )
    first, second = build(p, tmp_path), build(p, tmp_path)
    assert first.script == second.script and first.input_args == second.input_args


def test_small_source_is_upscaled_with_warning(tmp_path: Path) -> None:
    g = build(plan(), tmp_path, base=media(720, 1280, 25, 6.0), fc=face(720, 1280))
    assert "flags=lanczos" in g.script and "fps=25/1" in g.script
    assert any("sin detalle nativo nuevo" in w for w in g.warnings)


def test_horizontal_source_is_cropped_on_the_face(tmp_path: Path) -> None:
    fb = Box(x=1300, y=300, w=200, h=260)
    g = build(plan(), tmp_path, base=media(1920, 1080, 30, 6.0), fc=face(1920, 1080, fb))
    # crop width = round(1080 * 9/16) = 608, centred on x = 1400
    assert "crop=608:1080:1096:0" in g.script
    assert any("horizontal" in w and "rostro" in w for w in g.warnings)


def test_canvas_fps_override(tmp_path: Path) -> None:
    p = plan().model_copy(update={"canvas": Canvas(fps="25")})
    g = build(p, tmp_path)
    assert "fps=25/1" in g.script


def test_reframe_crop_stays_inside_base() -> None:
    bt = base_for(1080, 1920, Canvas(), None)
    c = reframe_crop(bt, 1.2, (10.0, 10.0))
    assert c.x == 0 and c.y == 0 and c.w == 900 and c.h == 1600
    c2 = reframe_crop(bt, 1.2, (1070.0, 1900.0))
    assert c2.x + c2.w <= 1080 and c2.y + c2.h <= 1920


def test_face_boxes_include_reframe_magnification() -> None:
    p = plan(VideoInterval(id="v02", in_=2, out=4, method="reframe", zoom=1.2, anchor="face"))
    boxes = face_boxes_on_canvas(p, face(), 1080, 1920, 2.5, 3.0)
    assert len(boxes) == 2
    assert boxes[1].w > boxes[0].w
    assert face_boxes_on_canvas(p, None, 1080, 1920, 0, 1) == []


def test_sheet_marks_include_edges() -> None:
    p = plan(VideoInterval(id="v02", in_=2.4, out=4.0, method="reframe", zoom=1.1))
    marks = sheet_marks(p, 12.0, 2.0)
    times = [m.t for m in marks]
    assert 0.0 in times and 10.0 in times and 2.4 in times
    assert any("v02" in m.label and "sale" in m.label for m in marks)
    with pytest.raises(ValueError):
        sheet_marks(p, 12.0, 0)
