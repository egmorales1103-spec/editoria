"""Linter rules (section 6 of the plan). Each rule: (plan, LintContext) -> list[Finding]."""

from __future__ import annotations

import itertools
import re
from collections.abc import Callable, Iterator
from typing import Any

import jsonschema

from editoria.captions.style import differing_fields, editorial_style
from editoria.captions.text import contains_phrase, has_figure, normalize
from editoria.policy.context import LintContext, template_schema
from editoria.schemas import AssetManifest, EditPlan, Finding, Severity
from editoria.util.files import fmt_ts
from editoria.util.geometry import base_transform

Rule = Callable[[EditPlan, LintContext], list[Finding]]

NATIVE_ZOOM_LIMIT = 1.25  # P07: max scale over native source pixels
EMOJI_RE = re.compile(r"^E0[1-6]$")
DATA_SOURCES = ("real", "ejemplo")


def finding(
    rule: str, severity: Severity, message: str, t: float | None = None, element: str | None = None
) -> Finding:
    return Finding(
        id=rule,
        severity=severity,
        message=message,
        t=None if t is None else round(t, 3),
        element=element,
    )


def _strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, list | tuple):
        for v in value:
            yield from _strings(v)


# ---- SCHEMA ------------------------------------------------------------------------------
def rule_schema(plan: EditPlan, lc: LintContext) -> list[Finding]:
    out: list[Finding] = [finding("SCHEMA", "ERROR", msg, element=el) for el, msg in lc.load_errors]
    if plan.captions.style != plan.style:
        out.append(
            finding(
                "SCHEMA",
                "WARN",
                f"captions.style ({plan.captions.style}) no coincide con el estilo del plan "
                f"({plan.style}).",
                element="captions",
            )
        )
    seen: dict[str, str] = {}
    for kind, ident in [("video", v.id) for v in plan.video] + [
        ("graphics", g.id) for g in plan.graphics
    ]:
        if ident in seen:
            out.append(finding("SCHEMA", "ERROR", f"El id '{ident}' está repetido.", element=ident))
        seen[ident] = kind
    for v in plan.video:
        if v.method == "reframe" and (v.zoom is None or v.zoom <= 1.0):
            out.append(
                finding(
                    "SCHEMA",
                    "ERROR",
                    "Un reencuadre necesita 'zoom' mayor que 1.",
                    t=v.in_,
                    element=v.id,
                )
            )
        if v.point is not None and not all(0.0 <= c <= 1.0 for c in v.point):
            out.append(
                finding(
                    "SCHEMA", "ERROR", "'point' debe estar normalizado entre 0 y 1.", v.in_, v.id
                )
            )
    if lc.words is not None:
        for i, e in enumerate(plan.captions.emphasis):
            if e.word >= len(lc.words):
                out.append(
                    finding(
                        "SCHEMA",
                        "ERROR",
                        f"El énfasis apunta a la palabra {e.word}, pero la transcripción tiene "
                        f"{len(lc.words)} palabras.",
                        element=f"emphasis[{i}]",
                    )
                )
    for i, t in enumerate(plan.captions.editorial_titles):
        if t.out <= t.in_:
            out.append(
                finding("SCHEMA", "ERROR", "'out' debe ser mayor que 'in'.", t.in_, f"titulo[{i}]")
            )
    for g in plan.graphics:
        if g.emoji is not None:
            if not EMOJI_RE.match(g.emoji):
                out.append(
                    finding(
                        "SCHEMA",
                        "ERROR",
                        f"Emoji desconocido '{g.emoji}' (se espera E01…E06).",
                        g.in_,
                        g.id,
                    )
                )
            continue
        assert g.template is not None
        schema = template_schema(g.template)
        if schema is None:
            out.append(
                finding("SCHEMA", "ERROR", f"La plantilla '{g.template}' no existe.", g.in_, g.id)
            )
            continue
        validator = jsonschema.Draft202012Validator(schema)
        for err in validator.iter_errors(g.params):
            path = ".".join(str(p) for p in err.absolute_path)
            if g.template == "dato_grafico" and "data_source" in (path + err.message):
                continue  # reported by P14
            where = f"params.{path}" if path else "params"
            out.append(
                finding(
                    "SCHEMA",
                    "ERROR",
                    f"Parámetros inválidos para '{g.template}' ({where}): {err.message}",
                    g.in_,
                    g.id,
                )
            )
    refs = {v.id for v in plan.video} | {g.id for g in plan.graphics}
    for i, cue in enumerate(plan.sfx):
        if cue.ref and cue.ref not in refs:
            out.append(
                finding(
                    "SCHEMA",
                    "WARN",
                    f"El SFX referencia '{cue.ref}', que no existe en el plan.",
                    cue.at,
                    f"sfx[{i}]",
                )
            )
    return out


