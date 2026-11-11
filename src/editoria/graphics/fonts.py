"""Local @font-face rules for the brand fonts (embedded as data URIs: no file/http access)."""

from __future__ import annotations

import base64
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from editoria.util.log import warn

FONT_EXTS = {".woff2": "woff2", ".woff": "woff", ".ttf": "truetype", ".otf": "opentype"}
FALLBACK_STACK = "'Segoe UI', system-ui, -apple-system, Roboto, 'Helvetica Neue', Arial, sans-serif"

_WEIGHTS = [
    ("extralight", 200),
    ("ultralight", 200),
    ("semibold", 600),
    ("demibold", 600),
    ("extrabold", 800),
    ("ultrabold", 800),
    ("thin", 100),
    ("light", 300),
    ("regular", 400),
    ("book", 400),
    ("medium", 500),
    ("bold", 700),
    ("black", 900),
    ("heavy", 900),
]


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


@dataclass(frozen=True)
class FontFile:
    family: str
    path: Path
    weight: str  # "700" or "100 900" for variable fonts
    italic: bool

    @property
    def fmt(self) -> str:
        return FONT_EXTS[self.path.suffix.lower()]


def _weight_of(stem: str) -> str:
    low = _norm(stem)
    if "variable" in low or "[" in stem or "wght" in low:
        return "100 900"
    low = low.removesuffix("italic")
    for key, value in _WEIGHTS:  # compound names (extrabold) are listed before simple ones
        if low.endswith(key):
            return str(value)
    return "400"


def find_font_files(family: str, fonts_dir: Path) -> list[FontFile]:
    """Font files in ``fonts_dir`` (recursive) whose file name starts with ``family``."""
    if not fonts_dir.is_dir():
        return []
    key = _norm(family)
    found: list[FontFile] = []
    for p in sorted(fonts_dir.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in FONT_EXTS:
            continue
        stem = p.stem
        if not _norm(stem).startswith(key):
            continue
        rest = _norm(stem)[len(key) :]
        # Avoid "Inter" matching "InterDisplay" / "InterTight" unless it is a weight/style word.
        if rest and not re.match(
            r"^(variable|wght|opsz|italic|" + "|".join(k for k, _ in _WEIGHTS) + r"|vf|\d)",
            rest,
        ):
            continue
        italic = "italic" in stem.lower()
        found.append(FontFile(family, p, _weight_of(stem), italic))
    return found


@dataclass(frozen=True)
class FontSetup:
    css: str  # @font-face rules
    stacks: dict[str, str]  # family -> CSS font-family stack
    digest: str  # changes when the set of font files changes
    missing: tuple[str, ...]


def build_font_css(families: list[str], fonts_dir: Path, *, quiet: bool = False) -> FontSetup:
    """@font-face rules for each family. Missing families fall back to system fonts (WARN)."""
    rules: list[str] = []
    stacks: dict[str, str] = {}
    missing: list[str] = []
    h = hashlib.sha256()
    for family in dict.fromkeys(families):
        files = find_font_files(family, fonts_dir)
        safe = family.replace("'", "")
        if not files:
            missing.append(family)
            # The system copy of the family is still preferred if it is installed.
            stacks[family] = f"'{safe}', {FALLBACK_STACK}"
            continue
        local = f"EditorIA {safe}"
        stacks[family] = f"'{local}', '{safe}', {FALLBACK_STACK}"
        for f in files:
            data = f.path.read_bytes()
            h.update(f.path.name.encode())
            h.update(hashlib.sha256(data).digest())
            b64 = base64.b64encode(data).decode("ascii")
            rules.append(
                "@font-face{"
                f"font-family:'{local}';"
                f"src:url(data:font/{f.fmt};base64,{b64}) format('{f.fmt}');"
                f"font-weight:{f.weight};"
                f"font-style:{'italic' if f.italic else 'normal'};"
                "font-display:block;}"
            )
    if missing and not quiet:
        warn(
            "No se encontró la fuente de marca "
            + ", ".join(f"'{m}'" for m in missing)
            + f" en {fonts_dir}; se usa la fuente del sistema. "
            "Descargala con 'uv run python scripts/fetch_assets.py'."
        )
    h.update(("|".join(missing)).encode())
    return FontSetup("\n".join(rules), stacks, h.hexdigest(), tuple(missing))
