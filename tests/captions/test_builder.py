"""ASS/SRT/VTT/JSON outputs, styles, highlight modes, placement and build_for_version."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from editoria.captions import (
    AssCaptionBuilder,
    build_for_version,
    face_avoid_boxes,
    parse_srt,
    read_events_json,
    stable_placement,
    to_srt,
    to_vtt,
)
from editoria.captions.fonts import resolve_family
from editoria.cli import app
from editoria.contracts import CaptionBuilder
from editoria.schemas import (
    Box,
    Canvas,
    CaptionEvent,
    EditorialTitle,
    EditPlan,
    Emphasis,
    FaceSample,
    FaceTrack,
    Transcript,
    read_model,
    write_model,
)
from editoria.util import resources
from editoria.util.project import PLAN_FILE, ProjectContext

runner = CliRunner()
CUTS = [4.0, 7.85]


@pytest.fixture(scope="module")
def transcript(fixtures_dir: Path) -> Transcript:
    return read_model(fixtures_dir / "transcript_fixture.json", Transcript)


def _build(transcript: Transcript, style_id: str, out: Path, **kw):  # type: ignore[no-untyped-def]
    builder = AssCaptionBuilder(fonts_dir=out / "sin_fuentes")
    arts = builder.build(
        transcript,
        resources.load_style(style_id),
        resources.load_brand("master-solution"),
        kw.pop("canvas", Canvas()),
        kw.pop("avoid", []),
        kw.pop("emphasis", [Emphasis(word=4), Emphasis(word=13, color="#FF0000")]),
        out,
        cuts=CUTS,
        duration=12.0,
        **kw,
    )
    return builder, arts


def test_builder_satisfies_contract() -> None:
    assert isinstance(AssCaptionBuilder(), CaptionBuilder)


def test_srt_roundtrip_and_vtt(tmp_path: Path, transcript: Transcript) -> None:
    _, arts = _build(transcript, "A", tmp_path / "salida ñ")
    srt_text = arts.srt.read_text(encoding="utf-8")
    parsed = parse_srt(srt_text)
    spoken = [e for e in arts.events if not e.editorial]
    assert [(round(e.start, 3), round(e.end, 3), e.text) for e in parsed] == [
        (round(e.start, 3), round(e.end, 3), e.text) for e in spoken
    ]
    assert to_srt(parsed) == to_srt(spoken)
    assert "{" not in srt_text and "\\" not in srt_text  # clean, no ASS tags
    assert "cómo" in srt_text  # UTF-8 accents preserved
    vtt = arts.vtt.read_text(encoding="utf-8")
    assert vtt.startswith("WEBVTT\n\n")
    assert re.search(r"00:00:00\.300 --> 00:00:0\d\.\d{3}", vtt)
    assert [e.text for e in parse_srt(vtt)] == [e.text for e in spoken]
    assert read_events_json(tmp_path / "salida ñ" / "subtitulos.json") == arts.events


def test_srt_parser_tolerates_crlf_and_bom() -> None:
    text = "\ufeff1\r\n00:00:01,000 --> 00:00:02,500\r\nHola\r\nequipo\r\n\r\n"
    (ev,) = parse_srt(text)
    assert (ev.start, ev.end, ev.text) == (1.0, 2.5, "Hola\nequipo")
    vtt = to_vtt([CaptionEvent(start=0, end=1, text="A & <b>")])
    assert "A &amp; &lt;b&gt;" in vtt


def test_ass_styles_and_tags(tmp_path: Path, transcript: Transcript) -> None:
    titles = [EditorialTitle(text="Tres claves", in_=5.0, out=7.0)]
    _, arts = _build(transcript, "A", tmp_path / "a", editorial_titles=titles)
    ass_a = arts.ass.read_text(encoding="utf-8")
    assert "PlayResX: 1080" in ass_a and "PlayResY: 1920" in ass_a
    assert re.search(r"^Style: A,", ass_a, re.M) and re.search(r"^Style: A_titulo,", ass_a, re.M)
    assert r"\fad(" in ass_a  # style A animates with fade
    assert r"\1c&H0000FF&" in ass_a  # explicit emphasis colour #FF0000 -> BGR
    assert r"\1c&H00D4FF&" in ass_a  # accent highlight on word 4 (automatizar)
    assert r"\t(" not in ass_a  # fade styles highlight emphasis words only (no karaoke)
    title_line = next(line for line in ass_a.splitlines() if ",A_titulo," in line)
    assert "TRES CLAVES" in title_line  # editorial style is upper case in A
    # Title events are flagged and excluded from SRT
    assert any(e.editorial for e in arts.events)
    assert "TRES CLAVES" not in arts.srt.read_text(encoding="utf-8")

    _, arts_c = _build(transcript, "C", tmp_path / "c")
    ass_c = arts_c.ass.read_text(encoding="utf-8")
    assert r"\fscx70\fscy70\t(0,90,\fscx110\fscy110)" in ass_c  # pop animation
    # karaoke: each word switches to the highlight colour while spoken
    assert re.search(r"\\t\(\d+,\d+,\\1c&H00D4FF&\)", ass_c)
    assert "AUTOMATIZAR" in ass_c  # upper case style


def test_placement_inside_safe_zone(tmp_path: Path, transcript: Transcript) -> None:
    canvas = Canvas()
    safe = canvas.safe_box()
    for sid in "ABC":
        _, arts = _build(transcript, sid, tmp_path / sid)
        boxes = {(e.box.x, e.box.y) for e in arts.events if e.box and not e.editorial}
        for e in arts.events:
            assert e.box is not None
            assert safe.y <= e.box.y and e.box.y2 <= safe.y2, (sid, e.box)
        # stable vertical position for all spoken events
        centres = {e.box.y + e.box.h // 2 for e in arts.events if e.box and not e.editorial}
        assert len(centres) <= 2 and boxes


def test_relocates_when_face_collides(tmp_path: Path, transcript: Transcript) -> None:
    style = resources.load_style("A").captions
    canvas = Canvas()
    free = stable_placement(style, canvas, [])
    face = Box(x=300, y=free.cy - 150, w=480, h=300)
    moved = stable_placement(style, canvas, [face])
    assert moved.relocated and moved.cy != free.cy
    _, arts = _build(transcript, "A", tmp_path / "rostro", avoid=[face])
    for e in arts.events:
        assert e.box is not None and not e.box.intersects(face)
        assert canvas.safe_box().y <= e.box.y and e.box.y2 <= canvas.safe_box().y2


def test_face_avoid_boxes_use_base_transform() -> None:
    # Horizontal 1920x1080 source: cropped to 9:16 around the face, then scaled 1080/608.
    face = FaceTrack(
        frame_w=1920,
        frame_h=1080,
        samples=[FaceSample(t=0, box=Box(x=860, y=200, w=200, h=260))],
    )
    (box,) = face_avoid_boxes(face, Canvas())
    assert box.w == round(200 * 1080 / 608)
    assert box.x >= 0 and box.x2 <= 1080
    assert face_avoid_boxes(None, Canvas()) == []


def test_font_fallback_warns(tmp_path: Path) -> None:
    family, warning = resolve_family(["FuenteQueNoExiste123"], tmp_path)
    assert warning and "FuenteQueNoExiste123" in warning
    assert family


def test_build_for_version_and_cli(fixture_project: ProjectContext, fixtures_dir: Path) -> None:
    vdir = fixture_project.version_dir("V1")
    vdir.mkdir(parents=True)
    plan = read_model(fixtures_dir / "plan_fixture.yaml", EditPlan)
    plan.captions.editorial_titles.append(EditorialTitle(text="Tres claves", in_=8.2, out=9.5))
    write_model(vdir / PLAN_FILE, plan)
    arts = build_for_version(fixture_project, "V1")
    for name in ("subtitulos.ass", "subtitulos.srt", "subtitulos.vtt", "subtitulos.json"):
        assert (vdir / name).is_file()
    assert any(e.editorial for e in arts.events)

    res = runner.invoke(app, ["captions", "build", "demo", "--version", "V1"], terminal_width=200)
    assert res.exit_code == 0, res.output
    res = runner.invoke(app, ["captions", "build", "demo", "--version", "V9"], terminal_width=200)
    assert res.exit_code != 0
