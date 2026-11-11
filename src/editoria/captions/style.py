"""Derived caption styles: editorial-title style and the P13 distinctness check."""

from __future__ import annotations

from editoria.schemas import CaptionStyle, StylePreset

# Attributes that make two text styles visibly different (P13). Position and colour alone
# are not enough: a title must not read like a subtitle.
DISTINCT_FIELDS: tuple[str, ...] = ("font", "weight", "size", "case", "outline")


def editorial_style(style: StylePreset) -> CaptionStyle:
    """The preset's editorial-title style, or a derived one guaranteed distinct."""
    if style.editorial_titles is not None:
        return style.editorial_titles
    base = style.captions
    return base.model_copy(
        update={
            "weight": 800 if base.weight < 800 else 600,
            "size": max(int(base.size * 0.82), 36),
            "case": "upper" if base.case != "upper" else "sentence",
            "outline": 0.0,
            "shadow": 0.0,
            "animation": "fade",
            "position_y": 0.2,
            "words_per_event": 8,
            "max_cps": max(base.max_cps, 20.0),
        }
    )


def differing_fields(a: CaptionStyle, b: CaptionStyle) -> list[str]:
    return [f for f in DISTINCT_FIELDS if getattr(a, f) != getattr(b, f)]


def is_distinct(captions: CaptionStyle, titles: CaptionStyle) -> bool:
    return bool(differing_fields(captions, titles))
