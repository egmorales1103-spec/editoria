"""Read/write schema models as YAML or JSON (chosen by file suffix)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypeVar

import yaml
from pydantic import BaseModel

M = TypeVar("M", bound=BaseModel)


def _load_raw(path: Path) -> Any:
    text = Path(path).read_text(encoding="utf-8")
    if Path(path).suffix.lower() in {".yaml", ".yml"}:
        return yaml.safe_load(text)
    return json.loads(text)


def read_model(path: Path | str, model: type[M]) -> M:
    return model.model_validate(_load_raw(Path(path)))


def to_data(obj: BaseModel) -> Any:
    """JSON-compatible dict using aliases (e.g. `in`, `schema`), dropping None values."""
    return obj.model_dump(mode="json", by_alias=True, exclude_none=True)


def write_model(path: Path | str, obj: BaseModel) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = to_data(obj)
    if p.suffix.lower() in {".yaml", ".yml"}:
        text = yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=100)
    else:
        text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    p.write_text(text, encoding="utf-8", newline="\n")
    return p
