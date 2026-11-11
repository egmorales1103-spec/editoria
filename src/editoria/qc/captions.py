"""Caption boxes for QC: measured (subtitulos.json) or estimated from subtitulos.ass."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from editoria.schemas import Box, Canvas, CaptionEvent

_TAG_RE = re.compile(r"\{[^}]*\}")
_POS_RE = re.compile(r"\\pos\(\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*\)")
_AN_RE = re.compile(r"\\an(\d)")
_FS_RE = re.compile(r"\\fs(\d+(?:\.\d+)?)")
_TIME_RE = re.compile(r"(\d+):(\d{2}):(\d{2})[.](\d{2})")

LINE_SPACING = 1.2


@dataclass(frozen=True)
class CaptionBox:
    start: float
    end: float
    text: str
    box: Box
    estimated: bool
    editorial: bool = False


@dataclass(frozen=True)
class _Style:
    fontsize: float
    scale_x: float
    scale_y: float
    outline: float
    alignment: int
    margin_l: int
    margin_r: int
    margin_v: int


def _ass_time(text: str) -> float:
    m = _TIME_RE.match(text.strip())
    if not m:
        return 0.0
    h, mi, s, cs = (int(g) for g in m.groups())
    return h * 3600 + mi * 60 + s + cs / 100


def char_em(ch: str) -> float:
    """Approximate advance width (em) of a character in a bold sans font."""
    if ch == " ":
        return 0.26
    if ch in "il.,:;'!|ìíj":
        return 0.28
    if ch in "mwMW":
        return 0.85
    if ch.isdigit():
        return 0.56
    if ch.isupper():
        return 0.68
    if ch.isalpha():
        return 0.48
    return 0.4


def text_width(line: str, size: float) -> float:
    return sum(char_em(c) for c in line) * size


def _split_lines(raw: str) -> list[str]:
    clean = _TAG_RE.sub("", raw).replace("\\h", " ")
    return [ln for ln in re.split(r"\\N|\\n", clean)] or [""]


def _event_box(raw: str, st: _Style, play_w: int, play_h: int, ml: int, mr: int, mv: int) -> Box:
    size = st.fontsize
    if m := _FS_RE.search(raw):
        size = float(m.group(1))
    lines = _split_lines(raw)
    w = max(text_width(ln, size) for ln in lines) * st.scale_x / 100 + 2 * st.outline
    h = len(lines) * size * LINE_SPACING * st.scale_y / 100 + 2 * st.outline
    align = st.alignment
    if m := _AN_RE.search(raw):
        align = int(m.group(1))
    col = (align - 1) % 3  # 0 left, 1 centre, 2 right
    row = (align - 1) // 3  # 0 bottom, 1 middle, 2 top
    if m := _POS_RE.search(raw):
        px, py = float(m.group(1)), float(m.group(2))
        x = px - (0, w / 2, w)[col]
        y = py - (h, h / 2, 0)[row]
    else:
        if col == 0:
            x = ml
        elif col == 2:
            x = play_w - mr - w
        else:
            x = (ml + (play_w - mr)) / 2 - w / 2
        if row == 0:
            y = play_h - mv - h
        elif row == 2:
            y = mv
        else:
            y = (play_h - h) / 2
    return Box(x=round(x), y=round(y), w=round(w), h=round(h))


def parse_ass(path: Path, canvas: Canvas) -> list[CaptionBox]:
    """Estimate canvas-space boxes of every Dialogue line of an ASS file."""
    section = ""
    play_w, play_h = canvas.width, canvas.height
    style_fmt: list[str] = []
    event_fmt: list[str] = []
    styles: dict[str, _Style] = {}
    events: list[tuple[str, dict[str, str]]] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        s = line.strip()
        if s.startswith("[") and s.endswith("]"):
            section = s.lower()
            continue
        if ":" not in s:
            continue
        key, _, value = s.partition(":")
        key, value = key.strip(), value.strip()
        if section == "[script info]":
            if key == "PlayResX":
                play_w = int(float(value))
            elif key == "PlayResY":
                play_h = int(float(value))
        elif section.startswith("[v4"):
            if key == "Format":
                style_fmt = [f.strip() for f in value.split(",")]
            elif key == "Style" and style_fmt:
                vals = [v.strip() for v in value.split(",", len(style_fmt) - 1)]
                d = dict(zip(style_fmt, vals, strict=False))
                styles[d.get("Name", "Default")] = _Style(
                    fontsize=float(d.get("Fontsize", 48)),
                    scale_x=float(d.get("ScaleX", 100)),
                    scale_y=float(d.get("ScaleY", 100)),
                    outline=float(d.get("Outline", 0)),
                    alignment=int(float(d.get("Alignment", 2))),
                    margin_l=int(float(d.get("MarginL", 0))),
                    margin_r=int(float(d.get("MarginR", 0))),
                    margin_v=int(float(d.get("MarginV", 0))),
                )
        elif section == "[events]":
            if key == "Format":
                event_fmt = [f.strip() for f in value.split(",")]
            elif key == "Dialogue" and event_fmt:
                vals = [v.strip() for v in value.split(",", len(event_fmt) - 1)]
                events.append((key, dict(zip(event_fmt, vals, strict=False))))
    default = _Style(48, 100, 100, 0, 2, 10, 10, 10)
    sx, sy = canvas.width / play_w, canvas.height / play_h
    out: list[CaptionBox] = []
    for _, ev in events:
        st = styles.get(ev.get("Style", ""), default)
        ml = int(float(ev.get("MarginL", 0) or 0)) or st.margin_l
        mr = int(float(ev.get("MarginR", 0) or 0)) or st.margin_r
        mv = int(float(ev.get("MarginV", 0) or 0)) or st.margin_v
        raw = ev.get("Text", "")
        b = _event_box(raw, st, play_w, play_h, ml, mr, mv)
        box = Box(x=round(b.x * sx), y=round(b.y * sy), w=round(b.w * sx), h=round(b.h * sy))
        out.append(
            CaptionBox(
                start=_ass_time(ev.get("Start", "0:00:00.00")),
                end=_ass_time(ev.get("End", "0:00:00.00")),
                text=" / ".join(_split_lines(raw)),
                box=box,
                estimated=True,
            )
        )
    return out


def load_events_json(path: Path) -> list[CaptionEvent]:
    data = json.loads(path.read_text(encoding="utf-8"))
    raw = data.get("events", []) if isinstance(data, dict) else data
    return [CaptionEvent.model_validate(e) for e in raw]


def caption_boxes(vdir: Path, canvas: Canvas) -> tuple[list[CaptionBox], str]:
    """Boxes from subtitulos.json when they carry boxes, else estimated from subtitulos.ass."""
    js, ass = vdir / "subtitulos.json", vdir / "subtitulos.ass"
    if js.is_file():
        events = load_events_json(js)
        if events and all(e.box is not None for e in events):
            return [
                CaptionBox(e.start, e.end, e.text.replace("\n", " / "), e.box, False, e.editorial)
                for e in events
                if e.box is not None
            ], js.name
    if ass.is_file():
        return parse_ass(ass, canvas), ass.name
    return [], ""
