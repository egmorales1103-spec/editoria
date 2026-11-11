"""Shared pytest fixtures (owner: lead). Tests never use the network."""

from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

import pytest

from editoria.schemas import CutList, ProjectConfig, write_model
from editoria.util.files import make_read_only, sha256_file
from editoria.util.project import (
    CUTS_FILE,
    FACE_FILE,
    PROBE_FILE,
    SEGMENTS_FILE,
    TRANSCRIPT_FILE,
    ProjectContext,
    set_projects_dir,
)

REPO = Path(__file__).resolve().parents[1]


def _load_make_fixtures():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location(
        "make_fixtures", REPO / "scripts" / "make_fixtures.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    """tests/.fixtures, generated on first use (synthetic media, < ~15 s)."""
    return _load_make_fixtures().ensure_fixtures(REPO / "tests" / ".fixtures")


@pytest.fixture(scope="session")
def base_video(fixtures_dir: Path) -> Path:
    return fixtures_dir / "base_1080x1920_30.mp4"


@pytest.fixture(scope="session")
def spaced_video(fixtures_dir: Path) -> Path:
    """Copy of the base video at 'carpeta con espacios/edición ñ.mp4'."""
    return fixtures_dir / "carpeta con espacios" / "edición ñ.mp4"


@pytest.fixture
def projects_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolated proyectos/ folder (with a space and an accent, on purpose)."""
    d = tmp_path / "proyectos con espacio ñ"
    d.mkdir()
    monkeypatch.setenv("EDITORIA_PROJECTS", str(d))
    set_projects_dir(None)
    return d


@pytest.fixture
def fixture_project(fixtures_dir: Path, projects_dir: Path) -> ProjectContext:
    """A ready workspace built WITHOUT the ingest module: original copied read-only with its
    hash, plus probe/transcript/face/segments from the fixtures. Slug: 'demo'."""
    ctx = ProjectContext.create("demo", projects_dir)
    src = fixtures_dir / "base_1080x1920_30.mp4"
    dst = ctx.original_dir / "video_base.mp4"
    shutil.copy2(src, dst)
    digest = sha256_file(dst)
    ctx.original_sha256_path().write_text(f"{digest}  video_base.mp4\n", encoding="utf-8")
    make_read_only(dst)
    write_model(
        ctx.config_path,
        ProjectConfig(
            slug="demo",
            brand="master-solution",
            original="00_original/video_base.mp4",
            original_sha256=digest,
            source_name=src.name,
        ),
    )
    for name, fixture in (
        (PROBE_FILE, "probe_fixture.json"),
        (TRANSCRIPT_FILE, "transcript_fixture.json"),
        (FACE_FILE, "rostro_fixture.json"),
        (SEGMENTS_FILE, "segmentos_fixture.json"),
    ):
        shutil.copy2(fixtures_dir / fixture, ctx.analysis(name))
    write_model(ctx.analysis(CUTS_FILE), CutList(cuts=[4.0, 7.85]))
    return ctx
