"""SFX density rules of a style (P16): spacing, maximum per 10 s and allowed cues."""

from __future__ import annotations

import itertools
from collections.abc import Sequence

from editoria.audio.sfx import CUES
from editoria.schemas import SfxCue, SfxPolicy, StylePreset

WINDOW_S = 10.0
_EPS = 1e-9


def check_sfx_density(cues: Sequence[SfxCue], style: StylePreset | SfxPolicy) -> list[str]:
    """Human-readable (Spanish) violations of the style's SFX policy; empty list = OK.

    An empty ``allowed_cues`` list means "no restriction" (only known cues are accepted).
    Windows are half-open ``[t, t + 10 s)`` anchored at each cue.
    """
    policy = style.sfx if isinstance(style, StylePreset) else style
    out: list[str] = []
    ordered = sorted(cues, key=lambda c: c.at)

    for c in ordered:
        if c.cue not in CUES:
            out.append(f"SFX en {c.at:.2f} s: el cue '{c.cue}' no existe ({', '.join(CUES)}).")
        elif policy.allowed_cues and c.cue not in policy.allowed_cues:
            out.append(
                f"SFX en {c.at:.2f} s: el cue '{c.cue}' no está permitido en este estilo "
                f"(permitidos: {', '.join(policy.allowed_cues)})."
            )

    for prev, cur in itertools.pairwise(ordered):
        gap = cur.at - prev.at
        if gap < policy.min_spacing_s - _EPS:
            out.append(
                f"SFX en {prev.at:.2f} s y {cur.at:.2f} s: separación de {gap:.2f} s "
                f"(mínimo {policy.min_spacing_s:.2f} s)."
            )

    reported: list[set[int]] = []
    for _i, first in enumerate(ordered):
        members = {j for j, c in enumerate(ordered) if first.at <= c.at < first.at + WINDOW_S}
        if len(members) > policy.max_per_10s and not any(members <= r for r in reported):
            reported.append(members)
            last = max(ordered[j].at for j in members)
            out.append(
                f"Hay {len(members)} SFX entre {first.at:.2f} s y {last:.2f} s "
                f"(máximo {policy.max_per_10s} cada 10 s)."
            )
    return out
