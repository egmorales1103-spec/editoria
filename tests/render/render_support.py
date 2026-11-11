"""Helpers shared by the render and QC tests (substitute inputs from tests/.fixtures)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from editoria.schemas import (
    Box,
    Canvas,
    FaceSample,
    FaceTrack,
    OverlayClip,
    ProjectConfig,
    write_model,
)
from editoria.util.files import make_read_only, sha256_file
from editoria.util.geometry import zone_box
from editoria.util.project import FACE_FILE, ProjectContext


def make_project(
    base_dir: Path, slug: str, video: Path, face: FaceTrack | None = None
) -> ProjectContext:
    """Minimal workspace around ``video`` (read-only original with hash)."""
    ctx = ProjectContext.create(slug, base_dir)
    dst = ctx.original_dir / "video_base.mp4"
    shutil.copy2(video, dst)
    digest = sha256_file(dst)
    ctx.original_sha256_path().write_text(f"{digest}  video_base.mp4\n", encoding="utf-8")
    make_read_only(dst)
    write_model(
        ctx.config_path,
        ProjectConfig(
            slug=slug,
            original="00_original/video_base.mp4",
            original_sha256=digest,
            source_name=video.name,
        ),
    )
    if face is not None:
        write_model(ctx.analysis(FACE_FILE), face)
    return ctx


def face_track(w: int, h: int, box: Box, duration: float = 12.0) -> FaceTrack:
    samples = [FaceSample(t=i * 0.5, box=box) for i in range(int(duration / 0.5) + 1)]
    return FaceTrack(frame_w=w, frame_h=h, samples=samples, union_box=box)


def setup_version(
    ctx: ProjectContext,
    fixtures: Path,
    version: str = "V1",
    *,
    plan: Path | None = None,
    captions: bool = True,
    graphics: bool = True,
    mix: bool = True,
) -> Path:
    """Fill 04_versiones/<version>/ like A2/A3/A4 would, using the substitute fixtures."""
    vdir = ctx.version_dir(version)
    vdir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(plan or fixtures / "plan_fixture.yaml", vdir / "plan.yaml")
    if captions:
        shutil.copy2(fixtures / "captions_fixture.ass", vdir / "subtitulos.ass")
    if graphics:
        gdir = vdir / "graficos"
        shutil.copytree(fixtures / "overlay_fixture", gdir / "g01")
        shutil.copy2(fixtures / "emoji_fixture.gif", gdir / "e01.gif")
        canvas = Canvas()
        g = zone_box("upper", canvas, 600, 200)
        e = zone_box("upper_right", canvas, 200, 200)
        clips = [
            OverlayClip(
                id="g01", frames_pattern=Path("g01/%05d.png"), frame_count=45, fps="30/1",
                x=g.x, y=g.y, w=600, h=200, start=0.3, end=1.8,
            ),
            OverlayClip(
                id="e01", frames_pattern=Path("e01.gif"), x=e.x, y=e.y, w=200, h=200,
                start=6.2, end=7.4, is_gif=True,
            ),
        ]  # fmt: skip
        data = {"overlays": [c.model_dump(mode="json") for c in clips]}
        (gdir / "overlays.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    if mix:
        (vdir / "audio").mkdir(exist_ok=True)
        shutil.copy2(fixtures / "mix_fixture.wav", vdir / "audio" / "mezcla.wav")
    return vdir
