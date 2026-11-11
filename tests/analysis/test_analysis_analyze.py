"""analyze: silences, cuts, face zone, segments, edit map."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest
from typer.testing import CliRunner

from editoria.analysis import analyze_project
from editoria.analysis import face as face_mod
from editoria.analysis.detectors import detect_silences, parse_silencedetect
from editoria.analysis.face import detect_faces, estimated_box, union
from editoria.analysis.segments import build_segments
from editoria.cli import app
from editoria.ingest import IngestError, init_project, transcribe_project
from editoria.schemas import MAPA_COLUMNS, Box, SegmentList, Transcript, Word, write_model
from editoria.util.project import ProjectContext

runner = CliRunner()

PAUSES = [(2.2, 2.6), (5.0, 5.5), (7.6, 8.1), (10.4, 10.8)]
TOL = 0.12


def _near(a: float, b: float, tol: float = TOL) -> bool:
    return abs(a - b) <= tol


def test_analyze_writes_every_artifact(transcribed: ProjectContext) -> None:
    segs = analyze_project(transcribed)
    for name in (
        "silencios.json",
        "cortes.json",
        "rostro.json",
        "segmentos.json",
        "mapa_edicion.csv",
        "probe.json",
    ):
        assert transcribed.analysis(name).exists(), name
    assert transcribed.load_segments() == segs


def test_analyze_detects_hard_cuts_at_4_and_7_85(transcribed: ProjectContext) -> None:
    analyze_project(transcribed)
    cuts = transcribed.load_cuts()
    assert cuts is not None and len(cuts.cuts) == 2
    assert _near(cuts.cuts[0], 4.0) and _near(cuts.cuts[1], 7.85)


def test_analyze_detects_pauses_between_voice_bursts(transcribed: ProjectContext) -> None:
    analyze_project(transcribed)
    sil = transcribed.load_silences()
    assert sil is not None
    for a, b in PAUSES:
        assert any(_near(s.start, a) and _near(s.end, b) for s in sil.silences), (a, b)
    # leading silence and trailing silence (closed at the video duration)
    assert _near(sil.silences[0].start, 0.0) and _near(sil.silences[0].end, 0.3)
    assert _near(sil.silences[-1].end, 12.0)


def test_analyze_face_falls_back_to_estimated_upper_centre(transcribed: ProjectContext) -> None:
    analyze_project(transcribed)  # synthetic video: no real face -> estimate
    face = transcribed.load_face()
    assert face is not None and face.estimated is True
    assert (face.frame_w, face.frame_h) == (1080, 1920)
    box = face.union_box
    assert box is not None
    assert box.x + box.w / 2 == pytest.approx(540, abs=2)  # centred
    assert box.y < 1920 / 3  # upper third
    assert len(face.samples) == 25 and face.samples[1].t == 0.5
    assert all(s.box == box for s in face.samples)


def test_analyze_segments_follow_sentences_and_pauses(transcribed: ProjectContext) -> None:
    segs = analyze_project(transcribed)
    expected = [(0.3, 2.2), (2.6, 5.0), (5.5, 7.6), (8.1, 10.4), (10.8, 11.7)]
    assert len(segs.segments) == 5
    for seg, (a, b) in zip(segs.segments, expected, strict=True):
        assert _near(seg.start, a) and _near(seg.end, b)
        assert seg.role is None and seg.intent == "" and seg.visual == ""
    assert segs.segments[0].text == "Hoy te muestro cómo automatizar"
    assert [s.id for s in segs.segments] == ["s01", "s02", "s03", "s04", "s05"]


def test_analyze_edit_map_has_the_exact_template_columns(transcribed: ProjectContext) -> None:
    analyze_project(transcribed)
    path = transcribed.analysis("mapa_edicion.csv")
    template = Path(__file__).resolve().parents[2] / "templates" / "docs" / "Mapa_Edicion.csv"
    assert (
        path.read_text(encoding="utf-8").splitlines()[0]
        == (template.read_text(encoding="utf-8").splitlines()[0])
    )
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
        assert tuple(reader.fieldnames or ()) == MAPA_COLUMNS
    assert len(rows) == 5
    assert rows[0]["entrada"] == "00:00.30" and rows[0]["intencion"] == ""
    assert rows[1]["frase_original"] == "las tareas repetitivas de tu equipo"


def test_analyze_horizontal_video_estimates_zone_from_the_9_16_crop(
    fixtures_dir: Path, projects_dir: Path
) -> None:
    ctx = init_project(fixtures_dir / "base_1920x1080.mp4", "hor", "master-solution")
    transcribe_project(ctx, backend="fixture")
    analyze_project(ctx)
    face = ctx.load_face()
    assert face is not None and (face.frame_w, face.frame_h) == (1920, 1080)
    assert face.union_box is not None and face.union_box.w < 400
    assert face.union_box.x + face.union_box.w / 2 == pytest.approx(960, abs=2)


# ---- preconditions / protection -----------------------------------------------------------------
def test_analyze_requires_the_transcript(spaced_video: Path, projects_dir: Path) -> None:
    ctx = init_project(spaced_video, "sin-transcript", "master-solution")
    with pytest.raises(IngestError, match="transcribe sin-transcript"):
        analyze_project(ctx)
    assert not ctx.analysis("segmentos.json").exists()


def test_analyze_keeps_the_directors_decisions_unless_forced(
    transcribed: ProjectContext,
) -> None:
    segs = analyze_project(transcribed)
    decided = SegmentList(
        segments=[
            segs.segments[0].model_copy(update={"role": "hook", "intent": "Gancho"}),
            *segs.segments[1:],
        ]
    )
    write_model(transcribed.analysis("segmentos.json"), decided)
    with pytest.raises(IngestError, match="--force"):
        analyze_project(transcribed)
    assert transcribed.load_segments().segments[0].role == "hook"
    analyze_project(transcribed, force=True)
    assert transcribed.load_segments().segments[0].role is None
    # With no decisions to protect, re-running is free.
    analyze_project(transcribed)


def test_analyze_without_audio_has_no_silences(fixtures_dir: Path) -> None:
    sil = detect_silences(fixtures_dir / "sin_audio.mp4", 4.0, has_audio=False)
    assert sil.silences == []


# ---- units ------------------------------------------------------------------------------------------
def test_parse_silencedetect_handles_open_trailing_silence() -> None:
    log = (
        "[silencedetect @ 0x1] silence_start: 0\n"
        "[silencedetect @ 0x1] silence_end: 0.3 | silence_duration: 0.3\n"
        "[silencedetect @ 0x1] silence_start: 11.7\n"
    )
    out = parse_silencedetect(log, 12.0)
    assert [(s.start, s.end) for s in out] == [(0.0, 0.3), (11.7, 12.0)]


def _words(spec: list[tuple[str, float, float]]) -> Transcript:
    return Transcript(model="x", words=[Word(text=t, start=a, end=b, prob=0.9) for t, a, b in spec])


def test_segments_split_on_sentence_punctuation_without_pause() -> None:
    tr = _words([("Hola.", 0.0, 0.3), ("Seguimos", 0.32, 0.6), ("ahora?", 0.62, 0.9)])
    segs = build_segments(tr)
    assert [s.text for s in segs.segments] == ["Hola.", "Seguimos ahora?"]


def test_segments_split_long_runs_at_the_biggest_pause() -> None:
    spec = [(f"w{i}", i * 1.0, i * 1.0 + 0.9) for i in range(12)]
    # one 0.5 s gap in the middle; the pause threshold is disabled so only the length guard acts
    spec = [
        (t, a + (0.5 if i >= 6 else 0.0), b + (0.5 if i >= 6 else 0.0))
        for i, (t, a, b) in enumerate(spec)
    ]
    segs = build_segments(_words(spec), pause_s=10.0)
    assert len(segs.segments) >= 2
    assert all(s.end - s.start <= 8.0 for s in segs.segments)
    assert segs.segments[0].end == pytest.approx(5.9)  # split at the 0.5 s gap
    assert " ".join(s.text for s in segs.segments).split() == [t for t, _, _ in spec]


def test_segments_of_empty_transcript() -> None:
    assert build_segments(Transcript(model="x", words=[])).segments == []


def test_union_and_estimated_box() -> None:
    assert union([]) is None
    assert union([Box(x=0, y=0, w=10, h=10), Box(x=20, y=5, w=10, h=10)]) == Box(
        x=0, y=0, w=30, h=15
    )
    assert estimated_box(1080, 1920) == Box(x=340, y=384, w=400, h=480)


def test_detect_faces_without_opencv_is_estimated(
    spaced_video: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(face_mod, "opencv_available", lambda: False)
    face = detect_faces(spaced_video, 1080, 1920, 12.0)
    assert face.estimated and face.union_box == estimated_box(1080, 1920)


def test_detect_faces_with_opencv_but_no_face_is_estimated(spaced_video: Path) -> None:
    face = detect_faces(spaced_video, 1080, 1920, 12.0)  # testsrc2 has no faces
    assert face.estimated is True


# ---- CLI --------------------------------------------------------------------------------------------
def test_cli_analyze(transcribed: ProjectContext) -> None:
    res = runner.invoke(app, ["analyze", "demo"])
    assert res.exit_code == 0, res.output
    assert "5 segmentos" in res.output and "cortes: 2" in res.output
    assert "zona estimada" in " ".join(res.output.split())


def test_cli_analyze_without_transcript(spaced_video: Path, projects_dir: Path) -> None:
    init_project(spaced_video, "x", "master-solution")
    res = runner.invoke(app, ["analyze", "x"])
    assert res.exit_code == 1
    assert "Falta la transcripción" in " ".join(res.output.split())
