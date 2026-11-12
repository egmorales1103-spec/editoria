"""Long text shrinks to fit the template box instead of being cut.

Regression: with the longest content a schema allows, chat_burbujas, checklist, titulo_gancho
and dato_grafico overflowed their box (text cut at the top/bottom, labels overlapping, a bar
pushed out of the image). They now scale their type with ``--k`` until the content fits.
"""

from __future__ import annotations

import hashlib
import io
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from editoria.graphics import PlaywrightGraphicsRenderer, list_templates, load_template
from editoria.graphics.preview import FRAME_START
from editoria.graphics.renderer import _INIT_JS, _SEEK_JS
from editoria.schemas import BrandProfile, Canvas

FPS = Fraction(30)
OPAQUE = 200  # cards and text; shadows peak around 90
TAIL = 2  # invisible gaussian shadow tail
MIN_K = 0.6  # below this the type would be too small to read on a phone
FITTING = ["chat_burbujas", "checklist", "titulo_gancho", "dato_grafico"]
POOL = [
    "Automatización",
    "de",
    "procesos",
    "administrativos",
    "para",
    "equipos",
    "pequeños",
    "que",
    "quieren",
    "comunicación",
    "clara,",
    "configuración",
    "sencilla",
    "y",
    "seguimiento",
    "constante",
    "de",
    "clientes",
]


def words(limit: int) -> str:
    """Real-looking text filling as much of ``limit`` characters as possible."""
    out, i = "", 0
    while len(cand := (out + " " + POOL[i % len(POOL)]).strip()) <= limit:
        out, i = cand, i + 1
    return out


def worst(schema: dict[str, Any]) -> Any:
    if "enum" in schema:
        return schema["enum"][0]
    kind = schema.get("type")
    if kind == "string":
        return words(schema.get("maxLength", 40))
    if kind == "number":
        return schema.get("maximum", 100)
    if kind == "array":
        return [worst(schema["items"]) for _ in range(schema.get("maxItems", 3))]
    if kind == "object":
        return {k: worst(v) for k, v in schema["properties"].items()}
    raise AssertionError(f"tipo de esquema sin caso máximo: {schema}")


def worst_params(template_id: str) -> dict[str, Any]:
    props = load_template(template_id).schema["properties"]
    params = {k: worst(v) for k, v in props.items() if k not in ("x", "y")}
    if "x" in props:
        params.update(x=0.5, y=0.4)
    if "valores" in params:
        params["valores"] = [95, 80, 65, 50, 35, 20][: len(params["valores"])]
    if "data_source" in props:
        params["data_source"] = "ejemplo"
    return params


# Extra extremes the generic generator cannot express (numbers have no schema maximum and the
# counter type allows at most 3 values).
EXTRA: dict[str, dict[str, Any]] = {
    "dato_grafico: barras con 5 cifras": {
        "tipo": "barras",
        "valores": [12500, 9800, 7300, 5100, 3200, 1100],
        "etiquetas": [words(22)] * 6,
        "unidad": "u",
        "data_source": "ejemplo",
    },
    "dato_grafico: contador de 7 cifras": {
        "tipo": "contador",
        "valores": [1250000, 3400000, 9100000],
        "etiquetas": ["Clientes", "Pedidos", "Tickets"],
        "titulo": words(40),
        "data_source": "ejemplo",
    },
}


def _late_frame(
    r: PlaywrightGraphicsRenderer, brand: BrandProfile, template_id: str, params: dict[str, Any]
) -> tuple[Image.Image, dict[str, Any] | None]:
    """Frame after every entrance animation (before the exit), plus the fit result."""
    template = load_template(template_id)
    params = template.validate(params)
    placement = r.place(template, params, Canvas(), template.meta.zonas[0])
    dur = template.meta.duracion_s
    html, _ = r.build_html(template, params, brand, dur, placement.anchor)
    context = r.browser().new_context(
        viewport={"width": template.meta.box_width, "height": template.meta.box_height}
    )
    try:
        page = context.new_page()
        page.set_content(html, wait_until="load")
        page.evaluate("() => document.fonts.ready")
        page.evaluate(_INIT_JS)
        fit = page.evaluate("() => window.__editoriaFitResult || null")
        page.evaluate(_SEEK_JS, (dur - 0.52) * 1000)
        png = page.screenshot(omit_background=True, type="png")
    finally:
        context.close()
    return Image.open(io.BytesIO(png)).convert("RGBA"), fit


