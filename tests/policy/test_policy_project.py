"""Linter against a real project folder: registry CSV, raw YAML validation and the CLI."""

from __future__ import annotations

import shutil
from pathlib import Path

import yaml
from typer.testing import CliRunner

from editoria.cli import app
from editoria.policy import has_errors, lint_file, lint_plan
from editoria.schemas import REGISTRO_COLUMNS, EditPlan, VideoInterval, read_model, write_model
from editoria.util.files import write_csv_rows
from editoria.util.project import PLAN_FILE, ProjectContext

runner = CliRunner()


def _fixture_plan(fixtures_dir: Path) -> EditPlan:
    return read_model(fixtures_dir / "plan_fixture.yaml", EditPlan)


def _registry(ctx: ProjectContext, verdict: str) -> None:
    row = dict.fromkeys(REGISTRO_COLUMNS, "")
    row.update(id="G01", veredicto=verdict, archivo_resultado="G01.mp4")
    write_csv_rows(ctx.generations_registry, REGISTRO_COLUMNS, [row])


def test_fixture_plan_lints_with_licensed_assets(
    project: ProjectContext, fixtures_dir: Path
) -> None:
    findings = lint_plan(_fixture_plan(fixtures_dir), project)
    assert not has_errors(findings), findings


def test_p05_reads_registry_csv(project: ProjectContext, fixtures_dir: Path) -> None:
    plan = _fixture_plan(fixtures_dir)
    plan.video[-1] = VideoInterval(id="v03", in_=4.0, out=8.5, method="original")
    plan.video.append(VideoInterval(id="v04", in_=8.5, out=10.5, method="generated", shot="G01"))
    plan.video.append(VideoInterval(id="v05", in_=10.5, out=12.0, method="original"))
    _registry(project, "pendiente")
    assert any(f.id == "P05" and f.severity == "ERROR" for f in lint_plan(plan, project))
    _registry(project, "aceptado")
    assert not any(f.id == "P05" for f in lint_plan(plan, project))


def test_lint_file_schema_errors(project: ProjectContext, tmp_path: Path) -> None:
    bad = tmp_path / "plan malo ñ.yaml"
    bad.write_text(
        yaml.safe_dump(
            {
                "schema": "editoria/plan@1",
                "version": "V1",
                "style": "A",
                "brand": "master-solution",
                "captions": {"style": "A"},
                "video": [{"id": "v01", "in": 3.0, "out": 1.0, "method": "original"}],
            }
        ),
        encoding="utf-8",
    )
    plan, findings = lint_file(bad, project)
    assert plan is None
    assert findings and all(f.id == "SCHEMA" and f.severity == "ERROR" for f in findings)
    assert any("out" in f.message for f in findings)
    missing_plan, missing = lint_file(tmp_path / "no.yaml", project)
    assert missing_plan is None and missing[0].id == "SCHEMA"


def test_cli_plan_lint_exit_codes(project: ProjectContext, fixtures_dir: Path) -> None:
    vdir = project.version_dir("V1")
    vdir.mkdir(parents=True)
    shutil.copy2(fixtures_dir / "plan_fixture.yaml", vdir / PLAN_FILE)
    res = runner.invoke(app, ["plan", "lint", "demo", "--version", "V1"], terminal_width=200)
    assert res.exit_code == 0, res.output

    plan = _fixture_plan(fixtures_dir)
    plan.video[1] = VideoInterval(id="v02", in_=2.4, out=4.0, method="reframe", zoom=1.4)
    bad = project.root / "plan_zoom.yaml"
    write_model(bad, plan)
    res = runner.invoke(app, ["plan", "lint", "demo", "--plan", str(bad)], terminal_width=200)
    assert res.exit_code != 0
    assert "P07" in res.output
