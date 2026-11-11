from __future__ import annotations

import pytest

from editoria.shots import ShotError, import_shot
from editoria.shots.media import video_info
from editoria.util import ffmpeg
from editoria.util.files import read_csv_rows


def _streams(path):  # type: ignore[no-untyped-def]
    return ffmpeg.probe(path)["streams"]


def test_import_conforms_and_drops_audio(packed, fixtures_dir):  # type: ignore[no-untyped-def]
    ctx, _ = packed
    src = fixtures_dir / "generada_ok.mp4"
    assert any(s["codec_type"] == "audio" for s in _streams(src))  # fixture has audio

    meta = import_shot(ctx, "G01", src, funcion="video a video (prueba)", ajustes="calidad alta")
    out = ctx.root / meta.imported.conformed  # type: ignore[union-attr]
    streams = _streams(out)
    assert [s["codec_type"] for s in streams] == ["video"]  # no audio (P03)
    v = streams[0]
    assert (v["width"], v["height"], v["pix_fmt"]) == (1080, 1920, "yuv420p")
    assert v["r_frame_rate"] == "30/1"
    assert video_info(out).duration == pytest.approx(2.0, abs=0.05)

    row = read_csv_rows(ctx.generations_registry)[0]
    assert row["archivo_resultado"] == "02_tomas/higgsfield/resultados/G01/conformado.mp4"
    assert row["funcion_modelo_real"] == "video a video (prueba)"
    assert row["ajustes_mostrados"] == "calidad alta"
    assert row["costo_mostrado"] == ""  # nobody reported a cost: nothing invented
    assert row["veredicto"] == "pendiente"
    assert not ctx.credits_log.exists()


def test_import_records_reported_cost(packed, fixtures_dir):  # type: ignore[no-untyped-def]
    ctx, _ = packed
    import_shot(ctx, "G01", fixtures_dir / "generada_ok.mp4", costo=12.5)
    assert read_csv_rows(ctx.generations_registry)[0]["costo_mostrado"] == "12.5"
    assert '"amount": 12.5' in ctx.credits_log.read_text(encoding="utf-8")


def test_import_rejects_different_aspect(packed, fixtures_dir):  # type: ignore[no-untyped-def]
    ctx, _ = packed
    with pytest.raises(ShotError, match="otro aspecto"):
        import_shot(ctx, "G01", fixtures_dir / "base_1920x1080.mp4")
    assert read_csv_rows(ctx.generations_registry)[0]["archivo_resultado"] == ""


def test_import_rejects_short_duration(packed, short_clip):  # type: ignore[no-untyped-def]
    ctx, _ = packed
    with pytest.raises(ShotError, match="más corto"):
        import_shot(ctx, "G01", short_clip)


def test_import_trims_longer_clip(packed, long_clip):  # type: ignore[no-untyped-def]
    ctx, _ = packed
    meta = import_shot(ctx, "G01", long_clip)
    assert meta.imported is not None and meta.imported.trimmed
    out = ctx.root / meta.imported.conformed
    assert video_info(out).duration == pytest.approx(2.0, abs=0.05)


def test_import_accepts_path_with_spaces_and_accents(packed, spaced_video):  # type: ignore[no-untyped-def]
    ctx, _ = packed
    assert spaced_video.name == "edición ñ.mp4"
    meta = import_shot(ctx, "G01", spaced_video)  # 12 s, 9:16 -> trimmed to the segment
    assert meta.imported is not None and meta.imported.trimmed


def test_import_conforms_other_resolution_and_fps(packed, fixtures_dir):  # type: ignore[no-untyped-def]
    ctx, _ = packed
    # 720x1280 @ 25 fps (6 s): same 9:16 aspect, other size and FPS
    meta = import_shot(ctx, "G01", fixtures_dir / "base_720x1280_25.mp4")
    v = _streams(ctx.root / meta.imported.conformed)[0]  # type: ignore[union-attr]
    assert (v["width"], v["height"], v["r_frame_rate"]) == (1080, 1920, "30/1")


def test_import_twice_needs_replace(packed, fixtures_dir):  # type: ignore[no-untyped-def]
    ctx, _ = packed
    import_shot(ctx, "G01", fixtures_dir / "generada_ok.mp4")
    with pytest.raises(ShotError, match="--reemplazar"):
        import_shot(ctx, "G01", fixtures_dir / "generada_mala.mp4")
    import_shot(ctx, "G01", fixtures_dir / "generada_mala.mp4", replace=True)


def test_import_needs_pack_and_existing_file(packed, fixtures_dir, tmp_path):  # type: ignore[no-untyped-def]
    ctx, _ = packed
    with pytest.raises(ShotError, match="No existe la toma"):
        import_shot(ctx, "G09", fixtures_dir / "generada_ok.mp4")
    with pytest.raises(ShotError, match="No existe el archivo"):
        import_shot(ctx, "G01", tmp_path / "nada.mp4")
    with pytest.raises(ShotError):
        import_shot(ctx, "G01", fixtures_dir / "transcript_fixture.json")
