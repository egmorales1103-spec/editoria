"""QC: report bound to the verified video, cached analysis of the original, refusal on
delivered versions and negative cases (duration, loudness/clipping, codec/resolution/FPS)."""

from __future__ import annotations

import json
import os
from fractions import Fraction
from pathlib import Path

import pytest
from typer.testing import CliRunner

from editoria.cli import app
from editoria.qc import DefaultQualityControl
from editoria.qc import control as qc_control
from editoria.render.media import MediaInfo
from editoria.schemas import QCReport, VoiceCheck, read_model
from editoria.util import ffmpeg
from editoria.util.files import sha256_file
from editoria.util.project import DELIVERED_MARKER, ProjectContext

runner = CliRunner()


def status(report: QCReport, cid: str) -> str:
    return next(c.status for c in report.checks if c.id == cid)


def detail(report: QCReport, cid: str) -> str:
    return next(c.detail for c in report.checks if c.id == cid)


def reencode(ctx: ProjectContext, args: list[str]) -> None:
    vdir = ctx.version_dir("V1")
    ffmpeg.run(["-i", "video.mp4", *args, "-movflags", "+faststart", "alterado.mp4"], cwd=vdir)
    os.replace(vdir / "alterado.mp4", vdir / "video.mp4")


def same_voice(a: Path, b: Path) -> VoiceCheck:
    return VoiceCheck(offset_ms=0.0, similarity=1.0)


# ---- the report names the exact video it checked -------------------------------------------
def test_report_stores_the_sha256_of_the_checked_video(rendered: ProjectContext) -> None:
    video = rendered.version_dir("V1") / "video.mp4"
    report = DefaultQualityControl().run(rendered, "V1")
    assert report.video_sha256 == sha256_file(video)
    saved = read_model(rendered.version_dir("V1") / "qc" / "qc.json", QCReport)
    assert saved.video_sha256 == report.video_sha256


def test_report_without_video_has_empty_sha256(rendered: ProjectContext) -> None:
    (rendered.version_dir("V1") / "video.mp4").unlink()
    assert DefaultQualityControl().run(rendered, "V1").video_sha256 == ""


# ---- cache of the original's analysis ------------------------------------------------------
def test_original_analysis_is_cached_by_hash(
    rendered: ProjectContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    real = qc_control.analyze_media

    def spy(path: Path, **kw: object) -> qc_control.VideoAnalysis:
        calls.append(path.name)
        return real(path, **kw)  # type: ignore[arg-type]

    monkeypatch.setattr(qc_control, "analyze_media", spy)
    qc = DefaultQualityControl(voice_checker=same_voice)
    first = qc.run(rendered, "V1")
    original = rendered.original_video().name
    assert calls.count(original) == 1
    cache = qc_control.original_cache_path(rendered)
    assert cache == rendered.analysis_dir / ".cache" / "qc_original.json"
    data = json.loads(cache.read_text(encoding="utf-8"))
    assert data["sha256"] == sha256_file(rendered.original_video())
    assert "ebur128=True" in data["params"]

    calls.clear()
    second = qc.run(rendered, "V1")
    assert calls == ["video.mp4"]  # the original is not decoded again
    assert [(c.id, c.status) for c in first.checks] == [(c.id, c.status) for c in second.checks]

    # a stale key (other original) or a corrupt file forces a fresh analysis
    data["sha256"] = "0" * 64
    cache.write_text(json.dumps(data), encoding="utf-8")
    calls.clear()
    qc.run(rendered, "V1")
    assert calls.count(original) == 1
    cache.write_text("{no es json", encoding="utf-8")
    calls.clear()
    qc.run(rendered, "V1")
    assert calls.count(original) == 1


# ---- delivered versions are immutable ------------------------------------------------------
def test_qc_refuses_delivered_version(rendered: ProjectContext) -> None:
    vdir = rendered.version_dir("V1")
    (vdir / DELIVERED_MARKER).write_text("V1", encoding="utf-8")
    with pytest.raises(PermissionError, match="entregada"):
        DefaultQualityControl().run(rendered, "V1")
    res = runner.invoke(app, ["qc", "demo", "--version", "V1"])
    assert res.exit_code != 0 and "entregada" in res.output
    assert not (vdir / "qc").exists()


# ---- negatives: duration -------------------------------------------------------------------
def _media(duration: float, fps: int = 30) -> MediaInfo:
    return MediaInfo(
        path=Path("v.mp4"), width=1080, height=1920, fps=Fraction(fps), duration=duration,
        format_duration=duration, has_video=True, has_audio=True,
    )  # fmt: skip


@pytest.mark.parametrize(
    ("final", "expected"),
    [
        (12.0, "PASS"),
        (12.0 + 1 / 30, "PASS"),  # exactly one frame longer
        (12.0 - 1 / 30, "PASS"),  # exactly one frame shorter
        (12.0 + 2 / 30, "FAIL"),
        (12.0 - 2 / 30, "FAIL"),
        (11.5, "FAIL"),
    ],
)
def test_duration_tolerance_is_one_frame(final: float, expected: str) -> None:
    check = DefaultQualityControl(linter=lambda p, c: [])._duration(_media(final), _media(12.0))
    assert check.status == expected, check.evidence


def test_shorter_render_fails_duration(rendered: ProjectContext) -> None:
    reencode(rendered, ["-t", "11.5", "-c", "copy"])
    report = DefaultQualityControl(voice_checker=same_voice).run(rendered, "V1")
    assert status(report, "duration") == "FAIL"
    assert "difiere" in detail(report, "duration")


# ---- negatives: loudness / clipping --------------------------------------------------------
def test_clipped_loud_audio_fails(rendered: ProjectContext) -> None:
    reencode(rendered, ["-c:v", "copy", "-af", "volume=24dB", "-c:a", "aac", "-b:a", "192k",
                        "-ar", "48000"])  # fmt: skip
    report = DefaultQualityControl(voice_checker=same_voice).run(rendered, "V1")
    assert status(report, "loudness") == "FAIL"
    text = detail(report, "loudness")
    assert "saturadas" in text or "true peak" in text


def test_quiet_audio_is_far_from_the_target(rendered: ProjectContext) -> None:
    reencode(rendered, ["-c:v", "copy", "-af", "volume=-15dB", "-c:a", "aac", "-b:a", "192k",
                        "-ar", "48000"])  # fmt: skip
    report = DefaultQualityControl(voice_checker=same_voice).run(rendered, "V1")
    assert status(report, "loudness") == "WARN"
    assert "lejos del objetivo" in detail(report, "loudness")


# ---- negatives: codec / resolution / FPS ---------------------------------------------------
@pytest.mark.parametrize(
    ("args", "needle"),
    [
        (["-c:v", "mpeg4", "-q:v", "5", "-c:a", "copy"], "códec de video mpeg4"),
        (["-vf", "scale=720:1280", "-c:v", "libx264", "-preset", "ultrafast",
          "-pix_fmt", "yuv420p", "-c:a", "copy"], "resolución 720×1280"),
        (["-r", "25", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
          "-c:a", "copy"], "FPS 25"),
        (["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac",
          "-ar", "44100"], "44100 Hz"),
    ],
    ids=["codec", "resolucion", "fps", "audio-sr"],
)  # fmt: skip
def test_wrong_format_fails(rendered: ProjectContext, args: list[str], needle: str) -> None:
    reencode(rendered, args)
    report = DefaultQualityControl(voice_checker=same_voice).run(rendered, "V1")
    assert status(report, "format") == "FAIL"
    assert needle in detail(report, "format"), detail(report, "format")