# ---- P04 ---------------------------------------------------------------------------------
def rule_p04(plan: EditPlan, lc: LintContext) -> list[Finding]:
    out: list[Finding] = []
    dur = lc.duration
    tol = lc.frame + 1e-3
    if dur is None:
        return [
            finding(
                "P04",
                "ERROR",
                "No hay probe.json: sin la duración del VIDEO_BASE no se puede garantizar que "
                "nada pase del final. Ejecutá 'editoria probe <proyecto>' y volvé a validar.",
            )
        ]
    for v in plan.video:
        if v.out > dur + tol:
            out.append(
                finding(
                    "P04",
                    "ERROR",
                    f"El intervalo termina en {fmt_ts(v.out)}, después del final del video "
                    f"({fmt_ts(dur)}).",
                    v.out,
                    v.id,
                )
            )
    ordered = sorted(plan.video, key=lambda v: v.in_)
    for a, b in itertools.pairwise(ordered):
        if b.in_ < a.out - 1e-3:
            out.append(
                finding(
                    "P04",
                    "ERROR",
                    f"'{b.id}' se superpone con '{a.id}' en la pista de video (la línea de tiempo "
                    "del VIDEO_BASE no admite solapes).",
                    b.in_,
                    b.id,
                )
            )
    for v in plan.video:
        if v.method == "original":
            continue
        inside = [c for c in lc.cuts if v.in_ + tol < c < v.out - tol]
        if inside:
            out.append(
                finding(
                    "P04",
                    "WARN",
                    f"El intervalo cruza un corte de cámara en {fmt_ts(inside[0])}; conviene "
                    "dividirlo en el corte.",
                    inside[0],
                    v.id,
                )
            )
    for g in plan.graphics:
        if g.in_ >= dur or g.out > dur + tol:
            out.append(
                finding("P04", "ERROR", "El gráfico excede la duración del video.", g.in_, g.id)
            )
    for i, t in enumerate(plan.captions.editorial_titles):
        if t.in_ >= dur or t.out > dur + tol:
            out.append(
                finding(
                    "P04",
                    "ERROR",
                    "El título editorial excede la duración del video.",
                    t.in_,
                    f"titulo[{i}]",
                )
            )
    for i, cue in enumerate(plan.sfx):
        if cue.at >= dur:
            out.append(
                finding(
                    "P04",
                    "ERROR",
                    "El SFX empieza después del final del video.",
                    cue.at,
                    f"sfx[{i}]",
                )
            )
    if plan.window is not None:
        w0, w1 = plan.window
        if w1 <= w0 or w0 < 0 or w1 > dur + tol:
            out.append(
                finding(
                    "P04",
                    "ERROR",
                    f"La ventana {w0:g}-{w1:g} s no es válida para un video de {dur:.2f} s.",
                    w0,
                    "window",
                )
            )
    return out


# ---- P05 ---------------------------------------------------------------------------------
def rule_p05(plan: EditPlan, lc: LintContext) -> list[Finding]:
    out: list[Finding] = []
    for v in plan.video:
        if v.method != "generated":
            continue
        if lc.registry is None:
            out.append(
                finding(
                    "P05",
                    "ERROR",
                    f"La toma {v.shot} no puede usarse: no existe registro_generaciones.csv.",
                    v.in_,
                    v.id,
                )
            )
            continue
        row = lc.registry.get(str(v.shot))
        verdict = (row or {}).get("veredicto", "").strip()
        if row is None:
            out.append(
                finding(
                    "P05",
                    "ERROR",
                    f"La toma {v.shot} no figura en registro_generaciones.csv.",
                    v.in_,
                    v.id,
                )
            )
        elif verdict != "aceptado":
            out.append(
                finding(
                    "P05",
                    "ERROR",
                    f"La toma {v.shot} tiene veredicto '{verdict or 'pendiente'}'; solo se usan "
                    "tomas 'aceptado' (editoria shots verdict).",
                    v.in_,
                    v.id,
                )
            )
    return out


