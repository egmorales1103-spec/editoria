"""Graphic template discovery, metadata and parameter validation.

A template lives in ``templates/graphics/<id>/`` with three files:

- ``template.html``: Jinja2 (autoescaped) that extends ``_base.html``.
- ``params.schema.json``: JSON Schema of the parameters (``examples[0]`` = sample params).
- ``meta.yaml``: :class:`TemplateMeta`.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Literal, cast

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from pydantic import BaseModel, ConfigDict, Field

from editoria.schemas import Zone
from editoria.util import resources

TEMPLATE_FILE = "template.html"
SCHEMA_FILE = "params.schema.json"
META_FILE = "meta.yaml"
BASE_FILE = "_base.html"


class GraphicsError(RuntimeError):
    """Base error of the graphics module (messages in Spanish)."""


class TemplateNotFound(GraphicsError):
    pass


class GraphicsParamsError(GraphicsError, ValueError):
    pass


def _default_zones() -> list[Zone]:
    return ["upper"]


class TemplateMeta(BaseModel):
    """Contents of ``meta.yaml``."""

    model_config = ConfigDict(extra="forbid")

    id: str
    nombre: str
    descripcion: str = ""
    size: tuple[int, int]  # CSS px at a 1080-wide canvas
    duracion_s: float = Field(gt=0)
    zonas: list[Zone] = Field(default_factory=_default_zones)
    sfx_sugerido: str | None = None
    etiquetas_obligatorias: list[str] = Field(default_factory=list)
    # "zona": placed with util.geometry.zone_box. "punto": centred on params x/y (0..1).
    ubicacion: Literal["zona", "punto"] = "zona"

    @property
    def width(self) -> int:
        return self.size[0]

    @property
    def height(self) -> int:
        return self.size[1]


class GraphicTemplate:
    """A loaded template folder."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.id = root.name
        for name in (TEMPLATE_FILE, SCHEMA_FILE, META_FILE):
            if not (root / name).is_file():
                raise TemplateNotFound(f"La plantilla '{self.id}' no tiene '{name}' ({root}).")
        raw = yaml.safe_load((root / META_FILE).read_text(encoding="utf-8")) or {}
        self.meta = TemplateMeta.model_validate(raw)
        if self.meta.id != self.id:
            raise GraphicsError(
                f"meta.yaml de '{self.id}' declara id '{self.meta.id}': deben coincidir."
            )
        self.schema: dict[str, Any] = json.loads((root / SCHEMA_FILE).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(self.schema)

    @property
    def html_path(self) -> Path:
        return self.root / TEMPLATE_FILE

    def example_params(self) -> dict[str, Any]:
        examples = self.schema.get("examples") or [{}]
        return copy.deepcopy(dict(examples[0]))

    def validate(self, params: dict[str, Any]) -> dict[str, Any]:
        """Validate ``params`` and return a copy with top-level schema defaults applied."""
        validator = Draft202012Validator(self.schema)
        errors = sorted(validator.iter_errors(params), key=lambda e: list(e.absolute_path))
        if errors:
            lines = [f"  - {_describe(e)}" for e in errors[:8]]
            raise GraphicsParamsError(
                f"Parámetros inválidos para la plantilla '{self.id}':\n" + "\n".join(lines)
            )
        out = copy.deepcopy(params)
        for key, spec in (self.schema.get("properties") or {}).items():
            if key not in out and isinstance(spec, dict) and "default" in spec:
                out[key] = copy.deepcopy(spec["default"])
        return out

    def digest(self) -> str:
        """Hash of every file that affects the rendered pixels."""
        h = hashlib.sha256()
        files = sorted(p for p in self.root.rglob("*") if p.is_file())
        base = self.root.parent / BASE_FILE
        if base.is_file():
            files.append(base)
        for p in files:
            h.update(p.name.encode())
            h.update(p.read_bytes())
        return h.hexdigest()


def _where(err: ValidationError) -> str:
    path = "".join(f"[{p}]" if isinstance(p, int) else f".{p}" for p in err.absolute_path)
    return path.lstrip(".") or "(raíz)"


def _describe(err: ValidationError) -> str:
    """Spanish wording for the common JSON Schema failures."""
    where = _where(err)
    v = err.validator
    val = err.validator_value
    inst = err.instance
    if v == "required":
        missing = err.message.split("'")[1] if "'" in err.message else err.message
        return f"{where}: falta el parámetro obligatorio '{missing}'"
    if v == "type":
        return f"{where}: se esperaba tipo {val}, llegó {json.dumps(inst, ensure_ascii=False)}"
    if v == "enum":
        opts = ", ".join(json.dumps(o, ensure_ascii=False) for o in cast(list[Any], val))
        got = json.dumps(inst, ensure_ascii=False)
        return f"{where}: valor {got} no permitido (opciones: {opts})"
    if v == "minItems":
        return f"{where}: debe tener al menos {val} elemento(s)"
    if v == "maxItems":
        return f"{where}: admite como máximo {val} elemento(s)"
    if v == "minLength":
        return f"{where}: el texto debe tener al menos {val} carácter(es)"
    if v == "maxLength":
        return f"{where}: el texto admite como máximo {val} caracteres"
    if v == "minimum":
        return f"{where}: debe ser ≥ {val}"
    if v == "maximum":
        return f"{where}: debe ser ≤ {val}"
    if v == "additionalProperties":
        return f"{where}: parámetro desconocido ({err.message})"
    return f"{where}: {err.message}"


def templates_root(root: Path | None = None) -> Path:
    return Path(root) if root is not None else resources.graphics_templates_dir()


def load_template(template_id: str, root: Path | None = None) -> GraphicTemplate:
    base = templates_root(root)
    folder = base / template_id
    if template_id.startswith(("_", ".")) or not folder.is_dir():
        available = ", ".join(m.id for m in list_templates(base)) or "ninguna"
        raise TemplateNotFound(
            f"No existe la plantilla de gráficos '{template_id}'. Disponibles: {available}."
        )
    return GraphicTemplate(folder)


def list_templates(root: Path | None = None) -> list[TemplateMeta]:
    """Metadata of every template under ``templates/graphics/`` (sorted by id)."""
    base = templates_root(root)
    if not base.is_dir():
        return []
    out: list[TemplateMeta] = []
    for folder in sorted(base.iterdir()):
        hidden = folder.name.startswith(("_", "."))
        if folder.is_dir() and not hidden and (folder / META_FILE).is_file():
            out.append(GraphicTemplate(folder).meta)
    return out
