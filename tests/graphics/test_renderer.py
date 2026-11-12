"""Renderer behaviour with real headless Chromium (no network)."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from fractions import Fraction
from pathlib import Path

import pytest
from PIL import Image

from editoria.contracts import GraphicsRenderer
from editoria.graphics import (
    CHROMIUM_MISSING_MSG,
    GraphicsError,
    GraphicsParamsError,
    GraphicsUnavailable,
    PlaywrightGraphicsRenderer,
    frame_count,
    list_templates,
    load_template,
)
from editoria.schemas import BrandProfile, Canvas, GraphicItem
from editoria.util.geometry import zone_box

FPS = Fraction(30)
# palabra_clave: 880x260 visible + a transparent bleed on every side for its shadow.
BLEED = load_template("palabra_clave").meta.bleed
BOX_W, BOX_H = 880 + 2 * BLEED, 260 + 2 * BLEED


def frame_hashes(folder: Path) -> list[str]:
    return [hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.glob("*.png"))]


def write_template(root: Path, template_id: str, body: str, extra_meta: str = "") -> Path:
    d = root / template_id
    d.mkdir()
    (d / "template.html").write_text(
        '{% extends "_base.html" %}\n{% block body %}' + body + "{% endblock %}\n",
        encoding="utf-8",
    )
    (d / "params.schema.json").write_text(
        '{"type": "object", "additionalProperties": false, "properties": {}}', encoding="utf-8"
    )
    (d / "meta.yaml").write_text(
        f"id: {template_id}\nnombre: Prueba\nsize: [200, 100]\nduracion_s: 0.2\n"
        f"zonas: [center]\n{extra_meta}",
        encoding="utf-8",
    )
    return d


def item(
    template: str, params: Mapping[str, object], t_in: float, t_out: float, **kw: object
) -> GraphicItem:
    return GraphicItem.model_validate(
        {"id": "g01", "template": template, "in": t_in, "out": t_out, "params": dict(params), **kw}
    )


def test_implements_contract() -> None:
    assert isinstance(PlaywrightGraphicsRenderer(), GraphicsRenderer)


def test_two_renders_give_identical_hashes(
    renderer: PlaywrightGraphicsRenderer, brand: BrandProfile, canvas: Canvas, tmp_path: Path
) -> None:
    g = item("palabra_clave", {"texto": "Automatizá"}, 0.3, 1.3)
    a = renderer.render(g, brand, canvas, FPS, tmp_path / "a")
    b = renderer.render(g, brand, canvas, FPS, tmp_path / "b")
    ha, hb = frame_hashes(tmp_path / "a"), frame_hashes(tmp_path / "b")
    assert len(ha) == a.frame_count == b.frame_count == 30
    assert ha == hb
    assert len(set(ha)) > 5, "la animación debe cambiar entre cuadros"


def test_alpha_channel_has_transparent_pixels(
    renderer: PlaywrightGraphicsRenderer, brand: BrandProfile, canvas: Canvas, out_dir: Path
) -> None:
    clip = renderer.render(
        item("palabra_clave", {"texto": "IA"}, 0, 1.0), brand, canvas, FPS, out_dir
    )
    mid = Image.open(out_dir / f"{1 + clip.frame_count // 2:05d}.png")
    assert mid.mode == "RGBA"
    assert mid.size == (clip.w, clip.h) == (BOX_W, BOX_H)  # template box, not the canvas
    alpha = mid.getchannel("A")
    lo, hi = alpha.getextrema()
    assert lo == 0 and hi == 255
    hist = alpha.histogram()
    assert hist[0] > 0.2 * clip.w * clip.h  # plenty of fully transparent background


@pytest.mark.parametrize(
    ("t_in", "t_out", "fps", "expected"),
    [
        (0.3, 2.1, Fraction(30), 54),
        (1.0, 2.0, Fraction(30000, 1001), 30),
        (0.0, 0.5, Fraction(25), 13),
    ],
)
def test_frame_count_is_duration_times_fps(
    renderer: PlaywrightGraphicsRenderer,
    brand: BrandProfile,
    canvas: Canvas,
    tmp_path: Path,
    t_in: float,
    t_out: float,
    fps: Fraction,
    expected: int,
) -> None:
    clip = renderer.render(
        item("palabra_clave", {"texto": "Hola"}, t_in, t_out), brand, canvas, fps, tmp_path
    )
    files = sorted(tmp_path.glob("*.png"))
    assert clip.frame_count == len(files) == expected == frame_count(t_out - t_in, fps)
    assert files[0].name == "00001.png" and files[-1].name == f"{expected:05d}.png"
    assert clip.frames_pattern == tmp_path / "%05d.png"
    assert clip.start == t_in and clip.end == t_out
    assert Fraction(clip.fps) == fps


def test_network_requests_are_blocked(
    custom_templates: Path, brand: BrandProfile, canvas: Canvas, tmp_path: Path
) -> None:
    write_template(
        custom_templates,
        "red",
        '<img src="https://example.com/pixel.png"><link rel="stylesheet" href="http://example.org/a.css">'
        "<div style=\"width:50px;height:50px;background:url('https://example.net/bg.png')\"></div>",
    )
    with PlaywrightGraphicsRenderer(custom_templates, use_cache=False) as r:
        r.render_template("red", {}, brand=brand, canvas=canvas, fps=FPS, out_dir=tmp_path)
        assert r.last_stats is not None
        blocked = r.last_stats.blocked_requests
    assert "https://example.com/pixel.png" in blocked
    assert "http://example.org/a.css" in blocked
    assert all(u.startswith(("http://", "https://")) for u in blocked)


def test_invalid_params_error_before_rendering(
    renderer: PlaywrightGraphicsRenderer, brand: BrandProfile, canvas: Canvas, tmp_path: Path
) -> None:
    with pytest.raises(GraphicsParamsError, match="valores"):
        renderer.render(
            item("dato_grafico", {"tipo": "barras", "valores": "40", "data_source": "real"}, 0, 1),
            brand,
            canvas,
            FPS,
            tmp_path,
        )
    assert not list(tmp_path.glob("*.png"))


@pytest.mark.parametrize("source", ["ejemplo", "real"])
def test_ejemplo_label_in_dom(
    renderer: PlaywrightGraphicsRenderer,
    brand: BrandProfile,
    canvas: Canvas,
    tmp_path: Path,
    source: str,
) -> None:
    params = {
        "tipo": "barras",
        "valores": [40, 75],
        "etiquetas": ["Antes", "Después"],
        "data_source": source,
    }
    clip = renderer.render(item("dato_grafico", params, 0, 0.2), brand, canvas, FPS, tmp_path)
    html = renderer.last_html or ""
    if source == "ejemplo":
        assert clip.labels == ["Ejemplo"]
        assert 'data-editoria-label="Ejemplo"' in html and ">Ejemplo<" in html
    else:
        assert clip.labels == []
        assert "data-editoria-label" not in html and ">Ejemplo<" not in html


def test_ui_demo_always_carries_illustration_label(
    renderer: PlaywrightGraphicsRenderer, brand: BrandProfile, canvas: Canvas, tmp_path: Path
) -> None:
    tpl = load_template("ui_demo")
    clip = renderer.render(
        item("ui_demo", tpl.example_params(), 0, 0.2), brand, canvas, FPS, tmp_path
    )
    assert clip.labels == ["Ilustración"]


def test_missing_mandatory_label_is_an_error(
    custom_templates: Path, brand: BrandProfile, canvas: Canvas, tmp_path: Path
) -> None:
    write_template(
        custom_templates, "sin_etiqueta", "<p>hola</p>", "etiquetas_obligatorias: [Ilustración]\n"
    )
    with (
        PlaywrightGraphicsRenderer(custom_templates, use_cache=False) as r,
        pytest.raises(GraphicsError, match="etiqueta obligatoria 'Ilustración'"),
    ):
        r.render_template("sin_etiqueta", {}, brand=brand, canvas=canvas, fps=FPS, out_dir=tmp_path)


@pytest.mark.parametrize("template_id", [m.id for m in list_templates()])
def test_every_template_renders_example(
    renderer: PlaywrightGraphicsRenderer,
    brand: BrandProfile,
    canvas: Canvas,
    out_dir: Path,
    template_id: str,
) -> None:
    tpl = load_template(template_id)
    clip = renderer.render_template(
        template_id,
        tpl.example_params(),
        brand=brand,
        canvas=canvas,
        fps=FPS,
        out_dir=out_dir,
        duration=0.1,
    )
    assert clip.frame_count == 3
    first = Image.open(out_dir / "00001.png")
    assert first.mode == "RGBA" and first.size == (clip.w, clip.h)
    assert clip.x >= 0 and clip.x + clip.w <= canvas.width
    assert clip.y >= 0 and clip.y + clip.h <= canvas.height


def test_zone_placement_uses_geometry(
    renderer: PlaywrightGraphicsRenderer, brand: BrandProfile, canvas: Canvas, tmp_path: Path
) -> None:
    clip = renderer.render(
        item("palabra_clave", {"texto": "Hola"}, 0, 0.1, zone="lower"), brand, canvas, FPS, tmp_path
    )
    box = zone_box("lower", canvas, 880, 260)  # where the VISIBLE content goes
    assert (clip.x, clip.y, clip.w, clip.h) == (box.x - BLEED, box.y - BLEED, BOX_W, BOX_H)


def test_disallowed_zone_falls_back_with_warning(
    renderer: PlaywrightGraphicsRenderer,
    brand: BrandProfile,
    canvas: Canvas,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    clip = renderer.render(
        item("palabra_clave", {"texto": "Hola"}, 0, 0.1, zone="full"), brand, canvas, FPS, tmp_path
    )
    assert (clip.w, clip.h) == (BOX_W, BOX_H)
    assert "no admite la zona 'full'" in " ".join(capsys.readouterr().err.split())


def test_annotation_is_placed_on_its_point(
    renderer: PlaywrightGraphicsRenderer, brand: BrandProfile, canvas: Canvas, tmp_path: Path
) -> None:
    params = {"tipo": "circulo", "x": 0.5, "y": 0.4, "texto": "Acá"}
    clip = renderer.render(item("anotacion", params, 0, 0.1), brand, canvas, FPS, tmp_path)
    assert clip.x + clip.w / 2 == pytest.approx(540, abs=1)
    assert clip.y + clip.h / 2 == pytest.approx(0.4 * 1920, abs=1)
    # Near the edge the box is clamped inside the canvas.
    edge = renderer.render(
        item("anotacion", {"tipo": "flecha", "x": 0.98, "y": 0.02}, 0, 0.1),
        brand,
        canvas,
        FPS,
        tmp_path / "e",
    )
    assert edge.x + edge.w == canvas.width and edge.y == 0


def test_canvas_scale(
    renderer: PlaywrightGraphicsRenderer, brand: BrandProfile, tmp_path: Path
) -> None:
    small = Canvas(width=720, height=1280)
    clip = renderer.render(
        item("palabra_clave", {"texto": "Hola"}, 0, 0.1), brand, small, FPS, tmp_path
    )
    s = 720 / 1080
    # Same rounding as the browser screenshot of the CSS box (visible content + bleed).
    assert (clip.w, clip.h) == (round(BOX_W * s), round(BOX_H * s))
    assert Image.open(tmp_path / "00001.png").size == (clip.w, clip.h)


def test_cache_skips_rerender(brand: BrandProfile, canvas: Canvas, out_dir: Path) -> None:
    g = item("palabra_clave", {"texto": "Caché"}, 0, 0.5)
    with PlaywrightGraphicsRenderer() as r:
        first = r.render(g, brand, canvas, FPS, out_dir)
        assert r.last_stats is not None and not r.last_stats.cached
        mtimes = {p.name: p.stat().st_mtime_ns for p in out_dir.glob("*.png")}
        second = r.render(g, brand, canvas, FPS, out_dir)
        assert r.last_stats.cached
        assert second == first
        assert {p.name: p.stat().st_mtime_ns for p in out_dir.glob("*.png")} == mtimes
        # Any change in the inputs invalidates the cache.
        r.render(g, brand, canvas, Fraction(25), out_dir)
        assert not r.last_stats.cached
        assert len(list(out_dir.glob("*.png"))) == 13


def test_frame_time_budget(
    renderer: PlaywrightGraphicsRenderer, brand: BrandProfile, canvas: Canvas, tmp_path: Path
) -> None:
    """Target is <= 150 ms/frame; the hard bound here is lenient to avoid CI flakiness."""
    tpl = load_template("checklist")
    renderer.render_template(
        "checklist",
        tpl.example_params(),
        brand=brand,
        canvas=canvas,
        fps=FPS,
        out_dir=tmp_path,
        duration=1.0,
    )
    assert renderer.last_stats is not None
    print(f"checklist: {renderer.last_stats.ms_per_frame:.1f} ms/cuadro")
    assert renderer.last_stats.ms_per_frame < 400


def test_emoji_items_are_rejected(
    renderer: PlaywrightGraphicsRenderer, brand: BrandProfile, canvas: Canvas, tmp_path: Path
) -> None:
    g = GraphicItem.model_validate({"id": "e01", "emoji": "E01", "in": 0, "out": 1})
    with pytest.raises(GraphicsError, match="emoji"):
        renderer.render(g, brand, canvas, FPS, tmp_path)


@pytest.mark.usefixtures("no_chromium")
def test_missing_chromium_gives_spanish_message(
    tmp_path: Path, brand: BrandProfile, canvas: Canvas
) -> None:
    with PlaywrightGraphicsRenderer() as r, pytest.raises(GraphicsUnavailable) as exc:
        r.render(item("palabra_clave", {"texto": "x"}, 0, 0.1), brand, canvas, FPS, tmp_path / "o")
    assert str(exc.value) == CHROMIUM_MISSING_MSG
    assert "playwright install chromium" in CHROMIUM_MISSING_MSG
