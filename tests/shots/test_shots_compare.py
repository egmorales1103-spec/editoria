from __future__ import annotations

import pytest

from editoria.schemas import Box, Canvas
from editoria.shots import ShotError, compare_shot, import_shot
from editoria.shots.compare import background_regions, recommend
from editoria.util.project import ProjectContext


def test_compare_flags_drift_in_bad_clip(packed, fixtures_dir):  # type: ignore[no-untyped-def]
    ctx, _ = packed
    import_shot(ctx, "G01", fixtures_dir / "generada_mala.mp4")
    res = compare_shot(ctx, "G01")
    assert res.recommendation == "deriva"
    assert res.ssim_background < 0.75
    assert res.color_delta_e > 10
    for rel_path in (res.sheet, res.side_by_side, res.metrics_file):
        assert (ctx.root / rel_path).is_file()
    assert (ctx.shots_comparisons_dir / "G01" / "informe.md").is_file()
    assert not (ctx.shots_comparisons_dir / "G01" / "_trabajo").exists()


def test_compare_marks_ok_clip_stable(packed, fixtures_dir):  # type: ignore[no-untyped-def]
    ctx, _ = packed
    import_shot(ctx, "G01", fixtures_dir / "generada_ok.mp4")
    res = compare_shot(ctx, "G01")
    assert res.recommendation == "estable"
    assert res.ssim_background > 0.9
    assert res.color_delta_e < 5
    assert res.flicker < 3
    assert res.face_box_canvas is not None  # face excluded from the background


def test_compare_does_not_touch_verdict(packed, fixtures_dir):  # type: ignore[no-untyped-def]
    from editoria.util.files import read_csv_rows

    ctx, _ = packed
    import_shot(ctx, "G01", fixtures_dir / "generada_ok.mp4")
    compare_shot(ctx, "G01")
    assert read_csv_rows(ctx.generations_registry)[0]["veredicto"] == "pendiente"


def test_compare_requires_import(packed):  # type: ignore[no-untyped-def]
    ctx, _ = packed
    with pytest.raises(ShotError, match="todavía no tiene resultado"):
        compare_shot(ctx, "G01")


def test_background_regions_exclude_face():
    canvas = Canvas()
    face = Box(x=260, y=300, w=560, h=640)
    regions = background_regions(canvas, face)
    assert len(regions) == 4
    area = sum(w * h for _, _, w, h in regions)
    assert area == canvas.width * canvas.height - face.w * face.h
    assert background_regions(canvas, None) == [(0, 0, 1080, 1920)]


@pytest.mark.parametrize(
    ("ssim", "flicker", "de", "expected"),
    [
        (0.97, 0.1, 0.5, "estable"),
        (0.85, 0.1, 0.5, "revisar"),
        (0.97, 5.0, 0.5, "revisar"),
        (0.6, 0.1, 0.5, "deriva"),
        (0.97, 0.1, 15.0, "deriva"),
        (0.97, 12.0, 0.5, "deriva"),
    ],
)
def test_recommend_thresholds(ssim, flicker, de, expected):  # type: ignore[no-untyped-def]
    assert recommend(ssim, flicker, de)[0] == expected


def test_compare_without_face_uses_whole_canvas(  # type: ignore[no-untyped-def]
    packed, fixtures_dir
):
    ctx, _ = packed
    ctx.analysis("rostro.json").unlink()
    import_shot(ctx, "G01", fixtures_dir / "generada_ok.mp4")
    res = compare_shot(ctx, "G01")
    assert res.face_box_canvas is None
    assert isinstance(ctx, ProjectContext)
