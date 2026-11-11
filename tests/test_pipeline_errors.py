"""Pipeline guards give Spanish, actionable errors instead of tracebacks (R2 review)."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from editoria.cli import app
from editoria.pipeline import parse_window

runner = CliRunner()


def test_propose_without_analysis_is_a_clean_error(base_video: Path, projects_dir: Path) -> None:
    assert runner.invoke(app, ["init", str(base_video), "--slug", "sin-analisis"]).exit_code == 0
    res = runner.invoke(app, ["propose", "sin-analisis"])
    assert res.exit_code == 1
    assert "editoria probe" in res.output and "Traceback" not in res.output


def test_run_without_audio_is_a_clean_error(fixtures_dir: Path, projects_dir: Path) -> None:
    video = fixtures_dir / "sin_audio.mp4"
    assert runner.invoke(app, ["init", str(video), "--slug", "mudo"]).exit_code == 0
    res = runner.invoke(app, ["run", "mudo", "--backend", "fixture"])
    assert res.exit_code == 1
    assert "no tiene pista de audio" in res.output


def test_parse_window() -> None:
    assert parse_window("2-9") == (2.0, 9.0)
    assert parse_window(None) is None
