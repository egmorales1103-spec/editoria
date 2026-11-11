"""QC fixtures: one correct render (session) copied per test, plus licensed manifests."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "render"))

from render_support import face_track, make_project, setup_version

from editoria.render import FFmpegRenderer, inputs_from_version
from editoria.schemas import AssetEntry, AssetManifest, Box, EncodeSettings
from editoria.util import resources
from editoria.util.project import ProjectContext

FACE = Box(x=340, y=380, w=400, h=480)


@pytest.fixture(scope="session")
def rendered_template(fixtures_dir: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A project (in a folder with spaces and ñ) with V1 rendered from the fixture plan."""
    base = tmp_path_factory.mktemp("qc") / "plantilla con espacio ñ"
    base.mkdir()
    ctx = make_project(
        base, "demo", fixtures_dir / "carpeta con espacios" / "edición ñ.mp4",
        face_track(1080, 1920, FACE),
    )  # fmt: skip
    vdir = setup_version(ctx, fixtures_dir)
    FFmpegRenderer().render(
        ctx.load_plan("V1"), ctx, inputs_from_version(ctx, "V1"), vdir / "video.mp4",
        EncodeSettings(preset="veryfast"),
    )  # fmt: skip
    return ctx.root


@pytest.fixture
def rendered(rendered_template: Path, projects_dir: Path) -> ProjectContext:
    """Fresh copy of the rendered project inside the per-test projects dir."""
    dst = projects_dir / "demo"
    shutil.copytree(rendered_template, dst)
    return ProjectContext(dst)


def _manifest(kind: str, ids: list[str]) -> AssetManifest:
    return AssetManifest(
        assets=[
            AssetEntry(id=i, path=f"assets/{kind}/{i}", kind=kind, license="CC0-1.0")  # type: ignore[arg-type]
            for i in ids
        ]
    )


@pytest.fixture(autouse=True)
def licensed_assets(monkeypatch: pytest.MonkeyPatch) -> None:
    """The fixture plan's SFX and emoji are licensed (the real manifests belong to A4/A7)."""
    sfx = _manifest(
        "sfx", [f"{c}_{n}" for c in ("pop", "click", "whoosh", "ding") for n in (1, 2, 3)]
    )
    ext = _manifest("emoji", [f"E0{n}" for n in range(1, 7)])
    monkeypatch.setattr(resources, "load_sfx_manifest", lambda: sfx)
    monkeypatch.setattr(resources, "load_external_manifest", lambda: ext)
