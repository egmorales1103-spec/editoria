"""Parse the completed ``Feedback_V1.md`` template into :class:`Feedback` (feedback.json)."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from editoria.ingest.errors import IngestError
from editoria.schemas import Feedback, FeedbackItem, write_model
from editoria.util.project import FEEDBACK_FILE, ProjectContext

_TIME = r"(?:\d+:)?\d{1,2}:\d{2}(?:[.,]\d+)?|\d+(?:[.,]\d+)?"
_RANGE = re.compile(rf"^\s*({_TIME})\s*(?:[-–—]\s*({_TIME}))?\s*$")
_VERSION = re.compile(r"^V\d+$")

# Template placeholders that mean "not filled in".
_PLACEHOLDER_PREFERRED = "a / b / c / combinacion concreta"  # accent-free (see _norm)
_PLACEHOLDER_ELEMENT = "toma / ritmo / subtitulo / grafico / sonido"


def _norm(text: str) -> str:
    base = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in base if not unicodedata.combining(c)).strip()


def parse_time(token: str) -> float:
    """'mm:ss', 'mm:ss.s', 'h:mm:ss', 'ss.s' (decimal point or comma) -> seconds."""
    parts = token.replace(",", ".").split(":")
    if len(parts) == 1:
        return float(parts[0])
    seconds = float(parts[-1])
    if seconds >= 60:
        raise ValueError(f"segundos fuera de rango en '{token}'")
    total = 0.0
    for p in parts[:-1]:
        total = total * 60 + int(p)
    return total * 60 + seconds if len(parts) > 1 else seconds


def parse_range(cell: str) -> tuple[float, float]:
    """'00:12–00:15', '12.5-14', '0:30' (single instant) -> (t_in, t_out)."""
    m = _RANGE.match(cell.strip())
    if not m:
        raise ValueError(f"no se entiende el tiempo '{cell.strip()}'")
    t_in = parse_time(m.group(1))
    t_out = parse_time(m.group(2)) if m.group(2) else t_in
    if t_out < t_in:
        raise ValueError(f"el fin es anterior al inicio en '{cell.strip()}'")
    return t_in, t_out


def _cells(line: str) -> list[str]:
    inner = line.strip()
    inner = inner[1:] if inner.startswith("|") else inner
    inner = inner[:-1] if inner.endswith("|") else inner
    return [c.strip() for c in re.split(r"(?<!\\)\|", inner)]


def _is_separator(line: str) -> bool:
    return bool(re.fullmatch(r"\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?", line.strip()))


def _bullets(lines: list[str]) -> list[str]:
    """Bullet texts of a section; indented lines continue the previous bullet."""
    out: list[str] = []
    for raw in lines:
        stripped = raw.strip()
        if not stripped:
            continue
        m = re.match(r"^[-*+]\s+(.*)$", stripped)
        if m:
            out.append(m.group(1).strip())
        elif out and raw[:1].isspace() and not stripped.startswith("|"):
            out[-1] = f"{out[-1]} {stripped}"
    return out


def _sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {"": []}
    current = ""
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            current = _norm(line.lstrip("# ").strip())
            sections.setdefault(current, [])
        else:
            sections[current].append(line)
    return sections


def _section(sections: dict[str, list[str]], *keys: str) -> list[str]:
    for name, body in sections.items():
        if any(k in name for k in keys):
            return body
    return []


def _field(bullets: list[str], label: str) -> str:
    for b in bullets:
        head, sep, value = b.partition(":")
        if sep and _norm(head).startswith(label):
            return value.strip()
    return ""


def _parse_table(lines: list[str]) -> list[FeedbackItem]:
    items: list[FeedbackItem] = []
    problems: list[str] = []
    header_seen = False
    for line in lines:
        if not line.strip().startswith("|"):
            continue
        if _is_separator(line):
            continue
        cells = _cells(line)
        if not header_seen:
            header_seen = True  # first table row is the header
            continue
        cells += [""] * (4 - len(cells))
        when, element, change, desired = cells[:4]
        element_text = "" if _norm(element) == _PLACEHOLDER_ELEMENT else element
        if not change and not desired:
            continue  # empty row or the untouched example row (00:00-00:00): nothing to apply
        try:
            if not when:
                raise ValueError("falta el tiempo")
            t_in, t_out = parse_range(when)
        except ValueError as exc:
            problems.append(f"'{change or desired}': {exc}")
            continue
        items.append(
            FeedbackItem(
                t_in=t_in, t_out=t_out, element=element_text, change=change, desired=desired
            )
        )
    if problems:
        raise IngestError(
            "No se pudo leer la tabla de feedback. Corregí estas filas:\n- " + "\n- ".join(problems)
        )
    return items


def _parse_quick_review(lines: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for b in _bullets(lines):
        m = re.match(r"^(¿.*?\?)\s*[:\-–—]?\s*(.*)$", b)
        if m and m.group(2).strip():
            out[m.group(1).strip()] = m.group(2).strip()
    return out


def parse_feedback(md_path: Path, version: str) -> Feedback:
    """Convert a completed Feedback_V1.md into a :class:`Feedback` about ``version``.

    Rows with no content (empty or the untouched ``00:00–00:00`` example) are ignored; a row
    with content but an unreadable time is an error (feedback is never guessed).
    """
    if not _VERSION.match(version):
        raise IngestError(f"Versión inválida '{version}' (se espera V1, V2, ...).")
    path = Path(md_path)
    if not path.is_file():
        raise IngestError(f"No existe el archivo de feedback '{path}'.")
    text = path.read_text(encoding="utf-8-sig")
    sections = _sections(text)
    general = _bullets(_section(sections, "impresion general"))
    preferred = _field(general, "propuesta")
    if _norm(preferred).rstrip(". ") == _PLACEHOLDER_PREFERRED:
        preferred = ""
    table_lines = _section(sections, "cambios por momento") or text.splitlines()
    return Feedback(
        version=version,
        preferred=preferred,
        keep=_field(general, "quiero conservar"),
        change=_field(general, "quiero cambiar"),
        items=_parse_table(table_lines),
        quick_review=_parse_quick_review(_section(sections, "revision rapida")),
    )


def save_feedback(ctx: ProjectContext, feedback: Feedback, *, force: bool = False) -> Path:
    """Write ``feedback.json`` inside the version it is about (the only file added to it)."""
    vdir = ctx.version_dir(feedback.version)
    if not vdir.is_dir():
        raise IngestError(
            f"No existe la versión {feedback.version} del proyecto '{ctx.slug}'. "
            "El feedback se guarda dentro de la versión entregada."
        )
    target = vdir / FEEDBACK_FILE
    if target.exists() and not force:
        raise IngestError(
            f"{feedback.version} ya tiene feedback.json. No se sobrescribe: usá --force "
            "para reemplazarlo."
        )
    return write_model(target, feedback)
