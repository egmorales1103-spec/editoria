"""Locate repo resources (brands, styles, templates, assets) and load them."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from editoria.schemas import AssetManifest, BrandProfile, StylePreset, read_model


@lru_cache(maxsize=1)
def repo_root() -> Path:
    """Root holding brands/, styles/, templates/, assets/.

    ``EDITORIA_HOME`` wins; otherwise walk up from this file (editable/dev install) and
    finally from the current directory.
    """
    env = os.environ.get("EDITORIA_HOME")
    if env:
        return Path(env).resolve()
    for start in (Path(__file__).resolve(), Path.cwd().resolve()):
        for parent in [start, *start.parents]:
            if (parent / "styles").is_dir() and (parent / "brands").is_dir():
                return parent
    return Path.cwd().resolve()


def brands_dir() -> Path:
    return repo_root() / "brands"


def styles_dir() -> Path:
    return repo_root() / "styles"


def templates_dir() -> Path:
    return repo_root() / "templates"


def graphics_templates_dir() -> Path:
    return templates_dir() / "graphics"


def doc_templates_dir() -> Path:
    return templates_dir() / "docs"


def assets_dir() -> Path:
    return repo_root() / "assets"


def fonts_dir() -> Path:
    return assets_dir() / "fonts"


FONT_SUFFIXES = (".ttf", ".otf", ".ttc")


def font_family_dir(family: str) -> Path | None:
    """Folder to pass as libass ``fontsdir`` for ``family``.

    libass does not scan subfolders, so this returns ``assets/fonts/<family>/`` when it holds
    font files, else ``assets/fonts/`` if it holds font files directly, else None (system fonts).
    Every render path (pipeline, ``render``, captions) must use this helper.
    """
    root = fonts_dir()
    for cand in (root / family, root):
        if cand.is_dir() and any(p.suffix.lower() in FONT_SUFFIXES for p in cand.iterdir()):
            return cand
    return None


def emoji_dir() -> Path:
    return assets_dir() / "emoji"


def emoji_path(emoji_id: str) -> Path:
    return emoji_dir() / f"{emoji_id}.gif"


def load_brand(slug: str) -> BrandProfile:
    path = brands_dir() / slug / "brand.yaml"
    if not path.exists():
        raise FileNotFoundError(f"No existe la marca '{slug}' ({path}).")
    return read_model(path, BrandProfile)


def style_path(style_id: str) -> Path:
    matches = sorted(styles_dir().glob(f"{style_id.upper()}_*.yaml"))
    if not matches:
        raise FileNotFoundError(f"No existe el estilo '{style_id}' en {styles_dir()}.")
    return matches[0]


def load_style(style_id: str) -> StylePreset:
    return read_model(style_path(style_id), StylePreset)


def load_sfx_manifest() -> AssetManifest:
    p = assets_dir() / "sfx" / "manifest.yaml"
    return read_model(p, AssetManifest) if p.exists() else AssetManifest()


def load_external_manifest() -> AssetManifest:
    p = assets_dir() / "externos.yaml"
    return read_model(p, AssetManifest) if p.exists() else AssetManifest()
