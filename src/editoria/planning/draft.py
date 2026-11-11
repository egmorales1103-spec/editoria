"""Automatic plan draft for a style (A/B/C): captions, emphasis, hook graphic, reframes, SFX.

The draft is a starting point for the creative director: it only uses information that is
in the project (transcript, segments, cuts, face, brand glossary) and is built so that it
passes the policy linter.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

import yaml

from editoria.captions.text import contains_phrase, has_figure, normalize
from editoria.policy.rules import NATIVE_ZOOM_LIMIT, sfx_asset_id
from editoria.schemas import (
    AssetManifest,
    BrandProfile,
    Canvas,
    CaptionsSpec,
    EditPlan,
    Emphasis,
    FaceTrack,
    GraphicItem,
    Segment,
    SfxCue,
    StylePreset,
    VideoInterval,
    Word,
)
from editoria.util import resources
from editoria.util.geometry import base_transform
from editoria.util.project import ProjectContext

Window = tuple[float, float]

MIN_REFRAME_S = 1.5  # shorter reframes read as glitches: dropped
CADENCE_TOLERANCE = 0.75  # an idea change may trigger a reframe after 75 % of cadence_s
EMPHASIS_MIN_GAP_S = 1.0  # at most one emphasised term per second
HOOK_GRAPHIC_MAX_S = 2.5
HOOK_GRAPHIC_MIN_S = 0.8
HOOK_TITLE_MAX_WORDS = 6
SFX_GAIN = {"pop": -14.0, "click": -16.0, "whoosh": -16.0, "ding": -15.0}
GRAPHIC_CUE = "pop"
REFRAME_CUE = "whoosh"


# ---- emphasis ----------------------------------------------------------------------------
def find_emphasis(
    words: Sequence[Word], glossary: Sequence[str], min_gap: float = EMPHASIS_MIN_GAP_S
) -> list[int]:
    """Word indices of glossary terms (multi-word aware) and figures, thinned by ``min_gap``."""
    norm = [normalize(w.text) for w in words]
    terms = sorted(
        {tuple(normalize(g).split()) for g in glossary if normalize(g)}, key=len, reverse=True
    )
    picks: list[int] = []
    last = float("-inf")
    i = 0
    while i < len(words):
        span = 0
        for term in terms:
            if tuple(norm[i : i + len(term)]) == term:
                span = len(term)
                break
        if not span and norm[i] and has_figure(words[i].text):
            span = 1
        if span:
            if words[i].start - last >= min_gap:
                picks.extend(range(i, i + span))
                last = words[i].start
            i += span
            continue
        i += 1
    return picks


def _glossary_term_in(words: Sequence[Word], glossary: Sequence[str]) -> str | None:
    """Surface text (as spoken) of the first glossary term in ``words``."""
    ids = find_emphasis(words, glossary, min_gap=0.0)
    ids = [i for i in ids if not has_figure(words[i].text)] or ids
    if not ids:
        return None
    run = [ids[0]]
    for i in ids[1:]:
        if i == run[-1] + 1:
            run.append(i)
        else:
            break
    return _clean(" ".join(words[i].text for i in run))


def _clean(text: str) -> str:
    t = " ".join(text.split()).strip(" .,;:¿?¡!…\"'«»")
    return t[:1].upper() + t[1:] if t else t


# ---- context -----------------------------------------------------------------------------
@dataclass
class DraftInputs:
    duration: float
    source_size: tuple[int, int]
    words: list[Word]
    segments: list[Segment]
    cuts: list[float]
    face: FaceTrack | None
    brand: BrandProfile
    brand_slug: str
    sfx_manifest: AssetManifest

    @classmethod
    def from_project(cls, ctx: ProjectContext) -> DraftInputs:
        probe = ctx.load_probe()
        transcript = ctx.load_transcript()
        try:
            segments = ctx.load_segments().segments
        except FileNotFoundError:
            segments = [
                Segment(id=f"s{i + 1:02d}", start=s.start, end=s.end, text=s.text)
                for i, s in enumerate(transcript.segments)
            ]
        cuts = ctx.load_cuts()
        cfg = ctx.load_config()
        return cls(
            duration=probe.duration_s,
            source_size=(probe.display_width, probe.display_height),
            words=list(transcript.words),
            segments=sorted(segments, key=lambda s: s.start),
            cuts=sorted(cuts.cuts) if cuts else [],
            face=ctx.load_face(),
            brand=resources.load_brand(cfg.brand),
            brand_slug=cfg.brand,
            sfx_manifest=resources.load_sfx_manifest(),
        )


# ---- pieces ------------------------------------------------------------------------------
def _hook_segment(segments: Sequence[Segment], rng: Window) -> Segment | None:
    inside = [s for s in segments if s.end > rng[0] and s.start < rng[1]]
    return next((s for s in inside if s.role == "hook"), inside[0] if inside else None)


def _allowed(style: StylePreset, template: str) -> bool:
    allowed = style.graphics.allowed_templates
    return not allowed or template in allowed


def _template_cue(template: str) -> str | None:
    meta = resources.graphics_templates_dir() / template / "meta.yaml"
    if not meta.exists():
        return None
    data: Any = yaml.safe_load(meta.read_text(encoding="utf-8")) or {}
    cue = data.get("sfx_sugerido") if isinstance(data, dict) else None
    return str(cue) if cue else None


def hook_graphic(
    inp: DraftInputs, style: StylePreset, rng: Window
) -> tuple[GraphicItem | None, str]:
    hook = _hook_segment(inp.segments, rng)
    if hook is None:
        return None, "sin segmentos en la ventana: no hay gráfico de gancho"
    hook_words = [w for w in inp.words if w.end > hook.start and w.start < hook.end]
    term = _glossary_term_in(hook_words, inp.brand.glossary)
    template: str | None = None
    text = ""
    if term and _allowed(style, "palabra_clave"):
        template, text = "palabra_clave", term
    elif _allowed(style, "titulo_gancho"):
        toks = (" ".join(w.text for w in hook_words) or hook.text).split()
        text = _clean(" ".join(toks[:HOOK_TITLE_MAX_WORDS]))
        template = "titulo_gancho" if text else None
    if template is None:
        return None, "el estilo no permite palabra_clave ni titulo_gancho"
    if any(contains_phrase(text, c) for c in inp.brand.forbidden_claims):
        return None, "el texto del gancho contiene un mensaje prohibido por la marca"
    start = max(hook.start, rng[0])
    end = min(hook.end, start + HOOK_GRAPHIC_MAX_S, rng[1], inp.duration)
    if end - start < HOOK_GRAPHIC_MIN_S:
        end = min(start + HOOK_GRAPHIC_MIN_S, rng[1], inp.duration)
    if end <= start:
        return None, "el gancho es demasiado corto para un gráfico"
    item = GraphicItem(
        id="g01",
        template=template,
        in_=round(start, 3),
        out=round(end, 3),
        zone="upper",
        params={"texto": text},
    )
    return item, f"gráfico '{template}' en el gancho ({hook.id})"


def reframe_zoom(inp: DraftInputs, style: StylePreset, canvas: Canvas) -> float:
    sw, sh = inp.source_size
    base_scale = base_transform(sw, sh, canvas).scale
    return round(min(style.reframe.max_zoom, NATIVE_ZOOM_LIMIT / base_scale), 3)


def plan_video(
    inp: DraftInputs, style: StylePreset, rng: Window, canvas: Canvas
) -> list[VideoInterval]:
    """Original/reframe alternation at idea changes (segment starts) every ~cadence_s.
    A reframe always ends at a camera cut: it never spans one."""
    a, b = rng
    zoom = reframe_zoom(inp, style, canvas)
    reframes: list[tuple[float, float]] = []
    if zoom >= 1.03:
        threshold = style.reframe.cadence_s * CADENCE_TOLERANCE
        points: list[tuple[float, Literal["cut", "idea"]]] = [
            (c, "cut") for c in inp.cuts if a < c < b
        ]
        points += [(s.start, "idea") for s in inp.segments if a < s.start < b]
        points.sort(key=lambda p: (p[0], 0 if p[1] == "cut" else 1))
        open_at: float | None = None
        last_change = a
        for t, kind in points:
            if kind == "cut":  # a reframe never spans a camera cut: close it there
                if open_at is not None:
                    reframes.append((open_at, t))
                    open_at = None
                    last_change = t
            elif t - last_change >= threshold - 1e-6:
                if open_at is None:
                    open_at = t
                else:
                    reframes.append((open_at, t))
                    open_at = None
                last_change = t
        if open_at is not None:
            reframes.append((open_at, b))
    reframes = [(s, e) for s, e in reframes if e - s >= MIN_REFRAME_S]

    anchor: Literal["face", "center"] = (
        "face" if inp.face is not None and not inp.face.estimated else "center"
    )
    motion: Literal["cut", "push"] = "push" if style.id == "B" else "cut"
    out: list[VideoInterval] = []
    t = a

    def add(start: float, end: float, reframe: bool) -> None:
        if end - start <= 1e-3:
            return
        vid = f"v{len(out) + 1:02d}"
        if reframe:
            out.append(
                VideoInterval(
                    id=vid,
                    in_=round(start, 3),
                    out=round(end, 3),
                    method="reframe",
                    zoom=zoom,
                    anchor=anchor,
                    motion=motion,
                )
            )
        else:
            out.append(
                VideoInterval(id=vid, in_=round(start, 3), out=round(end, 3), method="original")
            )

    for s, e in reframes:
        add(t, s, False)
        add(s, e, True)
        t = e
    add(t, b, False)
    return out


def _licensed_cue(manifest: AssetManifest, cue: str) -> bool:
    entry = manifest.get(sfx_asset_id(cue, None))
    return entry is not None and bool(entry.license.strip())


def plan_sfx(
    inp: DraftInputs,
    style: StylePreset,
    graphics: Sequence[GraphicItem],
    video: Sequence[VideoInterval],
    rng: Window,
) -> tuple[list[SfxCue], list[str]]:
    """SFX only on graphic entries and reframe starts, within the style's density rules."""
    notes: list[str] = []
    allowed = set(style.sfx.allowed_cues)
    cands: list[tuple[float, str, str]] = []
    for g in graphics:
        cue = (_template_cue(g.template) if g.template else None) or GRAPHIC_CUE
        cands.append((g.in_, cue, g.id))
    for v in video:
        if v.method == "reframe":
            cands.append((max(v.in_ - 0.02, rng[0]), REFRAME_CUE, v.id))
    cands.sort()
    chosen: list[SfxCue] = []
    for at, cue, ref in cands:
        if allowed and cue not in allowed:
            continue
        if not _licensed_cue(inp.sfx_manifest, cue):
            notes.append(f"sin SFX '{cue}' en {ref}: falta en assets/sfx/manifest.yaml")
            continue
        if chosen and at - chosen[-1].at < style.sfx.min_spacing_s:
            continue
        recent = [c for c in chosen if at - c.at < 10.0]
        if len(recent) >= style.sfx.max_per_10s:
            continue
        chosen.append(SfxCue(cue=cue, at=round(at, 3), gain_db=SFX_GAIN.get(cue, -15.0), ref=ref))
    return chosen, notes


