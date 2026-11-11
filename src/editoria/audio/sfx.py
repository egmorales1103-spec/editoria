"""Catalogue of the bundled sound effects (assets/sfx/) and cue -> file resolution."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from editoria.audio.wavio import AudioError, read_wav
from editoria.schemas import AssetEntry
from editoria.util import resources
from editoria.util.files import sha256_file

CUES: tuple[str, ...] = ("pop", "click", "whoosh", "ding", "teclado", "impacto_suave")
MAX_VARIANT = 3


def sfx_dir() -> Path:
    return resources.assets_dir() / "sfx"


def sfx_id(cue: str, variant: int | None) -> str:
    return f"{cue}_{variant or 1}"


def resolve_sfx(cue: str, variant: int | None = None, directory: Path | None = None) -> Path:
    """File for ``cue``/``variant`` (None = 1). Raises AudioError (Spanish) when unknown."""
    if cue not in CUES:
        raise AudioError(f"El cue de sonido '{cue}' no existe. Disponibles: {', '.join(CUES)}.")
    v = variant or 1
    path = (directory or sfx_dir()) / f"{sfx_id(cue, v)}.wav"
    if not path.exists():
        available = sorted(
            p.stem.rsplit("_", 1)[1]
            for p in (directory or sfx_dir()).glob(f"{cue}_*.wav")
            if p.stem.rsplit("_", 1)[1].isdigit()
        )
        hint = f" Variantes disponibles: {', '.join(available)}." if available else ""
        raise AudioError(f"No se encontró el SFX '{cue}' variante {v} ({path.name}).{hint}")
    return path


@dataclass(frozen=True)
class SfxInfo:
    id: str
    cue: str
    variant: int
    path: Path
    exists: bool
    duration_s: float | None
    license: str
    author: str
    suggested_use: str
    hash_ok: bool | None  # None = not verifiable (missing file or no hash in the manifest)


def list_sfx(directory: Path | None = None) -> list[SfxInfo]:
    """Every cue/variant with its licence from ``manifest.yaml`` (missing entries are flagged)."""
    base = directory or sfx_dir()
    manifest = resources.load_sfx_manifest() if directory is None else _load_manifest(base)
    rows: list[SfxInfo] = []
    for cue in CUES:
        for variant in range(1, MAX_VARIANT + 1):
            asset_id = sfx_id(cue, variant)
            path = base / f"{asset_id}.wav"
            entry: AssetEntry | None = manifest.get(asset_id)
            duration: float | None = None
            hash_ok: bool | None = None
            if path.exists():
                samples, sr = read_wav(path)
                duration = len(samples) / sr
                if entry is not None and entry.sha256:
                    hash_ok = sha256_file(path) == entry.sha256
            rows.append(
                SfxInfo(
                    id=asset_id,
                    cue=cue,
                    variant=variant,
                    path=path,
                    exists=path.exists(),
                    duration_s=duration,
                    license=entry.license if entry else "",
                    author=entry.author if entry else "",
                    suggested_use=entry.suggested_use if entry else "",
                    hash_ok=hash_ok,
                )
            )
    return rows


def _load_manifest(directory: Path):  # type: ignore[no-untyped-def]
    from editoria.schemas import AssetManifest, read_model

    p = directory / "manifest.yaml"
    return read_model(p, AssetManifest) if p.exists() else AssetManifest()
