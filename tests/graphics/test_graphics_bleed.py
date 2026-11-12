"""Shadows are never cut at the image edge, and the comparison arrow never touches the text.

Regression for two visual defects found in review: card shadows ended in a hard vertical edge
(the cards filled the whole template box) and the arrow circle of ``comparacion`` touched the
"R" of "Reserva".
"""

from __future__ import annotations

import math
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
OPAQUE = 200  # card/text pixels; shadows peak around 90
TAIL = 2  # a gaussian shadow tail of 1-2/255 is invisible; a cut shadow measures 20+

# Longest comparison the schema allows (60 chars per side, 40 in the title), with real words.
WORST_COMPARISON = {
    "titulo": "Cómo agendamos una cita sin llamadas",
    "antes": "Llamadas, mensajes sueltos y una agenda en papel que nadie",
    "despues": "Reserva automática, recordatorio y confirmación al cliente",
}


def _middle_frame(
    r: PlaywrightGraphicsRenderer,
    brand: BrandProfile,
    template_id: str,
    params: dict[str, Any],
    out: Path,
    **kw: Any,
) -> Image.Image:
    clip = r.render_template(
        template_id, params, brand=brand, canvas=Canvas(), fps=FPS, out_dir=out, **kw
    )
    mid = FRAME_START + clip.frame_count // 2
    return Image.open(out / f"{mid:05d}.png").convert("RGBA")


def _border_alpha(im: Image.Image) -> dict[str, int]:
    a = im.getchannel("A")
    w, h = a.size
    px = a.load()
    assert px is not None
    return {
        "arriba": max(px[x, 0] for x in range(w)),
        "abajo": max(px[x, h - 1] for x in range(w)),
        "izquierda": max(px[0, y] for y in range(h)),
        "derecha": max(px[w - 1, y] for y in range(h)),
    }


@pytest.mark.parametrize("meta", list_templates(), ids=lambda m: m.id)
def test_example_params_leave_the_image_border_transparent(
    meta: Any, renderer: PlaywrightGraphicsRenderer, brand: BrandProfile, tmp_path: Path
) -> None:
    params = load_template(meta.id).example_params()
    im = _middle_frame(renderer, brand, meta.id, params, tmp_path)
    cut = {k: v for k, v in _border_alpha(im).items() if v > TAIL}
    assert not cut, f"{meta.id}: la sombra o el contenido llega al borde de la imagen: {cut}"


def test_longest_comparison_does_not_reach_the_border(
    renderer: PlaywrightGraphicsRenderer, brand: BrandProfile, tmp_path: Path
) -> None:
    im = _middle_frame(renderer, brand, "comparacion", WORST_COMPARISON, tmp_path)
    cut = {k: v for k, v in _border_alpha(im).items() if v > TAIL}
    assert not cut, f"comparacion: {cut}"


@pytest.mark.parametrize("point", [(0.1, 0.1), (0.9, 0.1), (0.1, 0.9), (0.9, 0.9), (0.5, 0.5)])
@pytest.mark.parametrize("tipo", ["flecha", "circulo"])
def test_annotation_label_and_shadow_stay_inside_the_box(
    point: tuple[float, float],
    tipo: str,
    renderer: PlaywrightGraphicsRenderer,
    brand: BrandProfile,
    tmp_path: Path,
) -> None:
    params = {"tipo": tipo, "x": point[0], "y": point[1], "texto": "Acá se configura"}
    im = _middle_frame(renderer, brand, "anotacion", params, tmp_path)
    cut = {k: v for k, v in _border_alpha(im).items() if v > TAIL}
    assert not cut, f"{tipo} en {point}: {cut}"


@pytest.mark.parametrize("meta", [m for m in list_templates() if m.bleed], ids=lambda m: m.id)
def test_opaque_content_stays_inside_the_visible_area(
    meta: Any, renderer: PlaywrightGraphicsRenderer, brand: BrandProfile, tmp_path: Path
) -> None:
    """Only shadows (low alpha) may enter the bleed margin: cards and text never do."""
    params = load_template(meta.id).example_params()
    im = _middle_frame(renderer, brand, meta.id, params, tmp_path)
    solid = im.getchannel("A").point(lambda v: 255 if v >= OPAQUE else 0).getbbox()
    assert solid is not None
    left, top, right, bottom = solid
    b = meta.bleed
    assert left >= b - 1 and top >= b - 1, f"{meta.id}: contenido en el margen {solid}"
    assert right <= im.width - b + 1 and bottom <= im.height - b + 1, f"{meta.id}: {solid}"


# Measure the real DOM at the middle of the animation: text rectangles vs the arrow ring.
_RECTS_JS = """() => {
  const ring = document.querySelector('.arrow').getBoundingClientRect();
  const out = {cx: ring.left + ring.width / 2, cy: ring.top + ring.height / 2,
               r: ring.width / 2 + 6, rects: []};  // + the 6px ring around the circle
  for (const el of document.querySelectorAll('.side .txt, .side .kicker')) {
    const range = document.createRange();
    range.selectNodeContents(el);
    for (const q of range.getClientRects()) {
      if (q.width > 0) out.rects.push([q.left, q.top, q.right, q.bottom]);
    }
  }
  return out;
}"""


@pytest.mark.parametrize("case", ["ejemplo", "texto_largo"])
def test_comparison_arrow_never_touches_the_text(
    case: str, renderer: PlaywrightGraphicsRenderer, brand: BrandProfile, canvas: Canvas
) -> None:
    template = load_template("comparacion")
    params = template.example_params() if case == "ejemplo" else WORST_COMPARISON
    placement = renderer.place(template, params, canvas, "middle")
    html, _ = renderer.build_html(template, params, brand, 3.5, placement.anchor)
    context = renderer.browser().new_context(
        viewport={"width": template.meta.box_width, "height": template.meta.box_height}
    )
    try:
        page = context.new_page()
        page.set_content(html, wait_until="load")
        page.evaluate("() => document.fonts.ready")
        page.evaluate(_INIT_JS)
        page.evaluate(_SEEK_JS, 1750)  # all entrances done, exit not started
        m = page.evaluate(_RECTS_JS)
    finally:
        context.close()
    assert m["rects"], "no se midió ningún texto"
    clearances = []
    for left, top, right, bottom in m["rects"]:
        dx = max(left - m["cx"], 0, m["cx"] - right)
        dy = max(top - m["cy"], 0, m["cy"] - bottom)
        clearances.append(math.hypot(dx, dy) - m["r"])
    assert min(clearances) >= 12, f"la flecha queda a {min(clearances):.1f}px del texto"
