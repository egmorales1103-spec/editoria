"""Fixtures for the analysis tests: a project ingested from the fixture video + transcript."""

from __future__ import annotations

from pathlib import Path

import pytest

from editoria.ingest import init_project, transcribe_project
from editoria.util.project import ProjectContext


@pytest.fixture
def transcribed(spaced_video: Path, projects_dir: Path) -> ProjectContext:
    """Project 'demo' (video with spaces/accents in its path) with the fixture transcript."""
    ctx = init_project(spaced_video, "demo", "master-solution")
    transcribe_project(ctx, backend="fixture")
    return ctx
