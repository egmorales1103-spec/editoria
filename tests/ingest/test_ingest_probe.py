"""probe: metadata, integrity and warnings."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from editoria.cli import app
from editoria.ingest import init_project, probe_project
from editoria.ingest.probe import (
    CORRUPTION_PREFIX,
    build_probe,
    has_corruption,
    make_warnings,
    probe_file,
)
from editoria.schemas import ProbeResult
from editoria.util.log import read_jsonl
from editoria.util.project import ProjectContext

runner = CliRunner()


def _project(video: Path, slug: str = "p") -> ProjectContext:
    return init_project(video, slug, "master-solution")


def test_probe_clean_video_has_no_warnings_and_writes_probe_json(
    ingested: ProjectContext,
) -> None:
    res = probe_project(ingested)
    assert (res.width, res.height) == (1080, 1920)
    assert res.fps == "30/1"
    assert res.duration_s == 12.0 or abs(res.duration_s - 12.0) < 0.1
    assert res.has_audio and res.audio is not None
    assert (res.audio.codec, res.audio.sr, res.audio.ch) == ("aac", 48000, 1)
    assert res.video_codec == "h264" and res.pix_fmt == "yuv420p"
    assert res.vfr is False and res.rotation == 0
    assert res.warnings == []
    assert ingested.load_probe() == res


def test_probe_logs_the_ffmpeg_calls_of_the_project(ingested: ProjectContext) -> None:
    probe_project(ingested)
    tools = {rec["tool"] for rec in read_jsonl(ingested.commands_log)}
    assert tools == {"ffprobe", "ffmpeg"}


def test_probe_warns_low_resolution(fixtures_dir: Path, projects_dir: Path) -> None:
    res = probe_project(_project(fixtures_dir / "base_720x1280_25.mp4"))
    assert res.width == 720
    assert res.fps == "25/1"
    assert any("720 px" in w and "1080" in w for w in res.warnings)
    assert not any("horizontal" in w for w in res.warnings)


def test_probe_warns_horizontal(fixtures_dir: Path, projects_dir: Path) -> None:
    res = probe_project(_project(fixtures_dir / "base_1920x1080.mp4"))
    assert not res.is_vertical
    assert any("horizontal" in w and "1920x1080" in w for w in res.warnings)
    assert not any("px (<" in w for w in res.warnings)  # width 1920 is not low-res


def test_probe_warns_when_there_is_no_audio(fixtures_dir: Path, projects_dir: Path) -> None:
    res = probe_project(_project(fixtures_dir / "sin_audio.mp4"))
    assert res.has_audio is False and res.audio is None
    assert any("no tiene pista de audio" in w for w in res.warnings)


def test_probe_detects_variable_frame_rate(defective_dir: Path) -> None:
    res = probe_file(defective_dir / "vfr.mp4")
    assert res.vfr is True
    assert any("VFR" in w for w in res.warnings)


def test_probe_cfr_video_is_not_vfr(fixtures_dir: Path) -> None:
    assert probe_file(fixtures_dir / "base_720x1280_25.mp4").vfr is False


def test_probe_reports_rotation_from_display_matrix(defective_dir: Path) -> None:
    res = probe_file(defective_dir / "rotado.mp4")
    assert res.rotation == 90
    assert (res.width, res.height) == (720, 1280)  # coded size
    assert (res.display_width, res.display_height) == (1280, 720)
    assert any("rotación" in w for w in res.warnings)
    assert any("horizontal" in w for w in res.warnings)


def test_build_probe_normalises_negative_rotation_and_missing_rates() -> None:
    data = {
        "format": {"duration": "3.0"},
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "pix_fmt": "yuv420p",
                "width": 1920,
                "height": 1080,
                "r_frame_rate": "30000/1001",
                "avg_frame_rate": "0/0",
                "nb_frames": "N/A",
                "side_data_list": [{"rotation": -90}],
            }
        ],
    }
    res = build_probe(data)
    assert res.rotation == 270 and res.is_vertical
    assert res.fps == "30000/1001"
    assert res.nb_frames is None and res.has_audio is False


def test_probe_detects_corruption_by_decoding_everything(
    defective_dir: Path, fixtures_dir: Path
) -> None:
    bad = probe_file(defective_dir / "corrupto.mp4")
    assert any(w.startswith(CORRUPTION_PREFIX) for w in bad.warnings)
    assert has_corruption(bad)
    good = probe_file(fixtures_dir / "base_1080x1920_30.mp4")
    assert not has_corruption(good)


def test_make_warnings_is_empty_for_a_good_vertical_video() -> None:
    res = ProbeResult(
        duration_s=5, width=1080, height=1920, fps="30/1", has_audio=True,
        video_codec="h264", pix_fmt="yuv420p",
    )  # fmt: skip
    assert make_warnings(res) == []


def test_cli_probe_ok_and_warnings(fixtures_dir: Path, projects_dir: Path) -> None:
    ctx = _project(fixtures_dir / "base_720x1280_25.mp4", "lowres")
    res = runner.invoke(app, ["probe", "lowres"])
    assert res.exit_code == 0, res.output
    assert "AVISO" in res.output and "720" in res.output
    assert ctx.analysis("probe.json").exists()


def test_cli_probe_fails_for_corrupt_file_but_still_writes_json(
    defective_dir: Path, projects_dir: Path
) -> None:
    ctx = _project(defective_dir / "corrupto.mp4", "danado")
    res = runner.invoke(app, ["probe", "danado"])
    assert res.exit_code == 1
    assert "dañado" in res.output
    assert ctx.analysis("probe.json").exists()


def test_cli_probe_unknown_project(projects_dir: Path) -> None:
    res = runner.invoke(app, ["probe", "nope"])
    assert res.exit_code == 1
    assert "No existe el proyecto" in " ".join(res.output.split())
