"""Editorial segments (sentences and pauses) and the edit map CSV."""

from __future__ import annotations

from pathlib import Path

from editoria.schemas import MAPA_COLUMNS, Segment, SegmentList, Transcript, Word
from editoria.util.files import fmt_ts, write_csv_rows

PAUSE_SPLIT_S = 0.35  # a silence between words at least this long ends a segment
MAX_SEGMENT_S = 8.0  # longer segments are split at their largest internal pause
MIN_INNER_GAP_S = 0.12
SENTENCE_END = (".", "?", "!", "…")


def _split_long(words: list[Word]) -> list[list[Word]]:
    if len(words) < 2 or words[-1].end - words[0].start <= MAX_SEGMENT_S:
        return [words]
    gaps = [(words[i + 1].start - words[i].end, i) for i in range(len(words) - 1)]
    gap, idx = max(gaps)
    if gap < MIN_INNER_GAP_S:
        idx = len(words) // 2 - 1  # no real pause: split in the middle
    return _split_long(words[: idx + 1]) + _split_long(words[idx + 1 :])


def build_segments(transcript: Transcript, pause_s: float = PAUSE_SPLIT_S) -> SegmentList:
    """Group words into sentences: end punctuation or a pause >= ``pause_s`` closes a segment.

    ``role``/``intent`` stay empty: they are decided by the creative director.
    """
    groups: list[list[Word]] = []
    current: list[Word] = []
    for i, word in enumerate(transcript.words):
        current.append(word)
        nxt = transcript.words[i + 1] if i + 1 < len(transcript.words) else None
        ends_sentence = word.text.rstrip("\"')»”").endswith(SENTENCE_END)
        long_pause = nxt is not None and nxt.start - word.end >= pause_s
        if nxt is None or ends_sentence or long_pause:
            groups.extend(_split_long(current))
            current = []
    segments = [
        Segment(
            id=f"s{n:02d}",
            start=g[0].start,
            end=g[-1].end,
            text=" ".join(w.text for w in g),
        )
        for n, g in enumerate(groups, start=1)
    ]
    return SegmentList(segments=segments)


def write_edit_map(path: Path, segments: SegmentList) -> Path:
    """mapa_edicion.csv with the exact template columns (MAPA_COLUMNS); one row per segment."""
    rows = [
        {
            "entrada": fmt_ts(s.start),
            "salida": fmt_ts(s.end),
            "frase_original": s.text,
            "intencion": s.intent,
            "visual": s.visual,
            "metodo": s.method or "",
            "referencia": s.reference,
            "archivo": "",
            "subtitulo": "",
            "grafico": "",
            "sonido": "",
            "estado": "pendiente",
        }
        for s in segments.segments
    ]
    return write_csv_rows(path, MAPA_COLUMNS, rows)
