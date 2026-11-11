"""Fixtures for the render tests (substitute inputs; no A2/A3/A4 needed)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from render_support import face_track, make_project, setup_version

from editoria.schemas import Box
from editoria.util.project import ProjectContext

FACE = Box(x=340, y=380, w=400, h=480)


@pytest.fixture
def spaced_project(projects_dir: Path, spaced_video: Path) -> ProjectContext:
    """Project whose original comes from 'carpeta con espacios/edición ñ.mp4'."""
    return make_project(projects_dir, "demo", spaced_video, face_track(1080, 1920, FACE))


@pytest.fixture
def version_ctx(spaced_project: ProjectContext, fixtures_dir: Path) -> ProjectContext:
    setup_version(spaced_project, fixtures_dir)
    return spaced_project