# ---- P07 ---------------------------------------------------------------------------------
def rule_p07(plan: EditPlan, lc: LintContext) -> list[Finding]:
    out: list[Finding] = []
    base_scale = 1.0
    if lc.source_size is not None:
        sw, sh = lc.source_size
        base_scale = base_transform(sw, sh, plan.canvas).scale
    style_max = lc.style.reframe.max_zoom if lc.style else None
    for v in plan.video:
        if v.method != "reframe" or v.zoom is None:
            continue
        native = v.zoom * base_scale
        if native > NATIVE_ZOOM_LIMIT + 1e-6:
            out.append(
                finding(
                    "P07",
                    "ERROR",
                    f"Zoom {v.zoom:g}× equivale a {native:.2f}× sobre los píxeles nativos "
                    f"(máximo {NATIVE_ZOOM_LIMIT}×): no se puede prometer detalle que no existe.",
                    v.in_,
                    v.id,
                )
            )
        elif style_max is not None and v.zoom > style_max + 1e-6:
            out.append(
                finding(
                    "P07",
                    "WARN",
                    f"Zoom {v.zoom:g}× supera el máximo del estilo ({style_max:g}×).",
                    v.in_,
                    v.id,
                )
            )
    return out


# ---- P13 ---------------------------------------------------------------------------------
def rule_p13(plan: EditPlan, lc: LintContext) -> list[Finding]:
    titles = plan.captions.editorial_titles
    if not titles or lc.style is None:
        return []
    out: list[Finding] = []
    title_style = editorial_style(lc.style)
    if not differing_fields(lc.style.captions, title_style):
        out.append(
            finding(
                "P13",
                "ERROR",
                f"El estilo {lc.style.id} usa para los títulos editoriales la misma tipografía "
                "que los subtítulos: deben distinguirse de lo que se dice (fuente, peso, tamaño, "
                "mayúsculas o contorno).",
                titles[0].in_,
                "titulo[0]",
            )
        )
    if lc.words:
        for i, t in enumerate(titles):
            spoken = " ".join(w.text for w in lc.words if w.end > t.in_ and w.start < t.out)
            if normalize(t.text) and contains_phrase(spoken, t.text):
                out.append(
                    finding(
                        "P13",
                        "WARN",
                        f"El título «{t.text}» repite lo que se dice: eso es un subtítulo, no un "
                        "título editorial.",
                        t.in_,
                        f"titulo[{i}]",
                    )
                )
    return out


# ---- P14 ---------------------------------------------------------------------------------
def rule_p14(plan: EditPlan, lc: LintContext) -> list[Finding]:
    out: list[Finding] = []
    for g in plan.graphics:
        if g.template is None:
            continue
        src = g.params.get("data_source")
        if g.template == "dato_grafico":
            if src not in DATA_SOURCES:
                out.append(
                    finding(
                        "P14",
                        "ERROR",
                        "dato_grafico exige data_source: 'real' (dato verificable) o 'ejemplo' "
                        "(se muestra la etiqueta «Ejemplo»). No se inventan métricas.",
                        g.in_,
                        g.id,
                    )
                )
            continue
        if src is None and any(has_figure(s) for s in _strings(g.params)):
            out.append(
                finding(
                    "P14",
                    "WARN",
                    f"'{g.template}' muestra cifras sin data_source: confirmá que el dato es real "
                    "o marcalo como ejemplo.",
                    g.in_,
                    g.id,
                )
            )
        elif src is not None and src not in DATA_SOURCES:
            out.append(
                finding("P14", "ERROR", "data_source debe ser 'real' o 'ejemplo'.", g.in_, g.id)
            )
    return out


