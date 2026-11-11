"""Group transcript words into caption events (timing + line layout)."""

from __future__ import annotations

import itertools
import math
from collections.abc import Sequence
from dataclasses import dataclass, field

from editoria.captions.text import apply_case, ends_clause, visible_len, wrap_tokens
from editoria.schemas import CaptionStyle, Word

PAUSE_BREAK_S = 0.25  # a silence longer than this always starts a new event
MAX_LINGER_S = 0.8  # how long an event may stay after its last word (reading time)
MIN_EVENT_S = 0.5  # preferred minimum on-screen time (when there is room)
EPS = 1e-6
NBSP = chr(0xA0)


@dataclass
class WordGroup:
    """A caption event before rendering: word ids, timing and wrapped display lines."""

    word_ids: list[int]
    start: float
    end: float
    lines: list[str]
    warnings: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        """Display text, lines joined with a newline (NBSP turned back into spaces)."""
        return "\n".join(self.lines).replace(NBSP, " ")

    @property
    def cps(self) -> float:
        dur = max(self.end - self.start, EPS)
        return visible_len(self.text) / dur


def _word_mid(w: Word) -> float:
    return (w.start + w.end) / 2


def _cut_between(a: Word, b: Word, cuts: Sequence[float]) -> bool:
    lo, hi = _word_mid(a), _word_mid(b)
    return any(lo < c <= hi for c in cuts)


def _hard_runs(words: Sequence[Word], cuts: Sequence[float]) -> list[list[int]]:
    """Split word indices at pauses, clause punctuation and camera cuts."""
    runs: list[list[int]] = []
    cur: list[int] = []
    for i, w in enumerate(words):
        if cur:
            prev = words[cur[-1]]
            if (
                w.start - prev.end > PAUSE_BREAK_S
                or ends_clause(prev.text)
                or _cut_between(prev, w, cuts)
            ):
                runs.append(cur)
                cur = []
        cur.append(i)
    if cur:
        runs.append(cur)
    return runs


def _even_chunks(ids: list[int], k: int) -> list[list[int]]:
    n = len(ids)
    out: list[list[int]] = []
    pos = 0
    for j in range(k):
        size = n // k + (1 if j < n % k else 0)
        out.append(ids[pos : pos + size])
        pos += size
    return [c for c in out if c]


def _tokens(words: Sequence[Word], ids: Sequence[int], style: CaptionStyle) -> list[str]:
    # Internal whitespace becomes NBSP so that splitting a line on " " yields its words.
    toks = [NBSP.join(words[i].text.split()) for i in ids]
    if style.case == "sentence":  # only the first word of the event is capitalised
        return [apply_case(t, "sentence") if j == 0 else t for j, t in enumerate(toks)]
    return [apply_case(t, style.case) for t in toks]


def _layout(words: Sequence[Word], ids: list[int], style: CaptionStyle) -> list[list[int]]:
    """Split a chunk until each piece wraps into the style's line box."""
    if len(ids) <= 1 or wrap_tokens(
        _tokens(words, ids, style), style.max_chars_line, style.max_lines
    ):
        return [ids]
    half = math.ceil(len(ids) / 2)
    return _layout(words, ids[:half], style) + _layout(words, ids[half:], style)


def _chunk_run(words: Sequence[Word], run: list[int], style: CaptionStyle) -> list[list[int]]:
    k = math.ceil(len(run) / style.words_per_event)
    chunks: list[list[int]] = []
    for c in _even_chunks(run, k):
        chunks.extend(_layout(words, c, style))
    return chunks


def group_words(
    words: Sequence[Word],
    style: CaptionStyle,
    cuts: Sequence[float] = (),
    duration: float | None = None,
) -> list[WordGroup]:
    """Words -> timed, wrapped events.

    Guarantees: events are ordered and never overlap; no camera cut falls strictly inside an
    event; each event starts with its first word (clamped to a preceding cut when that word
    straddles it) and ends no later than ``MAX_LINGER_S`` after its last word. Events linger
    after the last word only as much as needed to respect ``max_cps`` / ``MIN_EVENT_S``.
    """
    cuts = sorted(c for c in cuts if c > 0)
    usable = [i for i, w in enumerate(words) if w.text.strip()]
    if not usable:
        return []
    sub = [words[i] for i in usable]
    chunks: list[list[int]] = []
    for run in _hard_runs(sub, cuts):
        chunks.extend(_chunk_run(sub, run, style))

    groups: list[WordGroup] = []
    for chunk in chunks:
        first, last = sub[chunk[0]], sub[chunk[-1]]
        start = first.start
        prev_cuts = [c for c in cuts if first.start < c <= _word_mid(first) + EPS]
        if prev_cuts:
            start = max(prev_cuts)
        end = last.end
        next_cuts = [c for c in cuts if c > start + EPS and c < end]
        if next_cuts:
            end = min(next_cuts)
        toks = _tokens(sub, chunk, style)
        lines = wrap_tokens(toks, style.max_chars_line, style.max_lines) or [" ".join(toks)]
        groups.append(
            WordGroup(word_ids=[usable[i] for i in chunk], start=start, end=end, lines=lines)
        )

    # Transcripts may overlap slightly: never let an event run into the next one.
    for g, nxt in itertools.pairwise(groups):
        if g.end > nxt.start:
            g.end = max(nxt.start, g.start + 0.01)
            nxt.start = max(nxt.start, g.end)

    # Linger for reading speed, never past the next event, the next cut or the media end.
    for idx, g in enumerate(groups):
        last_word_end = words[g.word_ids[-1]].end
        limit = last_word_end + MAX_LINGER_S
        if idx + 1 < len(groups):
            limit = min(limit, groups[idx + 1].start)
        later_cuts = [c for c in cuts if c > g.start + EPS]
        if later_cuts:
            limit = min(limit, later_cuts[0])
        if duration is not None:
            limit = min(limit, duration)
        needed = g.start + max(visible_len(g.text) / style.max_cps, MIN_EVENT_S)
        if needed > g.end:
            g.end = max(g.end, min(needed, limit))
        if g.cps > style.max_cps + 1e-3:
            g.warnings.append(
                f"{g.start:.2f}s: {g.cps:.1f} caracteres/s supera el máximo del estilo "
                f"({style.max_cps:g}); el habla es más rápida que la lectura cómoda."
            )
        widest = max(len(line) for line in g.lines)
        if widest > style.max_chars_line or len(g.lines) > style.max_lines:
            g.warnings.append(
                f"{g.start:.2f}s: una palabra no entra en {style.max_chars_line} caracteres "
                "por línea."
            )
    return groups
