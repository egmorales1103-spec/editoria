"""audio mix never writes into a delivered version (CLI and Python entry point)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from editoria.audio import mix_for_version
from editoria.cli import app
from editoria.util.project import DELIVERED_MARKER, PLAN_FILE, ProjectContext

runner = CliRunner()


def test_mix_refuses_delivered_version(fixture_project: ProjectContext, fixtures_dir: Path) -> None:
    vdir = fixture_project.version_dir("V1")
    vdir.mkdir(parents=True)
    shutil.copy2(fixtures_dir / "plan_fixture.yaml", vdir / PLAN_FILE)
    (vdir / DELIVERED_MARKER).write_text("V1", encoding="utf-8")

    with pytest.raises(PermissionError, match="entregada"):
        mix_for_version(fixture_project, "V1")
    res = runner.invoke(app, ["audio", "mix", fixture_project.slug, "--version", "V1"])
    assert res.exit_code == 1
    assert "entregada" in res.output and "inmutable" in res.output
    assert not (vdir / "audio").exists()


def test_mix_invalid_version_is_spanish_error(fixture_project: ProjectContext) -> None:
    res = runner.invoke(app, ["audio", "mix", fixture_project.slug, "--version", "v-uno"])
    assert res.exit_code == 1 and "Versión inválida" in res.output
