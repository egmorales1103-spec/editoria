"""AssCaptionBuilder (implements contracts.CaptionBuilder) and build_for_version()."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from editoria.captions import ass
from editoria.captions.fonts import resolve_family
from editoria.captions.formats import to_srt, to_vtt, write_events_json, write_text
from editoria.captions.grouping import NBSP, WordGroup, group_words
from editoria.captions.layout import (
    Placement,
    block_size,
    box_at,
    face_avoid_boxes,
    stable_placement,
)
from editoria.captions.style import editorial_style
from editoria.captions.text import apply_case, wrap_tokens
from editoria.schemas import (
    Box,
    BrandProfile,
    Canvas,
    CaptionArtifacts,
    CaptionEvent,
    CaptionStyle,
    EditorialTitle,
    Emphasis,
    StylePreset,
    Transcript,
)
from editoria.util import resources
from editoria.util.geometry import zone_box
from editoria.util.log import get_logger, warn
from editoria.util.project import ProjectContext

HighlightMode = Literal["auto", "karaoke", "emphasis"]

ASS_FILE = "subtitulos.ass"
SRT_FILE = "subtitulos.srt"
VTT_FILE = "subtitulos.vtt"
JSON_FILE = "subtitulos.json"

TITLE_BOX_PADDING = 18.0
_log = get_logger("captions")


def _resolve_color(brand: BrandProfile, token: str | None, default: str) -> str:
    if not token:
        return default
    try:
        return brand.colors.resolve(token)
    except AttributeError:
        _log.warning("unknown colour token %s", token)
        return default


class AssCaptionBuilder:
    """Groups words into events and writes subtitulos.ass/.srt/.vtt/.json.

    ``highlight_mode``: ``karaoke`` colours the active word as it is spoken; ``emphasis``
    colours only the plan's emphasis words; ``auto`` = karaoke for ``pop`` styles.
    Extra keyword arguments of :meth:`build` (cuts, editorial titles, duration) are optional
    so the class still satisfies :class:`editoria.contracts.CaptionBuilder`.
    """

    def __init__(
        self, fonts_dir: Path | None = None, highlight_mode: HighlightMode = "auto"
    ) -> None:
        self.fonts_dir = fonts_dir
        self.highlight_mode: HighlightMode = highlight_mode
        self.warnings: list[str] = []
        self.placement: Placement | None = None

    # ------------------------------------------------------------------------------------
    def _warn(self, msg: str) -> None:
        if msg not in self.warnings:
            self.warnings.append(msg)
            warn(msg)

    def _mode(self, style: CaptionStyle) -> Literal["karaoke", "emphasis"]:
        if self.highlight_mode == "auto":
            return "karaoke" if style.animation == "pop" else "emphasis"
        return self.highlight_mode

    # ------------------------------------------------------------------------------------
    def build(
        self,
        transcript: Transcript,
        style: StylePreset,
        brand: BrandProfile,
        canvas: Canvas,
        avoid: list[Box],
        emphasis: list[Emphasis],
        out_dir: Path,
        *,
        cuts: Sequence[float] = (),
        editorial_titles: Sequence[EditorialTitle] = (),
        duration: float | None = None,
    ) -> CaptionArtifacts:
        self.warnings = []
        cap = style.captions
        title_style = editorial_style(style)
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        cap_font, w1 = resolve_family([cap.font, brand.fonts.body], self.fonts_dir)
        title_font, w2 = resolve_family([title_style.font, brand.fonts.heading], self.fonts_dir)
        for font_warning in (w1, w2):
            if font_warning:
                self._warn(font_warning)

        text_color = brand.colors.text
        outline_color = brand.colors.bg
        highlight = _resolve_color(brand, cap.highlight, brand.colors.accent)
        safe = canvas.safe
        cap_name = style.id
        title_name = f"{style.id}_titulo"
        title_box_color = _resolve_color(brand, title_style.highlight, brand.colors.accent)
        styles = [
            ass.AssStyle(
                name=cap_name,
                font=cap_font,
                style=cap,
                primary=text_color,
                secondary=highlight,
                outline_color=outline_color,
                back_color=outline_color,
                margin_l=safe.left,
                margin_r=safe.right,
                margin_v=safe.bottom,
            ),
            ass.AssStyle(
                name=title_name,
                font=title_font,
                style=title_style,
                primary=ass.contrast_text(title_box_color),
                secondary=title_box_color,
                outline_color=title_box_color,
                back_color=outline_color,
                margin_l=safe.left,
                margin_r=safe.right,
                margin_v=safe.top,
                boxed=True,
                box_padding=TITLE_BOX_PADDING,
            ),
        ]

        placement = stable_placement(cap, canvas, avoid)
        self.placement = placement
        if placement.warning:
            self._warn(placement.warning)

        groups = group_words(transcript.words, cap, cuts=cuts, duration=duration)
        group_warnings = [w for g in groups for w in g.warnings]
        if group_warnings:
            more = f" (y {len(group_warnings) - 3} más)" if len(group_warnings) > 3 else ""
            self._warn(
                f"Subtítulos: {len(group_warnings)} eventos fuera de límites de lectura: "
                + "; ".join(group_warnings[:3])
                + more
            )
        emph_color = {e.word: _resolve_color(brand, e.color, highlight) for e in emphasis}
        mode = self._mode(cap)

        dialogues: list[ass.Dialogue] = []
        events: list[CaptionEvent] = []
        for g in groups:
            body = self._event_body(g, transcript, cap, mode, text_color, highlight, emph_color)
            prefix = (
                rf"\an5\pos({placement.cx},{placement.cy})"
                + (rf"\b{cap.weight}" if cap.weight not in (400, 700) else "")
                + ass.animation_tags(cap, g.end - g.start)
            )
            dialogues.append(
                ass.Dialogue(
                    start=g.start, end=g.end, style=cap_name, text="{" + prefix + "}" + body
                )
            )
            w, h = block_size(g.lines, cap)
            events.append(
                CaptionEvent(
                    start=round(g.start, 3),
                    end=round(g.end, 3),
                    text=g.text,
                    word_ids=g.word_ids,
                    box=box_at(placement.cx, placement.cy, w, h),
                )
            )

        title_events: list[CaptionEvent] = []
        for t in editorial_titles:
            end = min(t.out, duration) if duration is not None else t.out
            if end <= t.in_:
                continue
            toks = apply_case(t.text, title_style.case).split()
            lines = wrap_tokens(toks, title_style.max_chars_line, title_style.max_lines) or [
                " ".join(toks)
            ]
            w, h = block_size(lines, title_style)
            pad = int(TITLE_BOX_PADDING)
            zb = zone_box(t.zone, canvas, w + 2 * pad, h + 2 * pad)
            cx, cy = zb.x + zb.w // 2, zb.y + zb.h // 2
            text = r"\N".join(ass.escape_text(line) for line in lines)
            prefix = rf"\an5\pos({cx},{cy})" + ass.animation_tags(title_style, end - t.in_)
            dialogues.append(
                ass.Dialogue(
                    start=t.in_, end=end, style=title_name, text="{" + prefix + "}" + text, layer=1
                )
            )
            title_events.append(
                CaptionEvent(
                    start=round(t.in_, 3),
                    end=round(end, 3),
                    text="\n".join(lines),
                    box=box_at(cx, cy, w + 2 * pad, h + 2 * pad),
                    editorial=True,
                )
            )

        ass_path = write_text(out_dir / ASS_FILE, ass.document(canvas, styles, dialogues))
        srt_path = write_text(out_dir / SRT_FILE, to_srt(events))
        vtt_path = write_text(out_dir / VTT_FILE, to_vtt(events))
        all_events = sorted([*events, *title_events], key=lambda e: (e.start, e.editorial))
        write_events_json(out_dir / JSON_FILE, all_events)
        return CaptionArtifacts(ass=ass_path, srt=srt_path, vtt=vtt_path, events=all_events)

    # ------------------------------------------------------------------------------------
    @staticmethod
    def _event_body(
        g: WordGroup,
        transcript: Transcript,
        cap: CaptionStyle,
        mode: Literal["karaoke", "emphasis"],
        text_color: str,
        highlight: str,
        emph_color: dict[int, str],
    ) -> str:
        words = transcript.words
        ids = list(g.word_ids)
        pos = 0
        out_lines: list[str] = []
        for line in g.lines:
            tokens = line.split(" ")
            parts: list[str] = []
            for tok in tokens:
                wid = ids[pos]
                pos += 1
                shown = ass.escape_text(tok.replace(NBSP, " "))
                base = emph_color.get(wid, text_color)
                if mode == "karaoke":
                    w = words[wid]
                    a = max(round((max(w.start, g.start) - g.start) * 1000), 0)
                    nxt = words[ids[pos]].start if pos < len(ids) else w.end
                    b = max(round((min(nxt, g.end) - g.start) * 1000), a + 1)
                    tag = (
                        rf"{{\1c{ass.ass_inline_color(base)}"
                        rf"\t({a},{a + 1},\1c{ass.ass_inline_color(highlight)})"
                        rf"\t({b},{b + 1},\1c{ass.ass_inline_color(base)})}}"
                    )
                    parts.append(tag + shown)
                elif wid in emph_color:
                    parts.append(
                        rf"{{\1c{ass.ass_inline_color(base)}}}{shown}"
                        rf"{{\1c{ass.ass_inline_color(text_color)}}}"
                    )
                else:
                    parts.append(shown)
            out_lines.append(" ".join(parts))
        return r"\N".join(out_lines)


# ----------------------------------------------------------------------------------------
def build_for_version(
    ctx: ProjectContext, version: str, builder: AssCaptionBuilder | None = None
) -> CaptionArtifacts:
    """Read <version>/plan.yaml and write the caption files into that version folder."""
    plan = ctx.load_plan(version)
    style = ctx.load_style(plan.captions.style)
    brand = resources.load_brand(plan.brand)
    transcript = ctx.load_transcript()
    cuts_list = ctx.load_cuts()
    cuts = cuts_list.cuts if cuts_list else []
    duration: float | None = None
    try:
        duration = ctx.load_probe().duration_s
    except FileNotFoundError:
        duration = None
    avoid = face_avoid_boxes(ctx.load_face(), plan.canvas, plan.video)
    b = builder or AssCaptionBuilder(fonts_dir=resources.fonts_dir())
    if not plan.captions.enabled:
        transcript = Transcript(language=transcript.language, model=transcript.model, words=[])
    return b.build(
        transcript,
        style,
        brand,
        plan.canvas,
        avoid,
        list(plan.captions.emphasis),
        ctx.version_dir(version),
        cuts=cuts,
        editorial_titles=plan.captions.editorial_titles,
        duration=duration,
    )
