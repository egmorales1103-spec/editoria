from __future__ import annotations

import pytest

from editoria.schemas import REGISTRO_COLUMNS
from editoria.shots import ShotError, pack_shot
from editoria.shots.prompts import NEGATIVE_CONSTRAINTS
from editoria.util import ffmpeg
from editoria.util.files import read_csv_rows
from editoria.util.project import ProjectContext

SEG_IN, SEG_OUT = 8.5, 10.5


def test_pack_creates_everything(packed, fixtures_dir):  # type: ignore[no-untyped-def]
    ctx, meta = packed
    pdir = ctx.shots_packs_dir / "G01"
    assert meta.id == "G01" and meta.attempt == 1
    for name in (
        "segmento.mp4",
        "ancla_inicio.png",
        "ancla_medio.png",
        "ancla_fin.png",
        "prompt.txt",
        "pack.md",
        "meta.json",
    ):
        assert (pdir / name).is_file(), name

    info = ffmpeg.probe(pdir / "segmento.mp4")
    video = next(s for s in info["streams"] if s["codec_type"] == "video")
    assert (video["width"], video["height"]) == (1080, 1920)
    assert float(info["format"]["duration"]) == pytest.approx(SEG_OUT - SEG_IN, abs=0.1)

    first_line = ctx.generations_registry.read_text(encoding="utf-8").splitlines()[0]
    assert tuple(first_line.split(",")) == REGISTRO_COLUMNS
    rows = read_csv_rows(ctx.generations_registry)
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == "G01" and row["veredicto"] == "pendiente"
    assert row["entrada"] == "8.5" and row["salida"] == "10.5"
    assert row["archivo_origen"] == "00_original/video_base.mp4"
    assert "acercamiento suave del 10 %" in row["prompt"]
    assert row["costo_mostrado"] == "" and row["funcion_modelo_real"] == ""

    prompt = (pdir / "prompt.txt").read_text(encoding="utf-8")
    assert "Requested change: acercamiento suave del 10 %." in prompt
    assert NEGATIVE_CONSTRAINTS in prompt


def test_pack_md_without_limits_says_verify(packed):  # type: ignore[no-untyped-def]
    ctx, _ = packed
    md = (ctx.shots_packs_dir / "G01" / "pack.md").read_text(encoding="utf-8")
    assert "verificar en la herramienta" in md
    assert "SIN LÍMITE AUTORIZADO" in md
    assert "Pasos manuales" in md and "editoria shots import demo G01" in md


def test_pack_md_uses_project_limits(fixture_project: ProjectContext, set_config):  # type: ignore[no-untyped-def]
    set_config(
        fixture_project,
        tool_limits={"higgsfield_max_clip_s": 5.0, "max_attempts": 3},
        budget={"unit": "creditos", "limit": 40.0, "spent": 0.0},
    )
    pack_shot(fixture_project, 1.0, 3.0, "plano un poco más cerrado")
    md = (fixture_project.shots_packs_dir / "G01" / "pack.md").read_text(encoding="utf-8")
    assert "5 s (de proyecto.yaml)" in md
    assert "3 (de proyecto.yaml)" in md
    assert "límite 40 creditos" in md


def test_pack_ids_increment_and_clip_limit(fixture_project: ProjectContext, set_config):  # type: ignore[no-untyped-def]
    set_config(fixture_project, tool_limits={"higgsfield_max_clip_s": 3.0, "max_attempts": None})
    a = pack_shot(fixture_project, 0.5, 2.0, "encuadre más cerrado")
    b = pack_shot(fixture_project, 2.5, 4.0, "encuadre más cerrado")
    assert (a.id, b.id) == ("G01", "G02")
    with pytest.raises(ShotError, match="límite de la herramienta"):
        pack_shot(fixture_project, 0.0, 5.0, "encuadre")


@pytest.mark.parametrize(("a", "b"), [(-1.0, 2.0), (3.0, 3.05), (11.0, 13.0)])
def test_pack_rejects_bad_segment(fixture_project: ProjectContext, a: float, b: float):
    with pytest.raises(ShotError):
        pack_shot(fixture_project, a, b, "encuadre")


def test_pack_requires_change(fixture_project: ProjectContext):
    with pytest.raises(ShotError, match="--cambio"):
        pack_shot(fixture_project, 1.0, 2.0, "   ")


def test_pack_retry_requires_reintentar_verdict(packed):  # type: ignore[no-untyped-def]
    ctx, _ = packed
    with pytest.raises(ShotError, match="reintentar"):
        pack_shot(ctx, SEG_IN, SEG_OUT, "otro intento", retry_of="G01")
