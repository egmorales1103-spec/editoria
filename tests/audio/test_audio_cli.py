"""audio sfx / mix / check-voice through the root CLI."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from editoria.cli import app
from editoria.util import ffmpeg, log
from editoria.util.project import ProjectContext

runner = CliRunner()


@pytest.fixture(autouse=True)
def wide_console(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(log.console, "_width", 220, raising=False)
    monkeypatch.setattr(log.console, "_height", 60, raising=False)


def test_audio_sfx_lists_licences() -> None:
    res = runner.invoke(app, ["audio", "sfx"])
    assert res.exit_code == 0, res.output
    assert "CC0-1.0" in res.output
    assert "impacto_suave_3" in res.output and "teclado_2" in res.output
    assert "EditorIA contributors" in res.output
    assert "FALTA" not in res.output


def test_audio_mix_and_check_voice(fixture_project: ProjectContext, fixtures_dir: Path) -> None:
    ctx = fixture_project
    vdir = ctx.version_dir("V1")
    vdir.mkdir(parents=True)
    shutil.copy2(fixtures_dir / "plan_fixture.yaml", vdir / "plan.yaml")

    res = runner.invoke(app, ["audio", "mix", ctx.slug, "--version", "V1"])
    assert res.exit_code == 0, res.output
    assert "LUFS" in res.output and "dBTP" in res.output
    wav = vdir / "audio" / "mezcla.wav"
    assert wav.exists() and (vdir / "audio" / "mezcla.json").exists()

    ok = runner.invoke(app, ["audio", "check-voice", ctx.slug, str(wav)])
    assert ok.exit_code == 0, ok.output
    assert "Desfase" in ok.output

    late = vdir / "audio" / "retrasada ñ.wav"
    ffmpeg.run(["-i", str(wav), "-af", "adelay=200:all=1", str(late)])
    bad = runner.invoke(app, ["audio", "check-voice", ctx.slug, str(late)])
    assert bad.exit_code == 1
    assert "+200" in bad.output or "200." in bad.output


def test_audio_mix_unknown_project_is_spanish_error(projects_dir: Path) -> None:
    res = runner.invoke(app, ["audio", "mix", "no-existe"])
    assert res.exit_code == 1
    assert "No existe el proyecto" in res.output


def test_audio_check_voice_missing_file(fixture_project: ProjectContext, tmp_path: Path) -> None:
    res = runner.invoke(
        app, ["audio", "check-voice", fixture_project.slug, str(tmp_path / "x.mp4")]
    )
    assert res.exit_code == 1
    assert "No existe el archivo" in res.output
