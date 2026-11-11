"""Resolve caption font families: repo fonts first, then system fonts, then a fallback."""

from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path

from editoria.util import resources

FONT_SUFFIXES = (".ttf", ".otf", ".ttc")


def system_fallback_family() -> str:
    if sys.platform.startswith("win") or sys.platform == "darwin":
        return "Arial"
    return "DejaVu Sans"


def _system_font_dirs() -> list[Path]:
    if sys.platform.startswith("win"):
        windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
        local = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Windows" / "Fonts"
        return [windir / "Fonts", local]
    if sys.platform == "darwin":
        return [
            Path("/System/Library/Fonts"),
            Path("/Library/Fonts"),
            Path.home() / "Library/Fonts",
        ]
    return [Path("/usr/share/fonts"), Path("/usr/local/share/fonts"), Path.home() / ".fonts"]


def _key(name: str) -> str:
    return "".join(ch for ch in name.lower() if ch.isalnum())


@lru_cache(maxsize=8)
def _families_in(directory: str) -> frozenset[str]:
    """Normalised family names found in ``directory`` (font name table when readable)."""
    root = Path(directory)
    if not root.is_dir():
        return frozenset()
    found: set[str] = set()
    try:
        from PIL import ImageFont
    except ImportError:  # pragma: no cover - pillow is a hard dependency
        ImageFont = None  # type: ignore[assignment]
    for p in root.rglob("*"):
        if p.suffix.lower() not in FONT_SUFFIXES:
            continue
        found.add(_key(p.stem.split("-")[0].split("[")[0]))
        if ImageFont is not None:
            try:
                family = ImageFont.truetype(str(p), 12).getname()[0]
            except Exception:
                continue
            if family:
                found.add(_key(family))
    return frozenset(found)


def font_in_dir(family: str, directory: Path) -> bool:
    return _key(family) in _families_in(str(directory))


def font_in_system(family: str) -> bool:
    key = _key(family)
    for d in _system_font_dirs():
        if not d.is_dir():
            continue
        if any(key in _key(p.stem) for p in d.glob("*") if p.suffix.lower() in FONT_SUFFIXES):
            return True
    return False


def resolve_family(candidates: list[str], fonts_dir: Path | None = None) -> tuple[str, str | None]:
    """Pick the first available family. Returns (family, warning-or-None).

    Order: each candidate in the repo fonts dir, then each candidate installed in the
    system, then the platform fallback (always with a warning).
    """
    fdir = fonts_dir if fonts_dir is not None else resources.fonts_dir()
    cands = [c for c in dict.fromkeys(candidates) if c]
    for fam in cands:
        if font_in_dir(fam, fdir):
            return fam, None
    for fam in cands:
        if font_in_system(fam):
            return fam, (
                f"La fuente '{fam}' no está en {fdir}; se usa la instalada en el sistema "
                "(ejecutá scripts/fetch_assets.py para un render reproducible)."
            )
    fallback = system_fallback_family()
    wanted = cands[0] if cands else "(sin fuente)"
    return fallback, (
        f"Falta la fuente '{wanted}' (ni en {fdir} ni en el sistema); se usa '{fallback}'."
    )
