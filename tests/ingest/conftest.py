"""Fixtures for the ingest tests: an ingested project and a few defective media files."""

from __future__ import annotations

from pathlib import Path

import pytest

from editoria.ingest import init_project
from editoria.util import ffmpeg
from editoria.util.project import ProjectContext


@pytest.fixture
def ingested(spaced_video: Path, projects_dir: Path) -> ProjectContext:
    """Project 'demo' created by init from 'carpeta con espacios/edición ñ.mp4'."""
    return init_project(spaced_video, "demo", "master-solution")


@pytest.fixture(scope="session")
def defective_dir(fixtures_dir: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """VFR, rotated (display matrix) and corrupted variants of the fixtures."""
    out = tmp_path_factory.mktemp("defectuosos ñ")
    small = fixtures_dir / "base_720x1280_25.mp4"
    ffmpeg.run(
        [
            "-i", small, "-vf", "select='not(between(n,20,60))*not(between(n,90,100))'",
            "-fps_mode", "vfr", "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac",
            out / "vfr.mp4",
        ]
    )  # fmt: skip
    ffmpeg.run(["-display_rotation", "90", "-i", small, "-c", "copy", out / "rotado.mp4"])
    # Several damaged regions plus a truncated tail: a single 3 KB hole in the middle could
    # land on bytes the decoder skips silently (CI failed that way). With +faststart the moov
    # is up front, so the file still opens and decoding reports errors deterministically.
    data = bytearray((fixtures_dir / "base_1080x1920_30.mp4").read_bytes())
    size = len(data)
    for frac in (0.3, 0.45, 0.6):
        i = int(size * frac)
        data[i : i + 3000] = bytes([0x00, 0xFF]) * 1500
    (out / "corrupto.mp4").write_bytes(bytes(data[: int(size * 0.8)]))
    return out
