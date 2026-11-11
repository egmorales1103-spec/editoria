"""Text helpers shared by captions, planning and policy: normalisation, case, line wrapping."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from typing import Literal

Case = Literal["upper", "lower", "sentence", "as_is"]

_PUNCT_RE = re.compile(r"[^\w\s%]", re.UNICODE)
_SPACE_RE = re.compile(r"\s+")
BREAK_PUNCT = (".", ",", ";", ":", "?", "!", "…")
_NUMBER_WORDS = frozenset(
    {
        "cero",
        "uno",
        "dos",
        "tres",
        "cuatro",
        "cinco",
        "seis",
        "siete",
        "ocho",
        "nueve",
        "diez",
        "veinte",
        "treinta",
        "cuarenta",
        "cincuenta",
        "cien",
        "ciento",
        "mil",
        "millon",
        "millones",
        "doble",
        "triple",
        "mitad",
        "porcentaje",
    }
)
_FIGURE_RE = re.compile(r"\d|%|\bpor\s+ciento\b", re.IGNORECASE)


def strip_accents(text: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFD", text) if unicodedata.category(ch) != "Mn"
    )


def normalize(text: str) -> str:
    """Lowercase, accent-free, punctuation-free, single-spaced (for matching only)."""
    t = strip_accents(text).lower()
    t = _PUNCT_RE.sub(" ", t)
    return _SPACE_RE.sub(" ", t).strip()


def contains_phrase(haystack: str, needle: str) -> bool:
    """Whole-word, accent/case-insensitive containment."""
    h = f" {normalize(haystack)} "
    n = normalize(needle)
    return bool(n) and f" {n} " in h


def has_figure(text: str) -> bool:
    """True if the text carries digits, percentages or number words."""
    if _FIGURE_RE.search(text):
        return True
    return any(tok in _NUMBER_WORDS for tok in normalize(text).split())


def is_figure_word(word: str) -> bool:
    return has_figure(word)


def apply_case(text: str, case: Case) -> str:
    if case == "upper":
        return text.upper()
    if case == "lower":
        return text.lower()
    if case == "sentence":
        for i, ch in enumerate(text):
            if ch.isalpha():
                return text[:i] + ch.upper() + text[i + 1 :]
        return text
    return text


def ends_clause(word: str) -> bool:
    return word.rstrip("\"'»”)").endswith(BREAK_PUNCT)


def visible_len(text: str) -> int:
    """Characters counted for reading speed: everything except whitespace and line breaks."""
    return sum(1 for ch in text if not ch.isspace())


def _line_len(tokens: Sequence[str]) -> int:
    return sum(len(t) for t in tokens) + max(len(tokens) - 1, 0)


def wrap_tokens(tokens: Sequence[str], max_chars: int, max_lines: int) -> list[str] | None:
    """Balanced wrap of ``tokens`` into the fewest lines (<= max_lines) of <= max_chars.

    Returns None when it does not fit. A single token longer than ``max_chars`` is accepted
    alone on its line (it cannot be broken).
    """
    toks = list(tokens)
    if not toks:
        return []
    if len(toks) == 1:
        return [toks[0]]
    n = len(toks)
    for lines in range(1, min(max_lines, n) + 1):
        best = _best_partition(toks, lines)
        if best is not None and max(_line_len(seg) for seg in best) <= max_chars:
            return [" ".join(seg) for seg in best]
    return None


def _best_partition(toks: list[str], k: int) -> list[list[str]] | None:
    """Partition into exactly k contiguous non-empty lines minimising the longest line."""
    n = len(toks)
    if k > n:
        return None
    best: tuple[int, list[list[str]]] | None = None

    def rec(start: int, left: int, acc: list[list[str]]) -> None:
        nonlocal best
        if left == 1:
            seg = toks[start:]
            parts = [*acc, seg]
            score = max(_line_len(p) for p in parts)
            if best is None or score < best[0]:
                best = (score, parts)
            return
        for end in range(start + 1, n - left + 2):
            rec(end, left - 1, [*acc, toks[start:end]])

    rec(0, k, [])
    return best[1] if best else None
