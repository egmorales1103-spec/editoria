"""Test helpers: licensed asset manifests (SFX, emoji, music)."""

from __future__ import annotations

from editoria.schemas import AssetEntry, AssetManifest

CUES = ("pop", "click", "whoosh", "ding", "teclado", "impacto_suave")


def sfx_manifest() -> AssetManifest:
    return AssetManifest(
        assets=[
            AssetEntry(
                id=f"{c}_{n}",
                path=f"assets/sfx/{c}_{n}.wav",
                kind="sfx",
                license="CC0-1.0",
                author="EditorIA contributors",
            )
            for c in CUES
            for n in (1, 2, 3)
        ]
    )


def external_manifest() -> AssetManifest:
    return AssetManifest(
        assets=[
            AssetEntry(
                id=f"E0{n}",
                path=f"assets/emoji/E0{n}.gif",
                kind="emoji",
                license="Apache-2.0",
            )
            for n in range(1, 7)
        ]
        + [AssetEntry(id="musica_1", path="assets/music/m.mp3", kind="music", license="CC-BY-4.0")]
    )
