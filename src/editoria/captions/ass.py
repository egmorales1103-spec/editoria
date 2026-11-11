"""ASS (libass) document assembly: styles, colours, override tags and dialogue lines."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from editoria.schemas import Canvas, CaptionStyle

STYLE_FORMAT = (
    "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
    "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
    "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding"
)
EVENT_FORMAT = "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"


def hex_rgb(color: str) -> tuple[int, int, int]:
    c = color.strip().lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    if len(c) != 6:
        raise ValueError(f"Color inválido '{color}' (se espera #RRGGBB).")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def ass_color(color: str, alpha: int = 0) -> str:
    """'#RRGGBB' -> '&HAABBGGRR' (style fields)."""
    r, g, b = hex_rgb(color)
    return f"&H{alpha:02X}{b:02X}{g:02X}{r:02X}"


def ass_inline_color(color: str) -> str:
    """'#RRGGBB' -> '&HBBGGRR&' (override tags such as \\1c)."""
    r, g, b = hex_rgb(color)
    return f"&H{b:02X}{g:02X}{r:02X}&"


def luminance(color: str) -> float:
    r, g, b = (v / 255 for v in hex_rgb(color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_text(box_color: str) -> str:
    return "#000000" if luminance(box_color) > 0.5 else "#FFFFFF"


def ass_time(t: float) -> str:
    cs = max(round(t * 100), 0)
    h, rem = divmod(cs, 360_000)
    m, rem = divmod(rem, 6000)
    s, cs = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def escape_text(text: str) -> str:
    """Neutralise ASS control characters in user text."""
    return text.replace("\\", "/").replace("{", "(").replace("}", ")")


@dataclass(frozen=True)
class AssStyle:
    name: str
    font: str
    style: CaptionStyle
    primary: str  # #RRGGBB text
    secondary: str  # #RRGGBB (karaoke)
    outline_color: str  # #RRGGBB border (or box when boxed)
    back_color: str  # #RRGGBB shadow
    margin_l: int
    margin_r: int
    margin_v: int
    boxed: bool = False
    box_padding: float = 0.0

    def line(self) -> str:
        s = self.style
        bold = -1 if s.weight >= 600 else 0
        border_style = 3 if self.boxed else 1
        outline = self.box_padding if self.boxed else s.outline
        return (
            f"Style: {self.name},{self.font},{s.size},{ass_color(self.primary)},"
            f"{ass_color(self.secondary)},{ass_color(self.outline_color)},"
            f"{ass_color(self.back_color, 0x60)},{bold},0,0,0,100,100,0,0,{border_style},"
            f"{outline:g},{s.shadow:g},5,{self.margin_l},{self.margin_r},{self.margin_v},1"
        )


@dataclass(frozen=True)
class Dialogue:
    start: float
    end: float
    style: str
    text: str  # already contains override tags
    layer: int = 0

    def line(self) -> str:
        return (
            f"Dialogue: {self.layer},{ass_time(self.start)},{ass_time(self.end)},{self.style},"
            f",0,0,0,,{self.text}"
        )


def document(canvas: Canvas, styles: Sequence[AssStyle], dialogues: Sequence[Dialogue]) -> str:
    out = [
        "[Script Info]",
        "; Generado por EditorIA (editoria captions build)",
        "Title: EditorIA",
        "ScriptType: v4.00+",
        f"PlayResX: {canvas.width}",
        f"PlayResY: {canvas.height}",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "YCbCr Matrix: TV.709",
        "",
        "[V4+ Styles]",
        STYLE_FORMAT,
        *(s.line() for s in styles),
        "",
        "[Events]",
        EVENT_FORMAT,
        *(d.line() for d in sorted(dialogues, key=lambda d: (d.start, d.layer))),
        "",
    ]
    return "\n".join(out)


def pop_tags() -> str:
    return r"\fscx70\fscy70\t(0,90,\fscx110\fscy110)\t(90,170,\fscx100\fscy100)"


def fade_tags(duration: float) -> str:
    ms = int(min(120, max(duration * 1000 / 3, 0)))
    return rf"\fad({ms},{ms})"


def animation_tags(style: CaptionStyle, duration: float) -> str:
    if style.animation == "pop":
        return pop_tags()
    if style.animation == "fade":
        return fade_tags(duration)
    return ""