# ---- P16 ---------------------------------------------------------------------------------
def rule_p16(plan: EditPlan, lc: LintContext) -> list[Finding]:
    if lc.style is None:
        return []
    out: list[Finding] = []
    gp, sp = lc.style.graphics, lc.style.sfx
    allowed = set(gp.allowed_templates)
    for g in plan.graphics:
        if g.template is not None and allowed and g.template not in allowed:
            out.append(
                finding(
                    "P16",
                    "ERROR",
                    f"La plantilla '{g.template}' no está permitida en el estilo {lc.style.id}.",
                    g.in_,
                    g.id,
                )
            )
    items = sorted(plan.graphics, key=lambda g: g.in_)
    flagged: set[str] = set()
    for g in items:
        active = [h for h in items if h.in_ <= g.in_ + 1e-6 and h.out > g.in_ + 1e-6]
        if len(active) > gp.max_simultaneous and g.id not in flagged:
            flagged.add(g.id)
            out.append(
                finding(
                    "P16",
                    "ERROR",
                    f"{len(active)} gráficos/emojis a la vez (máximo {gp.max_simultaneous} en el "
                    f"estilo {lc.style.id}): satura la pantalla.",
                    g.in_,
                    g.id,
                )
            )
    cues = sorted(enumerate(plan.sfx), key=lambda p: p[1].at)
    allowed_cues = set(sp.allowed_cues)
    for i, cue in cues:
        if allowed_cues and cue.cue not in allowed_cues:
            out.append(
                finding(
                    "P16",
                    "ERROR",
                    f"El sonido '{cue.cue}' no está permitido en el estilo {lc.style.id}.",
                    cue.at,
                    f"sfx[{i}]",
                )
            )
    for (_, a), (j, b) in itertools.pairwise(cues):
        if b.at - a.at < sp.min_spacing_s - 1e-6:
            out.append(
                finding(
                    "P16",
                    "ERROR",
                    f"Dos SFX separados por {b.at - a.at:.2f} s (mínimo {sp.min_spacing_s:g} s).",
                    b.at,
                    f"sfx[{j}]",
                )
            )
    reported = False
    for k, (_, a) in enumerate(cues):
        window = [c for _, c in cues[k:] if c.at < a.at + 10.0 - 1e-6]
        if len(window) > sp.max_per_10s and not reported:
            reported = True
            out.append(
                finding(
                    "P16",
                    "ERROR",
                    f"{len(window)} SFX en 10 s desde {fmt_ts(a.at)} (máximo {sp.max_per_10s}).",
                    a.at,
                    f"sfx[{cues[k][0]}]",
                )
            )
    return out


# ---- P17 ---------------------------------------------------------------------------------
def _licensed(manifests: list[AssetManifest], asset_id: str) -> bool:
    for m in manifests:
        entry = m.get(asset_id)
        if entry is not None and entry.license.strip():
            return True
    return False


def sfx_asset_id(cue: str, variant: int | None) -> str:
    return f"{cue}_{variant or 1}"


def rule_p17(plan: EditPlan, lc: LintContext) -> list[Finding]:
    out: list[Finding] = []
    for i, cue in enumerate(plan.sfx):
        aid = sfx_asset_id(cue.cue, cue.variant)
        if not _licensed([lc.sfx_manifest], aid):
            out.append(
                finding(
                    "P17",
                    "ERROR",
                    f"El SFX '{aid}' no figura con licencia en assets/sfx/manifest.yaml.",
                    cue.at,
                    f"sfx[{i}]",
                )
            )
    for g in plan.graphics:
        if g.emoji is not None and not _licensed([lc.external_manifest], g.emoji):
            out.append(
                finding(
                    "P17",
                    "ERROR",
                    f"El emoji '{g.emoji}' no figura con licencia en assets/externos.yaml.",
                    g.in_,
                    g.id,
                )
            )
    if plan.music is not None and not _licensed(
        [lc.sfx_manifest, lc.external_manifest], plan.music.asset_id
    ):
        out.append(
            finding(
                "P17",
                "ERROR",
                f"La música '{plan.music.asset_id}' no figura con licencia en ningún manifest.",
                element="music",
            )
        )
    return out


# ---- BRAND -------------------------------------------------------------------------------
def rule_brand(plan: EditPlan, lc: LintContext) -> list[Finding]:
    out: list[Finding] = []
    if lc.project_brand and plan.brand != lc.project_brand:
        out.append(
            finding(
                "BRAND",
                "WARN",
                f"El plan usa la marca '{plan.brand}' pero el proyecto es de '{lc.project_brand}'.",
                element="brand",
            )
        )
    if lc.brand is None:
        return out
    texts: list[tuple[str, float, str]] = []
    for g in plan.graphics:
        texts.extend((s, g.in_, g.id) for s in _strings(g.params))
    for i, t in enumerate(plan.captions.editorial_titles):
        texts.append((t.text, t.in_, f"titulo[{i}]"))
    for text, t0, el in texts:
        for claim in lc.brand.forbidden_claims:
            if contains_phrase(text, claim):
                out.append(
                    finding(
                        "BRAND",
                        "ERROR",
                        f"«{text}» contiene un mensaje prohibido por la marca: «{claim}».",
                        t0,
                        el,
                    )
                )
    return out


RULES: tuple[Rule, ...] = (
    rule_schema,
    rule_p04,
    rule_p05,
    rule_p07,
    rule_p13,
    rule_p14,
    rule_p16,
    rule_p17,
    rule_brand,
)
