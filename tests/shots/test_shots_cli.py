from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from editoria.cli import app
from editoria.util.files import read_csv_rows
from editoria.util.project import ProjectContext

runner = CliRunner()


def _run(*args: str):  # type: ignore[no-untyped-def]
    return runner.invoke(app, ["shots", *args])


def test_cli_full_flow(fixture_project: ProjectContext, fixtures_dir: Path):
    ctx = fixture_project
    r = _run("pack", "demo", "--in", "8.5", "--out", "10.5", "--cambio", "acercamiento sutil")
    assert r.exit_code == 0, r.output
    assert "G01" in r.output

    r = _run("import", "demo", "G01", str(fixtures_dir / "generada_ok.mp4"), "--funcion", "prueba")
    assert r.exit_code == 0, r.output
    r = _run("compare", "demo", "G01")
    assert r.exit_code == 0, r.output
    assert "ESTABLE" in r.output
    r = _run("verdict", "demo", "G01", "aceptado", "--motivo", "revisado a mano")
    assert r.exit_code == 0, r.output
    assert read_csv_rows(ctx.generations_registry)[0]["veredicto"] == "aceptado"
    r = _run("list", "demo")
    assert "G01" in r.output and "aceptado" in r.output


def test_cli_errors_are_spanish_and_nonzero(fixture_project: ProjectContext, fixtures_dir: Path):
    r = _run("verdict", "demo", "G01", "aceptado", "--motivo", "x")
    assert r.exit_code == 1
    assert "No existe la toma" in r.output
    r = _run("pack", "demo", "--in", "1", "--out", "2", "--cambio", "x", "--reintento-de", "G05")
    assert r.exit_code == 1


def test_cli_budget(fixture_project: ProjectContext, set_config):  # type: ignore[no-untyped-def]
    r = _run("budget", "demo")
    assert r.exit_code == 0
    assert "Sin límite autorizado" in r.output
    set_config(fixture_project, budget={"unit": "creditos", "limit": 30.0, "spent": 0.0})
    r = _run("budget", "demo", "--registrar", "4.5", "--detalle", "G01")
    assert r.exit_code == 0, r.output
    assert "Límite: 30" in r.output and "Gastado: 4.5" in r.output and "Restante: 25.5" in r.output
