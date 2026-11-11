"""``init``: create the per-video workspace and keep an intact, read-only copy of the original.

Rules covered here: P01 (copy + sha256 + read-only, never move) and P02 (explicit path to the
VIDEO_BASE: a reference video or a missing file is never accepted silently).
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import unicodedata
from collections.abc import Callable
from pathlib import Path
from typing import Any

from editoria.ingest.errors import IngestError
from editoria.schemas import ProjectConfig, write_model
from editoria.util import ffmpeg, resources
from editoria.util.files import make_read_only, sha256_file
from editoria.util.project import ORIGINAL_DIR, ProjectContext, projects_dir

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
REFERENCE_DIR_NAME = "02_referencias_usuario"  # folder of the kit with third-party references


def slugify(text: str) -> str:
    """'Edición Ñandú 1!' -> 'edicion-nandu-1'."""
    norm = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", norm.lower()).strip("-")
    return slug or "proyecto"


def _on_rm_error(func: Callable[..., Any], path: str, _exc: object) -> None:
    os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
    func(path)


def remove_tree(path: Path) -> None:
    """rmtree that also removes read-only files (the original is read-only on purpose)."""
    shutil.rmtree(path, onerror=_on_rm_error)


def validate_video(video: Path | None) -> Path:
    """Return the explicit, existing video file or raise asking ONLY for that file (P02)."""
    if video is None or str(video).strip() in {"", "."}:
        raise IngestError(
            "Falta el VIDEO_BASE: indicá la ruta del archivo de video exportado desde CapCut "
            "(por ejemplo: editoria init ruta/al/video.mp4 --slug mi-proyecto)."
        )
    path = Path(video)
    if path.is_dir():
        raise IngestError(
            f"'{path}' es una carpeta. Indicá la ruta del archivo de video (VIDEO_BASE), "
            "no una carpeta."
        )
    if not path.is_file():
        raise IngestError(
            f"No existe el VIDEO_BASE '{path}'. Indicá la ruta completa del archivo de video."
        )
    parts = {p.lower() for p in path.resolve().parts}
    if REFERENCE_DIR_NAME in parts:
        raise IngestError(
            f"'{path.name}' está en la carpeta de referencias del usuario: una referencia no "
            "puede usarse como VIDEO_BASE. Indicá el video grabado y recortado por vos."
        )
    try:
        info = ffmpeg.probe(path)
    except ffmpeg.FFmpegError as exc:
        raise IngestError(
            f"'{path.name}' no se pudo leer como video. Indicá otro archivo (VIDEO_BASE)."
        ) from exc
    has_video = any(s.get("codec_type") == "video" for s in info.get("streams", []))
    if not has_video:
        raise IngestError(
            f"'{path.name}' no contiene una pista de video. Indicá el archivo de video "
            "(VIDEO_BASE)."
        )
    return path


def init_project(video: Path, slug: str, brand: str, base: Path | None = None) -> ProjectContext:
    """Create ``proyectos/<slug>/`` and copy (never move) ``video`` into ``00_original``.

    Writes ``video_base.sha256``, marks the copy read-only and writes ``proyecto.yaml``.
    Never overwrites an existing project.
    """
    src = validate_video(video)
    if not SLUG_RE.match(slug):
        raise IngestError(
            f"Slug inválido '{slug}': usá minúsculas, números, '-' o '_' "
            "(por ejemplo: mi-primer-reel)."
        )
    if not (resources.brands_dir() / brand / "brand.yaml").exists():
        raise IngestError(
            f"No existe la marca '{brand}' (se busca en {resources.brands_dir()}). "
            "Revisá la opción --brand."
        )
    root = (base or projects_dir()) / slug
    if root.exists():
        raise IngestError(
            f"Ya existe el proyecto '{slug}' en {root.parent}. No se sobrescribe: "
            "elegí otro --slug."
        )

    src_digest = sha256_file(src)
    ctx = ProjectContext.create(slug, base)
    try:
        dst = ctx.original_dir / f"video_base{src.suffix.lower()}"
        shutil.copy2(src, dst)
        digest = sha256_file(dst)
        if digest != src_digest:
            raise IngestError("La copia del original no coincide con el archivo de origen (hash).")
        ctx.original_sha256_path().write_text(f"{digest}  {dst.name}\n", encoding="utf-8")
        make_read_only(dst)
        make_read_only(ctx.original_sha256_path())
        write_model(
            ctx.config_path,
            ProjectConfig(
                slug=slug,
                brand=brand,
                original=f"{ORIGINAL_DIR}/{dst.name}",
                original_sha256=digest,
                source_name=src.name,
            ),
        )
    except BaseException:
        remove_tree(ctx.root)
        raise
    return ctx
