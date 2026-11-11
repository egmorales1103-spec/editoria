"""Fixtures for the graphics tests: one shared Chromium for the whole session."""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest

from editoria.graphics import GraphicsUnavailable, PlaywrightGraphicsRenderer
from editoria.schemas import BrandProfile, Canvas
from editoria.util import resources


@pytest.fixture(scope="session")
def renderer() -> Iterator[PlaywrightGraphicsRenderer]:
    r = PlaywrightGraphicsRenderer(use_cache=False)
    try:
        r.browser()
    except GraphicsUnavailable as exc:  # pragma: no cover - depends on the machine
        pytest.skip(str(exc))
    yield r
    r.close()


@pytest.fixture(scope="session")
def brand() -> BrandProfile:
    return resources.load_brand("master-solution")


@pytest.fixture
def canvas() -> Canvas:
    return Canvas()


@pytest.fixture
def out_dir(tmp_path: Path) -> Path:
    """Output folder with spaces and accents, on purpose."""
    d = tmp_path / "carpeta con espacios ñ" / "gráfico 01"
    d.mkdir(parents=True)
    return d


@pytest.fixture
def no_chromium(monkeypatch: pytest.MonkeyPatch) -> None:
    """Simulate a machine without Playwright's Chromium (the shared browser is hidden)."""
    from playwright.sync_api import Error as PlaywrightError

    from editoria.graphics import renderer as mod

    def _fail() -> None:
        raise PlaywrightError("Executable doesn't exist at C:\\ms-playwright\\chrome.exe")

    monkeypatch.setattr(mod, "_start_browser", _fail)
    monkeypatch.setattr(mod._SharedBrowser, "browser", None)
    monkeypatch.setattr(mod._SharedBrowser, "pw", None)
    monkeypatch.setattr(mod._SharedBrowser, "users", 0)


@pytest.fixture
def custom_templates(tmp_path: Path) -> Path:
    """A templates/graphics copy (with _base.html) where tests can add their own templates."""
    root = tmp_path / "plantillas"
    root.mkdir()
    shutil.copy2(resources.graphics_templates_dir() / "_base.html", root / "_base.html")
    return root