# ---- public ------------------------------------------------------------------------------
def draft_from_inputs(
    inp: DraftInputs, style: StylePreset, window: Window | None = None, version: str = "V1"
) -> EditPlan:
    canvas = Canvas()
    rng: Window = (0.0, inp.duration)
    if window is not None:
        a, b = window
        rng = (max(0.0, a), min(inp.duration, b))
        if rng[1] <= rng[0]:
            raise ValueError(
                f"La ventana {a:g}-{b:g} s no es válida para un video de {inp.duration:.2f} s."
            )
    emphasis = [Emphasis(word=i) for i in find_emphasis(inp.words, inp.brand.glossary)]
    graphic, g_note = hook_graphic(inp, style, rng)
    graphics = [graphic] if graphic else []
    video = plan_video(inp, style, rng, canvas)
    sfx, sfx_notes = plan_sfx(inp, style, graphics, video, rng)
    n_reframes = sum(1 for v in video if v.method == "reframe")
    notes = [
        f"Borrador automático del estilo {style.id} ({style.name}).",
        f"Subtítulos de todo el audio con {len(emphasis)} palabras en énfasis (glosario y cifras).",
        g_note[:1].upper() + g_note[1:] + ".",
        f"{n_reframes} reencuadre(s) cada ~{style.reframe.cadence_s:g} s en cambios de idea, "
        "sin cruzar cortes de cámara.",
        f"{len(sfx)} SFX solo en entradas de gráficos y reencuadres.",
    ]
    if sfx_notes:
        notes.append("Avisos: " + "; ".join(dict.fromkeys(sfx_notes)) + ".")
    notes.append("Revisá roles e intención de los segmentos antes de aprobar.")
    return EditPlan(
        version=version,
        style=style.id,
        brand=inp.brand_slug,
        canvas=canvas,
        video=video,
        captions=CaptionsSpec(style=style.id, emphasis=emphasis),
        graphics=graphics,
        sfx=sfx,
        notes=" ".join(notes),
        window=(round(rng[0], 3), round(rng[1], 3)) if window is not None else None,
    )


def draft_plan(
    ctx: ProjectContext, style: StylePreset, window: Window | None = None, version: str = "V1"
) -> EditPlan:
    return draft_from_inputs(DraftInputs.from_project(ctx), style, window, version)


def parse_window(text: str) -> Window:
    """'3.5-9' -> (3.5, 9.0). Accepts ',' as decimal separator."""
    parts = text.replace(",", ".").split("-")
    if len(parts) != 2:
        raise ValueError(f"Ventana inválida '{text}': usá el formato inicio-fin (por ej. 2-9.5).")
    a, b = (float(p.strip()) for p in parts)
    if b <= a:
        raise ValueError(f"Ventana inválida '{text}': el fin debe ser mayor que el inicio.")
    return a, b
