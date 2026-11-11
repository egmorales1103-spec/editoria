"""Fixtures for the shots tests: a project with a packed segment 8.5-10.5 s (matches generada_*)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from editoria.schemas import ProjectConfig, read_model, write_model
from editoria.shots import pack_shot
from editoria.shots.models import ShotMeta
from editoria.util import ffmpeg
from editoria.util.project import ProjectContext

SEG_IN, SEG_OUT = 8.5, 10.5


def _set_config(ctx: ProjectContext, **fields: object) -> None:
    data = read_model(ctx.config_path, ProjectConfig).model_dump()
    data.update(fields)
    write_model(ctx.config_path, ProjectConfig.model_validate(data))


@pytest.fixture
def set_config() -> Callable[..., None]:
    """set_config(ctx, budget={...}, tool_limits={...}) edits proyecto.yaml."""
    return _set_config


@pytest.fixture
def packed(fixture_project: ProjectContext) -> tuple[ProjectContext, ShotMeta]:
    meta = pack_shot(fixture_project, SEG_IN, SEG_OUT, "acercamiento suave del 10 %")
    return fixture_project, meta


@pytest.fixture
def short_clip(fixtures_dir: Path, tmp_path: Path) -> Path:
    """1.0 s of the 'ok' candidate (shorter than the 2.0 s segment)."""
    out = tmp_path / "corta ñ.mp4"
    ffmpeg.run(["-i", fixtures_dir / "generada_ok.mp4", "-t", "1.0", "-c:v", "libx264", out])
    return out


@pytest.fixture
def long_clip(fixtures_dir: Path, tmp_path: Path) -> Path:
    """3.5 s of the base starting at 8.0 s (longer than the segment)."""
    out = tmp_path / "larga.mp4"
    ffmpeg.run(
        [
            "-ss",
            "8.0",
            "-i",
            fixtures_dir / "base_1080x1920_30.mp4",
            "-t",
            "3.5",
            "-c:v",
            "libx264",
            out,
        ]
    )
    return out
