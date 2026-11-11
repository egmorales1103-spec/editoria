"""QC: passes a correct render, catches black frames, audio offset, altered original,
captions over the face, unaccepted shots, unlicensed assets and the zoom guard."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from editoria.cli import app
from editoria.qc import DefaultQualityControl, render_markdown
from editoria.qc.analysis import correlate_voice, is_faststart, new_spans, parse_freeze
from editoria.qc.captions import parse_ass
from editoria.schemas import (
    REGISTRO_COLUMNS,
    Box,
    Canvas,
    CaptionEvent,
    Finding,
    QCReport,
    VideoInterval,
    VoiceCheck,
    read_model,
    write_model,
)
from editoria.util import ffmpeg, resources
from editoria.util.files import make_writable, write_csv_rows
from editoria.util.project import ProjectContext

runner = CliRunner()


def by_id(report: QCReport) -> dict[str, str]:
    return {c.id: c.status for c in report.checks}


def replace_video(ctx: ProjectContext, args: list[str]) -> None:
    """Re-encode V1/video.mp4 with extra ffmpeg ``args`` (in place)."""
    vdir = ctx.version_dir("V1")
    ffmpeg.run(["-i", "video.mp4", *args, "-movflags", "+faststart", "alterado.mp4"], cwd=vdir)
    os.replace(vdir / "alterado.mp4", vdir / "video.mp4")


def test_correct_render_has_no_fail(rendered: ProjectContext) -> None:
    report = DefaultQualityControl().run(rendered, "V1")
    st = by_id(report)
    assert not report.has_fail, [(c.id, c.detail) for c in report.checks if c.status == "FAIL"]
    for cid in ("decode", "format", "faststart", "duration", "black", "voice_sync",
                "original_hash", "licenses", "shots_accepted"):  # fmt: skip
        assert st[cid] == "PASS", (cid, st[cid])
    for cid in ("identity", "background", "lips", "aesthetic"):
        assert st[cid] == "HUMAN"
    assert "generated_shots" not in st
    qc_dir = rendered.version_dir("V1") / "qc"
    saved = read_model(qc_dir / "qc.json", QCReport)
    assert saved.version == "V1" and len(saved.checks) == len(report.checks)
    md = (qc_dir / "qc.md").read_text(encoding="utf-8")
    assert "REVISIÓN HUMANA" in md and "PASS" in md and "Evidencia" in md


def test_detects_injected_black_frames(rendered: ProjectContext) -> None:
    replace_video(
        rendered,
        ["-vf", "drawbox=x=0:y=0:w=iw:h=ih:color=black:t=fill:enable='between(t,5,5.6)'",
         "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-c:a", "copy"],
    )  # fmt: skip
    report = DefaultQualityControl().run(rendered, "V1")
    black = next(c for c in report.checks if c.id == "black")
    assert black.status == "FAIL"
    assert "5.0" in black.detail


def test_detects_200ms_audio_offset(rendered: ProjectContext) -> None:
    replace_video(
        rendered,
        ["-map", "0", "-c:v", "copy", "-af", "adelay=200:all=1,atrim=end=12",
         "-c:a", "aac", "-b:a", "192k", "-ar", "48000"],
    )  # fmt: skip
    report = DefaultQualityControl().run(rendered, "V1")
    sync = next(c for c in report.checks if c.id == "voice_sync")
    assert sync.status == "FAIL"
    assert "+200" in sync.detail


def test_detects_altered_original(rendered: ProjectContext) -> None:
    original = rendered.original_video()
    make_writable(original)
    with original.open("ab") as fh:
        fh.write(b"\x00alterado")
    report = DefaultQualityControl().run(rendered, "V1")
    assert by_id(report)["original_hash"] == "FAIL"


def test_detects_caption_over_the_face(rendered: ProjectContext) -> None:
    ass = rendered.version_dir("V1") / "subtitulos.ass"
    text = ass.read_text(encoding="utf-8")
    text += "Dialogue: 0,0:00:08.10,0:00:09.00,A,,0,0,0,,{\\an5\\pos(540,620)}sobre la cara\n"
    ass.write_text(text, encoding="utf-8")
    report = DefaultQualityControl().run(rendered, "V1")
    cap = next(c for c in report.checks if c.id == "captions")
    assert cap.status == "FAIL" and "rostro" in cap.detail


def test_captions_json_outside_safe_zone_fails(rendered: ProjectContext) -> None:
    vdir = rendered.version_dir("V1")
    events = [
        CaptionEvent(start=0.3, end=2.0, text="abajo", box=Box(x=200, y=1700, w=600, h=120)),
    ]
    (vdir / "subtitulos.json").write_text(
        json.dumps([e.model_dump(mode="json") for e in events]), encoding="utf-8"
    )
    report = DefaultQualityControl().run(rendered, "V1")
    cap = next(c for c in report.checks if c.id == "captions")
    assert cap.status == "FAIL" and "zona segura" in cap.detail


def test_generated_shots_must_be_accepted(rendered: ProjectContext) -> None:
    vdir = rendered.version_dir("V1")
    plan = rendered.load_plan("V1")
    plan.video.append(VideoInterval(id="v04", in_=8.5, out=10.5, method="generated", shot="G01"))
    plan.video[2] = plan.video[2].model_copy(update={"out": 8.5})
    write_model(vdir / "plan.yaml", plan)
    row = {c: "" for c in REGISTRO_COLUMNS} | {"id": "G01", "veredicto": "reintentar"}
    write_csv_rows(rendered.generations_registry, REGISTRO_COLUMNS, [row])
    qc = DefaultQualityControl(voice_checker=lambda a, b: VoiceCheck(offset_ms=0, similarity=1))
    st = by_id(qc.run(rendered, "V1"))
    assert st["shots_accepted"] == "FAIL"
    assert st["generated_shots"] == "HUMAN"  # P24
    row["veredicto"] = "aceptado"
    write_csv_rows(rendered.generations_registry, REGISTRO_COLUMNS, [row])
    assert by_id(qc.run(rendered, "V1"))["shots_accepted"] == "PASS"


def test_unlicensed_assets_fail(rendered: ProjectContext, monkeypatch: pytest.MonkeyPatch) -> None:
    from editoria.schemas import AssetManifest

    monkeypatch.setattr(resources, "load_sfx_manifest", lambda: AssetManifest())
    report = DefaultQualityControl().run(rendered, "V1")
    lic = next(c for c in report.checks if c.id == "licenses")
    assert lic.status == "FAIL" and "pop_1" in lic.detail


def test_zoom_guard_fails_on_plan_over_limit(rendered: ProjectContext) -> None:
    vdir = rendered.version_dir("V1")
    plan = rendered.load_plan("V1")
    plan.video[1] = plan.video[1].model_copy(update={"zoom": 1.4})
    write_model(vdir / "plan.yaml", plan)
    assert by_id(DefaultQualityControl().run(rendered, "V1"))["zoom_guard"] == "FAIL"


def test_injected_voice_checker_and_linter(rendered: ProjectContext) -> None:
    calls: list[tuple[Path, Path]] = []

    def checker(a: Path, b: Path) -> VoiceCheck:
        calls.append((a, b))
        return VoiceCheck(offset_ms=12.0, similarity=0.95)

    def linter(plan: object, ctx: object) -> list[Finding]:
        return [Finding(id="P16", severity="ERROR", message="demasiados SFX")]

    report = DefaultQualityControl(voice_checker=checker, linter=linter).run(rendered, "V1")
    st = by_id(report)
    assert calls and st["voice_sync"] == "PASS"
    assert st["plan_lint"] == "FAIL"


def test_missing_video_fails(rendered: ProjectContext) -> None:
    (rendered.version_dir("V1") / "video.mp4").unlink()
    report = DefaultQualityControl().run(rendered, "V1")
    assert by_id(report)["decode"] == "FAIL" and report.has_fail


def test_cli_qc_exit_codes(rendered: ProjectContext) -> None:
    res = runner.invoke(app, ["qc", "demo", "--version", "V1"])
    assert res.exit_code == 0, res.output
    assert "REVISIÓN HUMANA" in res.output
    make_writable(rendered.original_video())
    with rendered.original_video().open("ab") as fh:
        fh.write(b"x")
    res = runner.invoke(app, ["qc", "demo", "--version", "V1"])
    assert res.exit_code == 1


# ---- unit pieces ------------------------------------------------------------------------
def test_new_spans_only_counts_new() -> None:
    assert new_spans([(1.0, 1.5), (5.0, 5.5)], [(0.9, 1.6)]) == [(5.0, 5.5)]
    assert parse_freeze("freeze_start: 2.0\nfreeze_end: 3.0\nfreeze_start: 9", 12) == [
        (2.0, 3.0),
        (9.0, 12.0),
    ]


def test_faststart_detection(fixtures_dir: Path, tmp_path: Path) -> None:
    slow = tmp_path / "sin faststart ñ.mp4"
    ffmpeg.run(["-i", fixtures_dir / "sin_audio.mp4", "-c", "copy", slow])
    assert not is_faststart(slow)[0]
    assert is_faststart(fixtures_dir / "sin_audio.mp4")[0]


def test_correlate_voice_measures_offset(fixtures_dir: Path, tmp_path: Path) -> None:
    src = fixtures_dir / "mix_fixture.wav"
    late = tmp_path / "tarde ñ.wav"
    ffmpeg.run(["-i", src, "-af", "adelay=120:all=1", late])
    vc = correlate_voice(src, late)
    assert vc.offset_ms == pytest.approx(120, abs=3)
    assert vc.similarity > 0.9
    same = correlate_voice(src, src)
    assert same.offset_ms == 0 and same.similarity > 0.99


def test_parse_ass_estimates_boxes(fixtures_dir: Path) -> None:
    boxes = parse_ass(fixtures_dir / "captions_fixture.ass", Canvas())
    assert len(boxes) == 5
    two_lines = boxes[1]
    assert two_lines.start == pytest.approx(2.6) and two_lines.end == pytest.approx(4.96)
    assert two_lines.box.y2 == 1920 - 560  # bottom aligned on MarginV
    assert two_lines.box.h > 140
    assert all(b.estimated for b in boxes)


def test_markdown_labels_human_review() -> None:
    from editoria.schemas import QCCheck

    rep = QCReport(
        version="V1",
        checks=[QCCheck(id="identity", prompt_question="P24 · ¿...?", status="HUMAN", detail="x")],
        summary="s",
    )
    assert "REVISIÓN HUMANA" in render_markdown(rep)
