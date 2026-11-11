"""End to end on synthetic fixtures: init -> ... -> deliver (G2)."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from editoria.cli import app
from editoria.schemas import QCReport, read_model
from editoria.util.files import sha256_file
from editoria.util.project import DELIVERED_MARKER, ProjectContext

pytestmark = pytest.mark.e2e
runner = CliRunner()


def _ok(args: list[str]) -> str:
    res = runner.invoke(app, args, catch_exceptions=False)
    assert res.exit_code == 0, f"{args}: {res.output}"
    return res.output


def _assert_v1_package(ctx: ProjectContext) -> None:
    v1 = ctx.version_dir("V1")
    for rel in (
        "video.mp4",
        "plan.yaml",
        "subtitulos.srt",
        "subtitulos.vtt",
        "subtitulos.ass",
        "qc/qc.json",
        "qc/qc.md",
        "resumen.md",
        "atribuciones.md",
        "mapa_edicion.csv",
        DELIVERED_MARKER,
    ):
        assert (v1 / rel).exists(), rel
    for sid in "ABC":
        assert (ctx.proposals_dir / f"muestra_{sid}.mp4").exists()
        assert (ctx.proposals_dir / f"plan_{sid}.yaml").exists()
    assert (ctx.proposals_dir / "comparativa_ABC.mp4").exists()
    assert (ctx.proposals_dir / "propuestas.md").exists()
    qc = read_model(v1 / "qc" / "qc.json", QCReport)
    assert not qc.has_fail, [c for c in qc.checks if c.status == "FAIL"]
    assert any(c.status == "HUMAN" for c in qc.checks)
    cfg = ctx.load_config()
    assert sha256_file(ctx.original_video()) == cfg.original_sha256
    resumen = (v1 / "resumen.md").read_text(encoding="utf-8")
    assert "¿Qué querés ajustar" in resumen


def test_run_end_to_end(
    base_video: Path, projects_dir: Path, monkeypatch: pytest.MonkeyPatch, fixtures_dir: Path
) -> None:
    monkeypatch.setenv("EDITORIA_TRANSCRIPT_FIXTURE", str(fixtures_dir / "transcript_fixture.json"))
    _ok(["init", str(base_video), "--slug", "e2e", "--brand", "master-solution"])
    out = _ok(["run", "e2e", "--backend", "fixture"])
    assert "V1 entregada" in out
    ctx = ProjectContext.open("e2e")
    _assert_v1_package(ctx)
    # run never continues past V1
    out2 = _ok(["run", "e2e", "--backend", "fixture"])
    assert "feedback" in out2.lower()
    assert ctx.versions() == ["V1"]


def test_step_by_step_with_spaces_and_accents(
    spaced_video: Path, projects_dir: Path, monkeypatch: pytest.MonkeyPatch, fixtures_dir: Path
) -> None:
    monkeypatch.setenv("EDITORIA_TRANSCRIPT_FIXTURE", str(fixtures_dir / "transcript_fixture.json"))
    _ok(["init", str(spaced_video), "--slug", "con-espacios"])
    _ok(["probe", "con-espacios"])
    _ok(["transcribe", "con-espacios", "--backend", "fixture"])
    _ok(["analyze", "con-espacios"])
    _ok(["propose", "con-espacios"])
    ctx = ProjectContext.open("con-espacios")
    _ok(
        [
            "plan",
            "draft",
            "con-espacios",
            "--style",
            "A",
            "--out",
            str(ctx.version_dir("V1") / "plan.yaml"),
        ]
    )
    _ok(["plan", "lint", "con-espacios", "--version", "V1"])
    _ok(["render", "con-espacios", "--version", "V1"])
    _ok(["contact-sheet", "con-espacios", "--version", "V1"])
    _ok(["deliver", "con-espacios", "--version", "V1"])
    _assert_v1_package(ctx)
    # delivered versions are immutable
    res = runner.invoke(app, ["render", "con-espacios", "--version", "V1"])
    assert res.exit_code != 0
