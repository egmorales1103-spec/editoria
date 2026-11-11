"""Everything the linter needs besides the plan, loaded once from the project."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from editoria.schemas import AssetManifest, BrandProfile, EditPlan, StylePreset, Word
from editoria.util import resources
from editoria.util.files import read_csv_rows
from editoria.util.project import ProjectContext


@dataclass
class LintContext:
    duration: float | None = None
    fps: float = 30.0
    source_size: tuple[int, int] | None = None  # display width/height of the VIDEO_BASE
    style: StylePreset | None = None
    brand: BrandProfile | None = None
    project_brand: str | None = None
    registry: dict[str, dict[str, str]] | None = None  # None = registry file missing
    sfx_manifest: AssetManifest = field(default_factory=AssetManifest)
    external_manifest: AssetManifest = field(default_factory=AssetManifest)
    cuts: list[float] = field(default_factory=list)
    words: list[Word] | None = None
    load_errors: list[tuple[str, str]] = field(default_factory=list)  # (element, message)

    @property
    def frame(self) -> float:
        return 1.0 / self.fps if self.fps > 0 else 1 / 30

    # ------------------------------------------------------------------------------------
    @classmethod
    def from_project(cls, ctx: ProjectContext, plan: EditPlan) -> LintContext:
        lc = cls()
        try:
            probe = ctx.load_probe()
            lc.duration = probe.duration_s
            lc.fps = float(probe.fps_fraction)
            lc.source_size = (probe.display_width, probe.display_height)
        except FileNotFoundError:
            pass
        try:
            lc.style = resources.load_style(plan.style)
        except FileNotFoundError as exc:
            lc.load_errors.append(("style", str(exc)))
        try:
            lc.brand = resources.load_brand(plan.brand)
        except FileNotFoundError as exc:
            lc.load_errors.append(("brand", str(exc)))
        try:
            lc.project_brand = ctx.load_config().brand
        except FileNotFoundError:
            lc.project_brand = None
        reg = ctx.generations_registry
        if reg.exists():
            lc.registry = {r.get("id", "").strip(): r for r in read_csv_rows(reg)}
        lc.sfx_manifest = resources.load_sfx_manifest()
        lc.external_manifest = resources.load_external_manifest()
        cuts = ctx.load_cuts()
        lc.cuts = sorted(cuts.cuts) if cuts else []
        try:
            lc.words = ctx.load_transcript().words
        except FileNotFoundError:
            lc.words = None
        return lc


def template_schema(template: str) -> dict[str, Any] | None:
    """params.schema.json of a graphics template (A3), or the built-in fallback."""
    p = resources.graphics_templates_dir() / template / "params.schema.json"
    if p.exists():
        data: dict[str, Any] = json.loads(Path(p).read_text(encoding="utf-8"))
        return data
    return BUILTIN_PARAM_SCHEMAS.get(template)


def _obj(props: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "object", "properties": props, "required": required}


_STR = {"type": "string", "minLength": 1}
_STR_LIST = {"type": "array", "items": {"type": "string"}}

# Fallback when templates/graphics/<id>/params.schema.json is not present (conventions table).
# `data_source` is checked by P14, not here.
BUILTIN_PARAM_SCHEMAS: dict[str, dict[str, Any]] = {
    "titulo_gancho": _obj({"texto": _STR, "subtitulo": {"type": "string"}}, ["texto"]),
    "palabra_clave": _obj({"texto": _STR}, ["texto"]),
    "checklist": _obj(
        {
            "items": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 5},
            "titulo": {"type": "string"},
        },
        ["items"],
    ),
    "chat_burbujas": _obj(
        {
            "mensajes": {
                "type": "array",
                "minItems": 1,
                "maxItems": 4,
                "items": _obj({"lado": {"enum": ["izq", "der"]}, "texto": _STR}, ["lado", "texto"]),
            }
        },
        ["mensajes"],
    ),
    "notificacion": _obj({"app": _STR, "titulo": _STR, "texto": _STR}, ["app", "titulo", "texto"]),
    "dato_grafico": _obj(
        {
            "tipo": {"enum": ["barras", "contador"]},
            "valores": {"type": "array", "items": {"type": "number"}, "minItems": 1},
            "etiquetas": _STR_LIST,
            "unidad": {"type": "string"},
        },
        ["tipo", "valores"],
    ),
    "anotacion": _obj(
        {
            "tipo": {"enum": ["flecha", "circulo"]},
            "x": {"type": "number", "minimum": 0, "maximum": 1},
            "y": {"type": "number", "minimum": 0, "maximum": 1},
            "texto": {"type": "string"},
        },
        ["tipo", "x", "y"],
    ),
    "comparacion": _obj(
        {"antes": _STR, "despues": _STR, "titulo": {"type": "string"}}, ["antes", "despues"]
    ),
    "ui_demo": _obj({"titulo": _STR, "pasos": _STR_LIST}, ["titulo", "pasos"]),
    "cta_cierre": _obj({"texto": _STR, "accion": {"type": "string"}}, ["texto"]),
}
