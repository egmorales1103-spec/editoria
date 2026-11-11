"""check_sfx_density: spacing, maximum per 10 s and allowed cues (positive and negative)."""

from __future__ import annotations

from editoria.audio import check_sfx_density
from editoria.schemas import SfxCue, SfxPolicy, StylePreset
from editoria.util import resources


def cues(*items: tuple[str, float]) -> list[SfxCue]:
    return [SfxCue(cue=c, at=t) for c, t in items]


POLICY = SfxPolicy(max_per_10s=2, min_spacing_s=2.0, allowed_cues=["pop", "click", "whoosh"])


def test_clean_plan_has_no_findings() -> None:
    assert check_sfx_density(cues(("pop", 0.3), ("whoosh", 2.5), ("click", 12.0)), POLICY) == []


def test_empty_plan_ok() -> None:
    assert check_sfx_density([], POLICY) == []


def test_spacing_violation() -> None:
    msgs = check_sfx_density(cues(("pop", 1.0), ("click", 2.0)), POLICY)
    assert len(msgs) == 1 and "separación" in msgs[0] and "2.00" in msgs[0]


def test_spacing_exactly_minimum_is_ok() -> None:
    assert check_sfx_density(cues(("pop", 1.0), ("click", 3.0)), POLICY) == []


def test_max_per_10s_violation() -> None:
    policy = SfxPolicy(max_per_10s=2, min_spacing_s=1.0, allowed_cues=[])
    msgs = check_sfx_density(cues(("pop", 0.0), ("click", 3.0), ("pop", 6.0)), policy)
    assert len(msgs) == 1 and "3 SFX" in msgs[0] and "cada 10 s" in msgs[0]


def test_max_per_10s_window_is_half_open() -> None:
    policy = SfxPolicy(max_per_10s=2, min_spacing_s=1.0, allowed_cues=[])
    assert check_sfx_density(cues(("pop", 0.0), ("click", 5.0), ("pop", 10.0)), policy) == []


def test_disallowed_and_unknown_cues() -> None:
    msgs = check_sfx_density(cues(("ding", 1.0), ("trompeta", 5.0)), POLICY)
    assert any("'ding' no está permitido" in m for m in msgs)
    assert any("'trompeta' no existe" in m for m in msgs)


def test_empty_allowed_cues_means_unrestricted() -> None:
    policy = SfxPolicy(max_per_10s=5, min_spacing_s=0.0, allowed_cues=[])
    assert check_sfx_density(cues(("teclado", 1.0)), policy) == []


def test_accepts_real_style_presets() -> None:
    style: StylePreset = resources.load_style("A")
    assert check_sfx_density(cues(("pop", 0.3), ("whoosh", 2.5)), style) == []
    bad = cues(("pop", 0.3), ("pop", 0.9), ("click", 1.2), ("impacto_suave", 20.0))
    msgs = check_sfx_density(bad, style)
    assert any("separación" in m for m in msgs)
    assert any("impacto_suave" in m for m in msgs)
