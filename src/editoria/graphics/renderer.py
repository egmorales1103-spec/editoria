"""Deterministic HTML/CSS -> RGBA PNG sequence renderer (Playwright + headless Chromium).

Per frame: every animation in the document is paused and seeked to ``frame / fps``, then
the viewport (the template size, not the whole canvas) is captured with a transparent
background. Every http/https request is aborted; fonts are embedded as data URIs.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING, Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from markupsafe import Markup

from editoria.graphics.fonts import build_font_css
from editoria.graphics.templates import (
    BASE_FILE,
    TEMPLATE_FILE,
    GraphicsError,
    GraphicTemplate,
    TemplateMeta,
    load_template,
    templates_root,
)
from editoria.schemas import (
    Box,
    BrandColors,
    BrandProfile,
    Canvas,
    GraphicItem,
    OverlayClip,
    Zone,
    fps_str,
)
from editoria.util import resources
from editoria.util.geometry import zone_box
from editoria.util.log import warn

if TYPE_CHECKING:
    from playwright.sync_api import Browser, Playwright, Route

RENDERER_VERSION = "1"
BASE_CANVAS_WIDTH = 1080  # template sizes are authored for a 1080-wide canvas
FRAME_PATTERN = "%05d.png"
FRAME_START = 1  # first file is 00001.png
CACHE_FILE = ".editoria_render.json"

_HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
_CHROMIUM_ARGS = [
    "--disable-gpu",
    "--disable-lcd-text",
    "--font-render-hinting=none",
    "--force-color-profile=srgb",
    "--disable-threaded-animation",
    "--disable-threaded-scrolling",
    "--disable-checker-imaging",
    "--hide-scrollbars",
    "--mute-audio",
    "--no-first-run",
    "--disable-extensions",
    "--disable-background-networking",
    "--disable-component-update",
    "--disable-default-apps",
    "--disable-sync",
]

_INIT_JS = """() => {
  const anims = document.getAnimations();
  for (const a of anims) a.pause();
  window.__editoriaAnims = anims;
  window.__editoriaSeek = (t) => {
    for (const a of window.__editoriaAnims) a.currentTime = t;
    if (typeof window.editoriaSeek === 'function') window.editoriaSeek(t);
  };
  return anims.length;
}"""
# After seeking, wait for two rendered frames so the compositor has committed the new state
# (without this, edges of moving semi-transparent layers differ between runs). This wait is
# renderer infrastructure: templates themselves may not use requestAnimationFrame.
_SEEK_JS = """(t) => {
  window.__editoriaSeek(t);
  return new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(() => done(t))));
}"""
_FONTS_READY_JS = "() => document.fonts.ready.then(() => document.fonts.size)"
_LABELS_JS = (
    "() => [...document.querySelectorAll('[data-editoria-label]')]"
    ".map(e => e.dataset.editoriaLabel)"
)

CHROMIUM_MISSING_MSG = (
    "Chromium de Playwright no está disponible, así que no se pueden renderizar gráficos. "
    "Instalalo con: uv run playwright install chromium (el pipeline sigue sin gráficos)."
)
PLAYWRIGHT_MISSING_MSG = (
    "Falta el paquete Playwright (extra 'graphics'). Instalalo con: uv sync --all-extras "
    "y luego uv run playwright install chromium (el pipeline sigue sin gráficos)."
)


class GraphicsUnavailable(GraphicsError):
    """Playwright or its Chromium is not installed."""


@dataclass
class RenderStats:
    template: str
    frames: int
    seconds: float
    cached: bool
    blocked_requests: list[str] = field(default_factory=list)

    @property
    def ms_per_frame(self) -> float:
        return 1000.0 * self.seconds / self.frames if self.frames else 0.0


@dataclass(frozen=True)
class Placement:
    box: Box  # canvas-space position and output size
    scale: float  # device scale factor (canvas.width / 1080)
    anchor: dict[str, float] | None  # local CSS px of the target point ("punto" templates)


def frame_count(duration: float, fps: Fraction) -> int:
    """Frames covering ``duration`` at ``fps`` (rounded half up, at least 1)."""
    return max(1, math.floor(float(duration) * float(fps) + 0.5 + 1e-9))


def _luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = (int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))

    def lin(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def _on_color(hex_color: str) -> str:
    """Black or white, whichever reads better on ``hex_color``."""
    return "#0B0B0C" if _luminance(hex_color) > 0.36 else "#FFFFFF"


def _safe_colors(colors: BrandColors) -> dict[str, str]:
    defaults = BrandColors()
    out: dict[str, str] = {}
    for token in ("primary", "accent", "text", "bg"):
        value = str(getattr(colors, token))
        if not _HEX_RE.match(value):
            warn(
                f"Color de marca '{token}' inválido ({value!r}); se usa {getattr(defaults, token)}."
            )
            value = str(getattr(defaults, token))
        out[token] = value[:7] if len(value) == 9 else value
    return out


def brand_css(brand: BrandProfile, stacks: dict[str, str]) -> str:
    c = _safe_colors(brand.colors)
    return (
        ":root{"
        f"--color-primary:{c['primary']};"
        f"--color-accent:{c['accent']};"
        f"--color-text:{c['text']};"
        f"--color-bg:{c['bg']};"
        f"--color-on-accent:{_on_color(c['accent'])};"
        f"--color-on-primary:{_on_color(c['primary'])};"
        f"--font-heading:{stacks[brand.fonts.heading]};"
        f"--font-body:{stacks[brand.fonts.body]};"
        "}"
    )


class _SharedBrowser:
    """Process-wide Chromium. Playwright's sync API allows a single instance per thread, so
    every renderer shares it (reference counted)."""

    pw: Playwright | None = None
    browser: Browser | None = None
    users: int = 0


def _start_browser() -> tuple[Playwright, Browser]:
    from playwright.sync_api import sync_playwright

    pw = sync_playwright().start()
    try:
        return pw, pw.chromium.launch(headless=True, args=_CHROMIUM_ARGS)
    except BaseException:
        pw.stop()
        raise


def _acquire_browser() -> Browser:
    if _SharedBrowser.browser is None:
        try:
            from playwright.sync_api import Error as PlaywrightError
        except ImportError as exc:  # pragma: no cover - depends on the environment
            raise GraphicsUnavailable(PLAYWRIGHT_MISSING_MSG) from exc
        try:
            _SharedBrowser.pw, _SharedBrowser.browser = _start_browser()
        except PlaywrightError as exc:
            raise GraphicsUnavailable(CHROMIUM_MISSING_MSG) from exc
        _SharedBrowser.users = 0
    _SharedBrowser.users += 1
    return _SharedBrowser.browser


def _release_browser() -> None:
    _SharedBrowser.users -= 1
    if _SharedBrowser.users > 0:
        return
    browser, pw = _SharedBrowser.browser, _SharedBrowser.pw
    _SharedBrowser.browser = _SharedBrowser.pw = None
    _SharedBrowser.users = 0
    try:
        if browser is not None:
            browser.close()
    finally:
        if pw is not None:
            pw.stop()


class PlaywrightGraphicsRenderer:
    """Implements :class:`editoria.contracts.GraphicsRenderer`.

    Chromium is launched lazily and shared by every renderer of the process; each rendered
    item gets its own page. Use as a context manager (or call :meth:`close`).
    """

    def __init__(
        self,
        templates_dir: Path | None = None,
        fonts_dir: Path | None = None,
        *,
        use_cache: bool = True,
    ) -> None:
        self.templates_dir = templates_root(templates_dir)
        self.fonts_dir = Path(fonts_dir) if fonts_dir is not None else resources.fonts_dir()
        self.use_cache = use_cache
        self.last_stats: RenderStats | None = None
        self.last_html: str | None = None
        self._browser: Browser | None = None
        self._font_warned: set[str] = set()
        self._env = Environment(
            loader=FileSystemLoader(str(self.templates_dir)),
            autoescape=True,
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
        )

    # ---- lifecycle ----------------------------------------------------------------------
    def __enter__(self) -> PlaywrightGraphicsRenderer:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        if self._browser is not None:
            self._browser = None
            _release_browser()

    def browser(self) -> Browser:
        if self._browser is None:
            self._browser = _acquire_browser()
        return self._browser

    # ---- contract -----------------------------------------------------------------------
    def render(
        self, item: GraphicItem, brand: BrandProfile, canvas: Canvas, fps: Fraction, out_dir: Path
    ) -> OverlayClip:
        if item.template is None:
            raise GraphicsError(
                f"{item.id}: es un emoji ('{item.emoji}'); los emojis no se renderizan acá."
            )
        return self.render_template(
            item.template,
            item.params,
            brand=brand,
            canvas=canvas,
            fps=fps,
            out_dir=out_dir,
            duration=item.out - item.in_,
            zone=item.zone,
            clip_id=item.id,
            start=item.in_,
        )

    # ---- implementation -----------------------------------------------------------------
    def place(
        self, template: GraphicTemplate, params: dict[str, Any], canvas: Canvas, zone: Zone
    ) -> Placement:
        meta = template.meta
        scale = canvas.width / BASE_CANVAS_WIDTH
        vw = round(meta.width * scale)  # visible content
        vh = round(meta.height * scale)
        bleed = round(meta.bleed * scale)
        # Rendered image: same rounding as the browser screenshot of the CSS box.
        w = round(meta.box_width * scale)
        h = round(meta.box_height * scale)
        if meta.ubicacion == "punto":
            px = float(params["x"]) * canvas.width
            py = float(params["y"]) * canvas.height
            x = int(min(max(round(px - w / 2), 0), max(canvas.width - w, 0)))
            y = int(min(max(round(py - h / 2), 0), max(canvas.height - h, 0)))
            anchor = {
                "x": round((px - x) / scale, 2),
                "y": round((py - y) / scale, 2),
                # Unit vector from the point towards the canvas centre (where the label goes).
                **_towards_centre(px, py, canvas),
            }
            return Placement(Box(x=x, y=y, w=w, h=h), scale, anchor)
        if zone not in meta.zonas:
            warn(
                f"La plantilla '{meta.id}' no admite la zona '{zone}' "
                f"(admite: {', '.join(meta.zonas)}); se usa '{meta.zonas[0]}'."
            )
            zone = meta.zonas[0]
        # The zone places the VISIBLE content; the bleed margin extends beyond it.
        box = zone_box(zone, canvas, vw, vh)
        return Placement(Box(x=box.x - bleed, y=box.y - bleed, w=w, h=h), scale, None)

    def build_html(
        self,
        template: GraphicTemplate,
        params: dict[str, Any],
        brand: BrandProfile,
        duration: float,
        anchor: dict[str, float] | None = None,
    ) -> tuple[str, str]:
        """Return (html, font_digest)."""
        families = [brand.fonts.heading, brand.fonts.body]
        fonts = build_font_css(families, self.fonts_dir, quiet=True)
        new_missing = [m for m in fonts.missing if m not in self._font_warned]
        if new_missing:
            self._font_warned.update(new_missing)
            build_font_css(new_missing, self.fonts_dir)  # emits the WARN once per family
        meta = template.meta
        tpl = self._env.get_template(f"{template.id}/{TEMPLATE_FILE}")
        html = tpl.render(
            params=params,
            meta=meta,
            w=meta.box_width,
            h=meta.box_height,
            bleed=meta.bleed,
            duration=round(duration, 4),
            anchor=anchor or {},
            brand_name=brand.name,
            font_css=Markup(fonts.css),
            brand_css=Markup(brand_css(brand, fonts.stacks)),
        )
        return html, fonts.digest

    def cache_key(
        self,
        template: GraphicTemplate,
        params: dict[str, Any],
        brand: BrandProfile,
        fps: Fraction,
        placement: Placement,
        duration: float,
        font_digest: str,
    ) -> str:
        payload = {
            "renderer": RENDERER_VERSION,
            "template": template.digest(),
            "params": params,
            "brand": brand.model_dump(mode="json"),
            "fps": fps_str(fps),
            "size": [placement.box.w, placement.box.h],
            "scale": placement.scale,
            "anchor": placement.anchor,
            "duration": round(duration, 6),
            "fonts": font_digest,
        }
        blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def render_template(
        self,
        template_id: str,
        params: dict[str, Any],
        *,
        brand: BrandProfile,
        canvas: Canvas,
        fps: Fraction,
        out_dir: Path,
        duration: float | None = None,
        zone: Zone | None = None,
        clip_id: str | None = None,
        start: float = 0.0,
    ) -> OverlayClip:
        template = load_template(template_id, self.templates_dir)
        meta = template.meta
        params = template.validate(dict(params))
        dur = float(duration if duration is not None else meta.duracion_s)
        if dur <= 0:
            raise GraphicsError(f"Duración inválida para '{template_id}': {dur} s.")
        placement = self.place(template, params, canvas, zone or meta.zonas[0])
        html, font_digest = self.build_html(template, params, brand, dur, placement.anchor)
        self.last_html = html
        n = frame_count(dur, fps)
        key = self.cache_key(template, params, brand, fps, placement, dur, font_digest)
        out_dir = Path(out_dir)
        clip_kwargs: dict[str, Any] = {
            "id": clip_id or template_id,
            "frames_pattern": out_dir / FRAME_PATTERN,
            "frame_count": n,
            "fps": fps_str(fps),
            "x": placement.box.x,
            "y": placement.box.y,
            "w": placement.box.w,
            "h": placement.box.h,
            "start": start,
            "end": start + dur,
        }

        cached = self._read_cache(out_dir, key, n) if self.use_cache else None
        if cached is not None:
            self.last_stats = RenderStats(template_id, n, 0.0, cached=True)
            return OverlayClip(**clip_kwargs, labels=cached)

        out_dir.mkdir(parents=True, exist_ok=True)
        for old in out_dir.glob("*.png"):
            old.unlink()
        (out_dir / CACHE_FILE).unlink(missing_ok=True)

        labels, stats = self._capture(template, html, placement, fps, n, out_dir)
        missing = [lab for lab in meta.etiquetas_obligatorias if lab not in labels]
        if missing:
            raise GraphicsError(
                f"La plantilla '{template_id}' no muestra la etiqueta obligatoria "
                + ", ".join(f"'{m}'" for m in missing)
                + "."
            )
        self.last_stats = stats
        (out_dir / CACHE_FILE).write_text(
            json.dumps(
                {"key": key, "frames": n, "labels": labels, "template": template_id},
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return OverlayClip(**clip_kwargs, labels=labels)

    def _read_cache(self, out_dir: Path, key: str, n: int) -> list[str] | None:
        marker = out_dir / CACHE_FILE
        if not marker.is_file():
            return None
        try:
            data = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if data.get("key") != key or data.get("frames") != n:
            return None
        if not all((out_dir / f"{i:05d}.png").is_file() for i in range(FRAME_START, n + 1)):
            return None
        return [str(x) for x in data.get("labels", [])]

    def _capture(
        self,
        template: GraphicTemplate,
        html: str,
        placement: Placement,
        fps: Fraction,
        n: int,
        out_dir: Path,
    ) -> tuple[list[str], RenderStats]:
        browser = self.browser()
        blocked: list[str] = []

        def _route(route: Route) -> None:
            url = route.request.url
            if url.startswith(("data:", "blob:", "about:")):
                route.continue_()
                return
            blocked.append(url)
            route.abort("blockedbyclient")

        context = browser.new_context(
            viewport={
                "width": template.meta.box_width,
                "height": template.meta.box_height,
            },
            device_scale_factor=placement.scale,
            locale="es-AR",
            timezone_id="UTC",
            reduced_motion="no-preference",
            color_scheme="dark",
            service_workers="block",
        )
        try:
            context.route("**/*", _route)
            page = context.new_page()
            page.set_content(html, wait_until="load")
            page.evaluate(_FONTS_READY_JS)
            page.evaluate(_INIT_JS)
            labels: list[str] = list(page.evaluate(_LABELS_JS))
            t0 = time.perf_counter()
            step_ms = 1000.0 / float(fps)
            for i in range(n):
                page.evaluate(_SEEK_JS, i * step_ms)
                page.screenshot(
                    path=str(out_dir / f"{i + FRAME_START:05d}.png"),
                    omit_background=True,
                    type="png",
                )
            elapsed = time.perf_counter() - t0
        finally:
            context.close()
        if blocked:
            warn(
                f"Plantilla '{template.id}': se bloquearon {len(blocked)} solicitud(es) de red "
                f"(los gráficos se renderizan sin red): {', '.join(blocked[:3])}"
            )
        return labels, RenderStats(template.id, n, elapsed, cached=False, blocked_requests=blocked)


def _towards_centre(px: float, py: float, canvas: Canvas) -> dict[str, float]:
    dx = canvas.width / 2 - px
    dy = canvas.height / 2 - py
    norm = (dx * dx + dy * dy) ** 0.5
    ux, uy = (0.0, 1.0) if norm < 1e-6 else (dx / norm, dy / norm)
    # ``angle``: direction of travel from the label (towards the centre) to the point, degrees.
    angle = math.degrees(math.atan2(-uy, -ux))
    return {"dx": round(ux, 4), "dy": round(uy, 4), "angle": round(angle, 2)}


def chromium_available() -> bool:
    """True when Playwright can launch headless Chromium."""
    try:
        with PlaywrightGraphicsRenderer() as r:
            r.browser()
        return True
    except GraphicsUnavailable:
        return False


__all__ = [
    "BASE_FILE",
    "CACHE_FILE",
    "CHROMIUM_MISSING_MSG",
    "FRAME_PATTERN",
    "FRAME_START",
    "GraphicsUnavailable",
    "Placement",
    "PlaywrightGraphicsRenderer",
    "RenderStats",
    "TemplateMeta",
    "chromium_available",
    "frame_count",
]
