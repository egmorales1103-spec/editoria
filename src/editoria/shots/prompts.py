"""Prompt template of section 7 of the master prompt (English, as used in Higgsfield)."""

from __future__ import annotations

PROMPT_TEMPLATE = (
    "Use the uploaded source video as the authoritative reference. Create a subtle "
    "complementary shot of the same person in the exact same recorded environment. "
    "Requested change: {change}. Preserve the person's identity, face, skin texture, "
    "hairstyle, clothing, accessories, anatomy, gestures and timing. Preserve every visible "
    "background object, its placement, geometry, color, texture and lighting. Do not add, "
    "remove, replace or redesign any part of the room. Do not reveal areas outside the "
    "original recording. Preserve the original speech timing and mouth motion where supported. "
    "No new dialogue. Keep natural, realistic motion. If this change requires inventing the "
    "environment, do not expand the scene; keep the original framing."
)

NEGATIVE_CONSTRAINTS = (
    "background replacement, invented room details, new objects, moved furniture, lighting "
    "changes, face drift, beauty filter, altered clothes, deformed hands, extra fingers, "
    "lip-sync drift, flicker, warping, artificial skin, wide camera orbit, outpainting, "
    "new dialogue"
)

# Requests that the master prompt (section 5) forbids; used only to warn, never to decide.
RISKY_CHANGE_HINTS: tuple[str, ...] = (
    "órbita",
    "orbita",
    "orbit",
    "360",
    "180",
    "fondo nuevo",
    "cambiar el fondo",
    "cambio de fondo",
    "nueva habitación",
    "nueva habitacion",
    "relight",
    "nueva luz",
    "iluminación nueva",
    "outpaint",
    "expandir",
    "ropa nueva",
    "cambiar la ropa",
    "embellec",
)


def build_prompt(change: str) -> str:
    """Fill the template with ONE small framing variation (trailing period removed)."""
    return PROMPT_TEMPLATE.format(change=change.strip().rstrip(".").strip())


def risky_hints(change: str) -> list[str]:
    low = change.lower()
    return [h for h in RISKY_CHANGE_HINTS if h in low]
