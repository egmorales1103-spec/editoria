"""render_plan_graphics + the `graphics` CLI (list / preview / render)."""

from __future__ import annotations

import json
from fractions import Fraction
from pathlib import Path

import pytest
from typer.testing import CliRunner

from editoria.cli import app
from editoria.graphics import (
    GraphicsError,
    PlaywrightGraphicsRenderer,
    list_templates,
    render_plan_graphics,
)
from editoria.schemas import (
    CaptionsSpec,
    EditPlan,
    GraphicItem,
    OverlayClip,
    write_model,
)
from editoria.util import ffmpeg
from editoria.util.geometry import zone_box
from editoria.util.project import DELIVERED_MARKER, PLAN_FILE, ProjectContext

runner = CliRunner()


def _plan() -> EditPlan:
    return EditPlan(
        version="V1",
        style="B",
        brand="master-solution",
        captions=CaptionsSpec(style="B"),
        graphics=[
            GraphicItem.model_validate(
                {
                    "id": "g01",
                    "template": "palabra_clave",
                    "in": 0.3,
                    "out": 1.1,
                    "zone": "upper",
                    "params": {"texto": "Automatizá"},
                }
            ),
            GraphicItem.model_validate(
                {
                    "id": "g02",
                    "template": "dato_grafico",
                    "in": 2.0,
                    "out": 2.5,
                    "zone": "middle",
                    "params": {
                        "tipo": "barras",
                        "valores": [40, 75],
                        "etiquetas": ["Antes", "Después"],
                        "data_source": "ejemplo",
                    },
                }
            ),
            GraphicItem.model_validate({"id": "e01", "emoji": "E01", "in": 3.0, "out": 4.0}),
        ],
    )


@pytest.fixture
def project_v1(fixture_project: ProjectContext) -> ProjectContext:
    write_model(fixture_project.version_dir("V1") / PLAN_FILE, _plan())
    return fixture_project


def test_render_plan_graphics(project_v1: ProjectContext) -> None:
    with PlaywrightGraphicsRenderer() as r:
        clips = render_plan_graphics(project_v1, "V1", renderer=r)
    assert [c.id for c in clips] == ["g01", "g02"]  # emojis are left to the lead
    gdir = project_v1.version_dir("V1") / "graficos"
    assert len(list((gdir / "g01").glob("*.png"))) == clips[0].frame_count == 24
    assert len(list((gdir / "g02").glob("*.png"))) == clips[1].frame_count == 15
    assert clips[1].labels == ["Ejemplo"]
    plan = _plan()
    box = zone_box("upper", plan.canvas, 880, 260)
    assert (clips[0].x, clips[0].y) == (box.x, box.y)

    data = json.loads((gdir / "overlays.json").read_text(encoding="utf-8"))
    loaded = [OverlayClip.model_validate(o) for o in data["overlays"]]
    assert loaded == clips
    assert Path(loaded[0].frames_pattern) == gdir / "g01" / "%05d.png"


def test_render_plan_refuses_delivered_version(project_v1: ProjectContext) -> None:
    (project_v1.version_dir("V1") / DELIVERED_MARKER).write_text("", encoding="utf-8")
    with pytest.raises(GraphicsError, match="entregada"):
        render_plan_graphics(project_v1, "V1")


def test_cli_list() -> None:
    res = runner.invoke(app, ["graphics", "list"], terminal_width=200)
    assert res.exit_code == 0, res.output
    for m in list_templates():
        assert m.id in res.output


def test_cli_preview(tmp_path: Path) -> None:
    out = tmp_path / "vista previa ñ"
    res = runner.invoke(
        app,
        [
            "graphics",
            "preview",
            "palabra_clave",
            "--params",
            '{"texto": "Hola"}',
            "--out",
            str(out),
        ],
        terminal_width=200,
    )
    assert res.exit_code == 0, res.output
    mp4 = out / "palabra_clave_preview.mp4"
    png = out / "palabra_clave_medio.png"
    assert png.is_file() and mp4.is_file()
    info = ffmpeg.probe(mp4)
    video = next(s for s in info["streams"] if s["codec_type"] == "video")
    assert (video["width"], video["height"]) == (1080, 1920)
    assert Fraction(video["r_frame_rate"]) == 30
    assert float(info["format"]["duration"]) == pytest.approx(1.8, abs=0.1)


def test_cli_preview_uses_example_params(tmp_path: Path) -> None:
    res = runner.invoke(
        app, ["graphics", "preview", "dato_grafico", "--out", str(tmp_path), "--duracion", "0.3"]
    )
    assert res.exit_code == 0, res.output
    assert "Ejemplo" in res.output


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["graphics", "preview", "palabra_clave", "--params", "{texto"], "no es un JSON válido"),
        (
            ["graphics", "preview", "palabra_clave", "--params", '{"texto": 3}'],
            "Parámetros inválidos",
        ),
        (["graphics", "preview", "no_existe"], "No existe la plantilla"),
        (["graphics", "preview", "palabra_clave", "--zona", "arriba"], "Zona inválida"),
    ],
)
def test_cli_preview_errors(args: list[str], message: str) -> None:
    res = runner.invoke(app, args, terminal_width=200)
    assert res.exit_code == 1
    assert message in " ".join(res.output.split())


def test_cli_render(project_v1: ProjectContext) -> None:
    res = runner.invoke(app, ["graphics", "render", "demo", "--version", "V1"], terminal_width=200)
    assert res.exit_code == 0, res.output
    assert "2 gráfico(s)" in res.output
    assert (project_v1.version_dir("V1") / "graficos" / "overlays.json").is_file()
    again = runner.invoke(
        app, ["graphics", "render", "demo", "--version", "V1"], terminal_width=200
    )
    assert again.exit_code == 0 and "caché" in again.output


@pytest.mark.usefixtures("no_chromium")
def test_cli_render_without_chromium(project_v1: ProjectContext) -> None:
    res = runner.invoke(app, ["graphics", "render", "demo"], terminal_width=200)
    assert res.exit_code == 2
    assert "playwright install chromium" in " ".join(res.output.split())


def test_cli_render_unknown_project(projects_dir: Path) -> None:
    res = runner.invoke(app, ["graphics", "render", "nada"], terminal_width=200)
    assert res.exit_code == 1 and "No existe el proyecto" in " ".join(res.output.split())
