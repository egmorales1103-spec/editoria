"""Template library contract (no browser needed)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

from editoria.graphics import (
    GraphicsParamsError,
    TemplateNotFound,
    list_templates,
    load_template,
)
from editoria.graphics.fonts import build_font_css, find_font_files
from editoria.schemas import Zone
from editoria.util import resources

REQUIRED = {
    "titulo_gancho",
    "palabra_clave",
    "checklist",
    "chat_burbujas",
    "notificacion",
    "dato_grafico",
    "anotacion",
    "comparacion",
}
OPTIONAL = {"ui_demo", "cta_cierre"}
FORBIDDEN_JS = re.compile(r"\b(setTimeout|setInterval|requestAnimationFrame|requestIdleCallback)\b")
REMOTE_URL = re.compile(
    r"""(?:src|href)\s*=\s*["']?\s*(?:https?:)?//|url\(\s*["']?\s*(?:https?:)?//"""
)

ROOT = resources.graphics_templates_dir()
ALL_HTML = sorted(ROOT.rglob("*.html"))


def test_library_has_required_templates() -> None:
    ids = {m.id for m in list_templates()}
    assert ids >= REQUIRED
    assert ids <= REQUIRED | OPTIONAL


@pytest.mark.parametrize("template_id", sorted(REQUIRED | OPTIONAL))
def test_template_folder_contract(template_id: str) -> None:
    folder = ROOT / template_id
    for name in ("template.html", "params.schema.json", "meta.yaml"):
        assert (folder / name).is_file(), f"falta {name}"
    raw = yaml.safe_load((folder / "meta.yaml").read_text(encoding="utf-8"))
    for key in ("id", "nombre", "descripcion", "size", "duracion_s", "zonas", "sfx_sugerido"):
        assert key in raw, f"meta.yaml sin '{key}'"
    tpl = load_template(template_id)
    assert tpl.meta.id == template_id
    assert all(z in Zone.__args__ for z in tpl.meta.zonas)
    schema = json.loads((folder / "params.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    assert schema.get("additionalProperties") is False
    assert schema.get("examples"), "params.schema.json necesita 'examples' (params de ejemplo)"
    tpl.validate(tpl.example_params())  # examples must be valid


@pytest.mark.parametrize("path", ALL_HTML, ids=lambda p: p.parent.name + "/" + p.name)
def test_no_timers_or_raf(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert not FORBIDDEN_JS.search(text), f"{path}: solo CSS/WAAPI; timers y rAF prohibidos"


@pytest.mark.parametrize("path", ALL_HTML, ids=lambda p: p.parent.name + "/" + p.name)
def test_no_remote_resources(path: Path) -> None:
    assert not REMOTE_URL.search(path.read_text(encoding="utf-8")), f"{path}: recurso remoto"


def test_forbidden_js_scan_catches_offenders() -> None:
    assert FORBIDDEN_JS.search("window.requestAnimationFrame(step)")
    assert FORBIDDEN_JS.search("setTimeout(() => x(), 10)")
    assert not FORBIDDEN_JS.search("animation: fade 1s; // no timers here")


def test_invalid_params_give_clear_spanish_error() -> None:
    tpl = load_template("checklist")
    with pytest.raises(GraphicsParamsError) as exc:
        tpl.validate({"items": []})
    msg = str(exc.value)
    assert "Parámetros inválidos para la plantilla 'checklist'" in msg
    assert "items" in msg and "al menos 1" in msg

    with pytest.raises(GraphicsParamsError, match="falta el parámetro obligatorio 'texto'"):
        load_template("palabra_clave").validate({})
    with pytest.raises(GraphicsParamsError, match="parámetro desconocido"):
        load_template("palabra_clave").validate({"texto": "Hola", "color": "rojo"})


def test_dato_grafico_requires_data_source() -> None:
    tpl = load_template("dato_grafico")
    with pytest.raises(GraphicsParamsError, match="data_source"):
        tpl.validate({"tipo": "barras", "valores": [1, 2]})
    with pytest.raises(GraphicsParamsError, match="no permitido"):
        tpl.validate({"tipo": "barras", "valores": [1], "data_source": "inventado"})
    with pytest.raises(GraphicsParamsError, match="como máximo 3"):
        tpl.validate({"tipo": "contador", "valores": [1, 2, 3, 4], "data_source": "real"})


def test_ui_demo_declares_mandatory_label() -> None:
    assert "Ilustración" in load_template("ui_demo").meta.etiquetas_obligatorias


def test_notificacion_has_no_third_party_brands() -> None:
    text = (ROOT / "notificacion" / "template.html").read_text(encoding="utf-8").lower()
    for brand in ("whatsapp", "instagram", "gmail", "slack", "telegram", "facebook", "apple"):
        assert brand not in text


def test_unknown_template_lists_available() -> None:
    with pytest.raises(TemplateNotFound, match=r"Disponibles: .*palabra_clave"):
        load_template("no_existe")
    with pytest.raises(TemplateNotFound):
        load_template("_base.html")


def test_font_lookup(tmp_path: Path) -> None:
    fonts = tmp_path / "fonts"
    (fonts / "Inter").mkdir(parents=True)
    (fonts / "Inter" / "Inter-Bold.ttf").write_bytes(b"fake")
    (fonts / "Inter" / "Inter-Regular.woff2").write_bytes(b"fake")
    (fonts / "InterDisplay-Bold.ttf").write_bytes(b"other family")
    found = {(f.path.name, f.weight) for f in find_font_files("Inter", fonts)}
    assert found == {("Inter-Bold.ttf", "700"), ("Inter-Regular.woff2", "400")}
    setup = build_font_css(["Inter"], fonts, quiet=True)
    assert setup.css.count("@font-face") == 2 and "data:font/truetype;base64" in setup.css
    assert setup.stacks["Inter"].startswith("'EditorIA Inter'")
    assert setup.missing == ()


def test_missing_font_falls_back_with_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    setup = build_font_css(["Fuente Inexistente"], tmp_path)
    assert setup.css == "" and setup.missing == ("Fuente Inexistente",)
    assert "sans-serif" in setup.stacks["Fuente Inexistente"]
    assert "fuente del sistema" in " ".join(capsys.readouterr().err.split())
