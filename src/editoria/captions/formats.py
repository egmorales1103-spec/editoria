"""Plain subtitle formats: SRT and WebVTT (clean UTF-8, no styling) and subtitulos.json."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from pathlib import Path

from editoria.schemas import CaptionEvent


def _ms(t: float) -> int:
    return max(round(t * 1000), 0)


def _clock(t: float, sep: str) -> str:
    total = _ms(t)
    h, rem = divmod(total, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def srt_time(t: float) -> str:
    return _clock(t, ",")


def vtt_time(t: float) -> str:
    return _clock(t, ".")


def to_srt(events: Sequence[CaptionEvent]) -> str:
    blocks = []
    for n, ev in enumerate(events, start=1):
        blocks.append(f"{n}\n{srt_time(ev.start)} --> {srt_time(ev.end)}\n{ev.text}\n")
    return "\n".join(blocks)


def _vtt_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def to_vtt(events: Sequence[CaptionEvent]) -> str:
    out = ["WEBVTT", ""]
    for ev in events:
        out.append(f"{vtt_time(ev.start)} --> {vtt_time(ev.end)}")
        out.append(_vtt_escape(ev.text))
        out.append("")
    return "\n".join(out)


_TIME_RE = re.compile(r"(\d+):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d+):(\d{2}):(\d{2})[,.](\d{3})")


def _secs(h: str, m: str, s: str, ms: str) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def parse_srt(text: str) -> list[CaptionEvent]:
    """Parse SRT (or the cue part of VTT) into events. Tolerates CRLF and BOM."""
    text = text.lstrip("﻿").replace("\r\n", "\n")
    events: list[CaptionEvent] = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = block.split("\n")
        for i, line in enumerate(lines):
            m = _TIME_RE.search(line)
            if m:
                g = m.groups()
                events.append(
                    CaptionEvent(
                        start=_secs(*g[:4]),
                        end=_secs(*g[4:]),
                        text="\n".join(lines[i + 1 :]).strip("\n"),
                    )
                )
                break
    return events


def write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8", newline="\n")
    return path


def write_events_json(path: Path, events: Sequence[CaptionEvent]) -> Path:
    data = [ev.model_dump(mode="json", exclude_none=True) for ev in events]
    return write_text(path, json.dumps(data, ensure_ascii=False, indent=2))


def read_events_json(path: Path) -> list[CaptionEvent]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [CaptionEvent.model_validate(d) for d in data]
