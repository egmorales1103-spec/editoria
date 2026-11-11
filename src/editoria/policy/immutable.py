"""Write guards: delivered versions and the original folder are immutable (P01/P20).

Every command or function that writes inside ``04_versiones/<Vn>/`` calls these guards first.
The only exception (``feedback parse`` writing ``feedback.json``) lives in another module.
"""

from __future__ import annotations

from pathlib import Path

from editoria.util.project import DELIVERED_MARKER, ORIGINAL_DIR, ProjectContext


class ImmutableTargetError(PermissionError):
    """User-facing (Spanish) refusal to write into a delivered version or ``00_original/``."""


def delivered_message(version: str) -> str:
    return (
        f"La versión {version} ya fue entregada y es inmutable: no se modifica. "
        "Creá una versión nueva con 'editoria version new'."
    )


def ensure_not_delivered(ctx: ProjectContext, version: str) -> None:
    """Raise :class:`ImmutableTargetError` when ``version`` has the ``.entregado`` marker."""
    if ctx.is_delivered(version):
        raise ImmutableTargetError(delivered_message(version))


def delivered_version_of(path: Path) -> Path | None:
    """Folder of the delivered version that contains ``path`` (or None).

    Walks ``path`` and its ancestors looking for the ``.entregado`` marker, so it works for
    files that do not exist yet and for any project location.
    """
    p = Path(path).resolve()
    for folder in (p, *p.parents):
        if (folder / DELIVERED_MARKER).is_file():
            return folder
    return None


def ensure_writable_path(path: Path) -> None:
    """Refuse destinations inside a delivered version or inside any ``00_original/``."""
    p = Path(path).resolve()
    if any(part == ORIGINAL_DIR for part in p.parts):
        raise ImmutableTargetError(
            f"No se escribe dentro de {ORIGINAL_DIR}/: el VIDEO_BASE y su carpeta son de solo "
            "lectura. Elegí otro destino."
        )
    delivered = delivered_version_of(p)
    if delivered is not None:
        raise ImmutableTargetError(delivered_message(delivered.name))
