"""registro_generaciones.csv (exact REGISTRO_COLUMNS) and per-shot meta.json."""

from __future__ import annotations

import csv
import os
import re
from pathlib import Path

from pydantic import ValidationError

from editoria.schemas import REGISTRO_COLUMNS, GenerationRecord, read_model, write_model
from editoria.shots.errors import ShotError
from editoria.shots.models import ShotMeta
from editoria.util.files import read_csv_rows, write_csv_rows
from editoria.util.project import ProjectContext

_ID_RE = re.compile(r"^G(\d{2,})$")


def normalize_id(shot_id: str) -> str:
    sid = shot_id.strip().upper()
    if not _ID_RE.match(sid):
        raise ShotError(f"Id de toma inválido '{shot_id}'. Se espera G01, G02, ...")
    return sid


def _check_header(path: Path) -> None:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        header = next(csv.reader(fh), [])
    if tuple(header) != REGISTRO_COLUMNS:
        raise ShotError(
            f"{path.name} no tiene las columnas esperadas del registro de generaciones. "
            f"Se esperaba: {', '.join(REGISTRO_COLUMNS)}."
        )


def load_registry(ctx: ProjectContext) -> list[GenerationRecord]:
    path = ctx.generations_registry
    if not path.exists():
        return []
    _check_header(path)
    try:
        return [GenerationRecord.model_validate(r) for r in read_csv_rows(path)]
    except ValidationError as exc:
        raise ShotError(f"{path.name} tiene filas inválidas: {exc}") from exc


def save_registry(ctx: ProjectContext, records: list[GenerationRecord]) -> None:
    """Atomic rewrite with the exact column order."""
    path = ctx.generations_registry
    tmp = path.with_name(path.name + ".tmp")
    write_csv_rows(tmp, REGISTRO_COLUMNS, [r.model_dump() for r in records])
    os.replace(tmp, path)


def get_record(ctx: ProjectContext, shot_id: str) -> GenerationRecord:
    sid = normalize_id(shot_id)
    for rec in load_registry(ctx):
        if rec.id == sid:
            return rec
    raise ShotError(
        f"No existe la toma {sid} en el registro. Prepará una con 'editoria shots pack'."
    )


def update_record(ctx: ProjectContext, shot_id: str, **changes: str) -> GenerationRecord:
    sid = normalize_id(shot_id)
    records = load_registry(ctx)
    for i, rec in enumerate(records):
        if rec.id == sid:
            records[i] = GenerationRecord.model_validate({**rec.model_dump(), **changes})
            save_registry(ctx, records)
            return records[i]
    raise ShotError(f"No existe la toma {sid} en el registro.")


def next_shot_id(ctx: ProjectContext) -> str:
    used = [rec.id for rec in load_registry(ctx)]
    if ctx.shots_packs_dir.exists():
        used += [p.name for p in ctx.shots_packs_dir.iterdir() if p.is_dir()]
    nums = [int(m.group(1)) for sid in used if (m := _ID_RE.match(sid))]
    return f"G{(max(nums) + 1) if nums else 1:02d}"


def pack_dir(ctx: ProjectContext, shot_id: str) -> Path:
    return ctx.shots_packs_dir / normalize_id(shot_id)


def results_dir(ctx: ProjectContext, shot_id: str) -> Path:
    return ctx.shots_results_dir / normalize_id(shot_id)


def comparison_dir(ctx: ProjectContext, shot_id: str) -> Path:
    return ctx.shots_comparisons_dir / normalize_id(shot_id)


def meta_path(ctx: ProjectContext, shot_id: str) -> Path:
    return pack_dir(ctx, shot_id) / "meta.json"


def load_meta(ctx: ProjectContext, shot_id: str) -> ShotMeta:
    path = meta_path(ctx, shot_id)
    if not path.exists():
        raise ShotError(
            f"Falta el paquete de {normalize_id(shot_id)} ({path.name}). "
            "Ejecutá primero 'editoria shots pack'."
        )
    return read_model(path, ShotMeta)


def save_meta(ctx: ProjectContext, meta: ShotMeta) -> None:
    write_model(meta_path(ctx, meta.id), meta)


def rel(ctx: ProjectContext, path: Path) -> str:
    """Project-relative POSIX path for CSV/meta files."""
    return path.resolve().relative_to(ctx.root.resolve()).as_posix()