def _assert_inside_visible_area(im: Image.Image, bleed: int, label: str) -> None:
    solid = im.getchannel("A").point(lambda v: 255 if v >= OPAQUE else 0).getbbox()
    assert solid is not None, label
    left, top, right, bottom = solid
    over = {
        "izquierda": bleed - left,
        "arriba": bleed - top,
        "derecha": right - (im.width - bleed),
        "abajo": bottom - (im.height - bleed),
    }
    over = {k: v for k, v in over.items() if v > 1}
    assert not over, f"{label}: el contenido sobresale de su caja (px): {over}"
    a = im.getchannel("A")
    w, h = a.size
    px = a.load()
    assert px is not None
    edge = max(
        max(px[x, 0] for x in range(w)),
        max(px[x, h - 1] for x in range(w)),
        max(px[0, y] for y in range(h)),
        max(px[w - 1, y] for y in range(h)),
    )
    assert edge <= TAIL, f"{label}: contenido o sombra cortados en el borde de la imagen ({edge})"


CASES = [(m.id, "máximo del esquema", worst_params(m.id)) for m in list_templates()]
CASES += [(name.split(":")[0], name, params) for name, params in EXTRA.items()]


@pytest.mark.parametrize(
    ("template_id", "label", "params"), CASES, ids=[c[1] + c[0] for c in CASES]
)
def test_longest_content_fits_inside_the_box(
    template_id: str,
    label: str,
    params: dict[str, Any],
    renderer: PlaywrightGraphicsRenderer,
    brand: BrandProfile,
) -> None:
    bleed = load_template(template_id).meta.bleed
    im, fit = _late_frame(renderer, brand, template_id, params)
    _assert_inside_visible_area(im, bleed, f"{template_id} ({label})")
    if fit is not None:
        assert fit["fits"], f"{template_id} ({label}): ni con la letra más chica entra: {fit}"
        assert fit["k"] >= MIN_K, f"{template_id} ({label}): letra demasiado chica (x{fit['k']})"


@pytest.mark.parametrize("template_id", FITTING)
def test_example_params_keep_the_design_size(
    template_id: str, renderer: PlaywrightGraphicsRenderer, brand: BrandProfile
) -> None:
    """Normal content is not touched: the fit only acts when something would overflow."""
    params = load_template(template_id).example_params()
    _, fit = _late_frame(renderer, brand, template_id, params)
    assert fit == {"k": 1, "fits": True}


@pytest.mark.parametrize("template_id", FITTING)
def test_long_content_really_shrinks_the_type(
    template_id: str, renderer: PlaywrightGraphicsRenderer, brand: BrandProfile
) -> None:
    """The long case must trigger the fit: guards against a test that passes by accident."""
    if template_id == "dato_grafico":
        params = EXTRA["dato_grafico: contador de 7 cifras"]
    else:
        params = worst_params(template_id)
    _, fit = _late_frame(renderer, brand, template_id, params)
    assert fit is not None
    assert fit["k"] < 1


def test_fit_is_deterministic(
    renderer: PlaywrightGraphicsRenderer, brand: BrandProfile, tmp_path: Path
) -> None:
    hashes = []
    for run in ("a", "b"):
        out = tmp_path / run
        clip = renderer.render_template(
            "chat_burbujas",
            worst_params("chat_burbujas"),
            brand=brand,
            canvas=Canvas(),
            fps=FPS,
            out_dir=out,
        )
        mid = FRAME_START + clip.frame_count // 2
        hashes.append(hashlib.sha256((out / f"{mid:05d}.png").read_bytes()).hexdigest())
    assert hashes[0] == hashes[1]


def test_content_that_cannot_fit_warns(
    brand: BrandProfile, canvas: Canvas, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "plantillas"
    root.mkdir()
    (root / "_base.html").write_text(
        (Path(__file__).resolve().parents[2] / "templates" / "graphics" / "_base.html").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    folder = root / "gigante"
    folder.mkdir()
    (folder / "template.html").write_text(
        "\n".join(
            [
                '{% extends "_base.html" %}',
                '{% block body %}<div class="panel" style="width:100%;height:5000px"></div>{% endblock %}',
                "{% block script %}<script>window.editoriaFit = () =>",
                " window.editoriaFitTo({target: '.panel'});</script>{% endblock %}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (folder / "params.schema.json").write_text(
        '{"type": "object", "additionalProperties": false, "properties": {}}', encoding="utf-8"
    )
    (folder / "meta.yaml").write_text(
        "\n".join(
            [
                "id: gigante",
                "nombre: Prueba",
                "size: [200, 100]",
                "duracion_s: 0.2",
                "zonas: [center]",
                "",
            ]
        ),
        encoding="utf-8",
    )
    with PlaywrightGraphicsRenderer(root, use_cache=False) as r:
        r.render_template(
            "gigante", {}, brand=brand, canvas=canvas, fps=FPS, out_dir=tmp_path / "o"
        )
    err = " ".join(capsys.readouterr().err.split())
    assert "no entra en su caja" in err and "gigante" in err
