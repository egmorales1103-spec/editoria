"""Word grouping: timing inside word times, line/char limits, cps, camera cuts."""

from __future__ import annotations

from pathlib import Path

import pytest

from editoria.captions import group_words
from editoria.captions.grouping import MAX_LINGER_S
from editoria.captions.text import visible_len, wrap_tokens
from editoria.schemas import CaptionStyle, Transcript, Word, read_model
from editoria.util import resources

CUTS = [4.0, 7.85]


@pytest.fixture(scope="module")
def transcript(fixtures_dir: Path) -> Transcript:
    return read_model(fixtures_dir / "transcript_fixture.json", Transcript)


def _check_groups(words: list[Word], groups, style: CaptionStyle, cuts: list[float]) -> None:  # type: ignore[no-untyped-def]
    covered: list[int] = []
    for g, nxt in zip(groups, [*groups[1:], None], strict=False):
        first, last = words[g.word_ids[0]], words[g.word_ids[-1]]
        # timing within the words (start clamped to a cut only when the first word straddles it)
        assert first.start - 1e-6 <= g.start <= first.end
        assert g.end <= last.end + MAX_LINGER_S + 1e-6
        next_cut = min((c for c in cuts if c > g.start), default=float("inf"))
        assert g.end >= min(last.end, next_cut) - 1e-6
        assert g.end > g.start
        # never across a camera cut
        assert not any(g.start + 1e-6 < c < g.end - 1e-6 for c in cuts), (g.start, g.end)
        # ordered, no overlap
        if nxt is not None:
            assert g.end <= nxt.start + 1e-6
        # layout limits
        assert len(g.lines) <= style.max_lines
        assert all(len(line) <= style.max_chars_line for line in g.lines), g.lines
        assert len(g.word_ids) <= style.words_per_event
        # reading speed: within limits or explicitly warned (speech faster than reading)
        assert g.cps <= style.max_cps + 1e-3 or g.warnings
        covered.extend(g.word_ids)
    assert covered == sorted(covered) == list(range(len(words)))


@pytest.mark.parametrize("style_id", ["A", "B", "C"])
def test_fixture_groups_respect_style(transcript: Transcript, style_id: str) -> None:
    style = resources.load_style(style_id).captions
    groups = group_words(transcript.words, style, cuts=CUTS, duration=12.0)
    assert groups
    _check_groups(transcript.words, groups, style, CUTS)
    if style.case == "upper":
        assert all(g.text == g.text.upper() for g in groups)


def test_word_straddling_cut_is_clamped(transcript: Transcript) -> None:
    style = resources.load_style("A").captions
    groups = group_words(transcript.words, style, cuts=CUTS, duration=12.0)
    # "de" spans 3.80-4.16 across the 4.0 cut: its event must end at the cut
    g = next(g for g in groups if 8 in g.word_ids)
    assert g.end == pytest.approx(4.0)


def _slow_words(
    text: str, start: float = 0.5, step: float = 0.55, gap_every: int = 0
) -> list[Word]:
    words, t = [], start
    for i, tok in enumerate(text.split()):
        words.append(Word(text=tok, start=round(t, 3), end=round(t + step - 0.05, 3), prob=0.9))
        t += step + (0.4 if gap_every and (i + 1) % gap_every == 0 else 0.0)
    return words


def test_cps_and_chars_strict_on_normal_speech() -> None:
    words = _slow_words(
        "Hoy vamos a ver cómo organizar el trabajo del equipo, paso a paso. "
        "Primero ordenamos las tareas y después medimos los resultados reales"
    )
    for style_id in "ABC":
        style = resources.load_style(style_id).captions
        groups = group_words(words, style, cuts=[3.3], duration=60.0)
        _check_groups(words, groups, style, [3.3])
        assert all(g.cps <= style.max_cps + 1e-3 for g in groups)
        assert not any(g.warnings for g in groups)


def test_breaks_on_punctuation_and_pauses() -> None:
    words = _slow_words("Hola, equipo. Hoy automatizamos todo", gap_every=0)
    style = CaptionStyle(words_per_event=6, max_chars_line=40, max_lines=2)
    groups = group_words(words, style)
    assert [g.text for g in groups] == ["Hola,", "equipo.", "Hoy automatizamos todo"]
    paused = _slow_words("uno dos tres cuatro", gap_every=2)
    groups = group_words(paused, style)
    assert [g.text for g in groups] == ["uno dos", "tres cuatro"]


def test_linger_respects_cps_but_not_next_event() -> None:
    words = [
        Word(text="Automatización", start=0.0, end=0.3, prob=0.9),
        Word(text="hoy", start=2.0, end=2.3, prob=0.9),
    ]
    style = CaptionStyle(words_per_event=1, max_cps=17)
    g1, g2 = group_words(words, style)
    assert g1.end == pytest.approx(visible_len("Automatización") / 17)
    assert g1.end <= g2.start
    assert g1.cps <= 17 + 1e-3


def test_wrap_tokens_balanced() -> None:
    assert wrap_tokens(["Hoy", "te", "muestro"], 24, 2) == ["Hoy te muestro"]
    assert wrap_tokens(["las", "tareas", "repetitivas", "de"], 16, 2) == [
        "las tareas",
        "repetitivas de",
    ]
    assert wrap_tokens(["aaaa", "bbbb", "cccc"], 4, 2) is None
    assert wrap_tokens(["supercalifragilístico"], 10, 2) == ["supercalifragilístico"]


def test_sentence_case_only_first_word() -> None:
    words = _slow_words("hola equipo de ventas")
    style = CaptionStyle(case="sentence", words_per_event=4, max_chars_line=30)
    (g,) = group_words(words, style)
    assert g.text == "Hola equipo de ventas"
