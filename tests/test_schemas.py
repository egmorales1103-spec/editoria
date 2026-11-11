from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from editoria.schemas import (
    REGISTRO_COLUMNS,
    Box,
    Canvas,
    EditPlan,
    GraphicItem,
    ProjectConfig,
    QCCheck,
    QCReport,
    VideoInterval,
    parse_fps,
    read_model,
    write_model,
)
from editoria.schemas.export import export_all
from editoria.util.files import read_csv_rows
from editoria.util.resources import doc_templates_dir, load_brand, load_style

PLAN_NORMATIVE = """
schema: editoria/plan@1
version: V1
style: A
brand: master-solution
canvas: {width: 1080, height: 1920, fps: source}
video:
  - {id: v01, in: 0.00, out: 2.40, method: original}
  - {id: v02, in: 2.40, out: 4.10, method: reframe, zoom: 1.15, anchor: face, motion: cut}
  - {id: v03, in: 9.80, out: 12.30, method: generated, shot: G01}
captions:
  style: A
  emphasis: [{word: 14}, {word: 37, color: accent}]
  editorial_titles: []
graphics:
  - {id: g01, template: palabra_clave, in: 0.30, out: 2.10, zone: upper, params: {texto: "Automatizá"}}
  - {id: g02, template: dato_grafico, in: 14.0, out: 17.5, zone: middle,
     params: {tipo: barras, valores: [40, 75], etiquetas: ["Antes", "Después"], data_source: ejemplo}}
  - {id: e01, emoji: E01, in: 6.2, out: 7.4, zone: upper_right}
sfx:
  - {cue: pop, at: 0.30, gain_db: -14, ref: g01}
  - {cue: whoosh, at: 2.38, gain_db: -16, ref: v02}
music: null
mix: {target_lufs: -14, true_peak_db: -1.0, duck_db: -10}
notes: "Propuesta A recomendada porque…"
"""


def test_normative_plan_parses_and_roundtrips(tmp_path: Path) -> None:
    p = tmp_path / "plan.yaml"
    p.write_text(PLAN_NORMATIVE, encoding="utf-8")
    plan = read_model(p, EditPlan)
    assert plan.video[1].in_ == 2.4
    assert plan.graphics[2].is_emoji
    out = write_model(tmp_path / "again.yaml", plan)
    text = out.read_text(encoding="utf-8")
    assert "in: 2.4" in text and "schema: editoria/plan@1" in text
    assert read_model(out, EditPlan) == plan


def test_plan_rejects_unknown_keys_and_bad_intervals() -> None:
    with pytest.raises(ValidationError):
        VideoInterval.model_validate({"id": "x", "in": 2, "out": 1, "method": "original"})
    with pytest.raises(ValidationError):
        VideoInterval.model_validate({"id": "x", "in": 0, "out": 1, "method": "generated"})
    with pytest.raises(ValidationError):
        GraphicItem.model_validate({"id": "g", "in": 0, "out": 1})
    with pytest.raises(ValidationError):
        GraphicItem.model_validate({"id": "g", "template": "t", "emoji": "E01", "in": 0, "out": 1})
    with pytest.raises(ValidationError):
        EditPlan.model_validate(
            {"version": "V1", "style": "A", "brand": "x", "captions": {"style": "A"}, "foo": 1}
        )


def test_canvas_fps_and_safe_box() -> None:
    c = Canvas(fps="30000/1001")
    assert c.fps == "30000/1001"
    assert Canvas().resolve_fps("25/1") == parse_fps(25)
    sb = Canvas().safe_box()
    assert (sb.x, sb.y, sb.w, sb.h) == (60, 220, 880, 1280)
    assert Box(x=0, y=0, w=10, h=10).intersects(Box(x=5, y=5, w=10, h=10))


def test_project_config_and_qc(tmp_path: Path) -> None:
    cfg = ProjectConfig(slug="mi-video")
    p = write_model(tmp_path / "proyecto.yaml", cfg)
    assert read_model(p, ProjectConfig).budget.limit is None
    with pytest.raises(ValidationError):
        ProjectConfig(slug="Con Espacios")
    rep = QCReport(version="V1", checks=[QCCheck(id="x", prompt_question="q", status="FAIL")])
    assert rep.has_fail and rep.counts()["FAIL"] == 1


def test_resources_are_valid() -> None:
    for sid in "ABC":
        st = load_style(sid)
        assert st.id == sid
        assert st.editorial_titles is not None
    for slug in ("master-solution", "_plantilla"):
        assert load_brand(slug).provisional


def test_registry_columns_match_kit_template() -> None:
    header = (doc_templates_dir() / "Registro_Generaciones.csv").read_text("utf-8").splitlines()[0]
    assert tuple(header.split(",")) == REGISTRO_COLUMNS
    assert read_csv_rows(doc_templates_dir() / "Mapa_Edicion.csv") == []


def test_json_schema_export(tmp_path: Path) -> None:
    files = export_all(tmp_path)
    assert any(f.name == "plan.schema.json" for f in files)
