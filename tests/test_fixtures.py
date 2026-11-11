from __future__ import annotations

from pathlib import Path

from editoria.schemas import Box, Canvas, EditPlan, Transcript, read_model
from editoria.util import ffmpeg
from editoria.util.files import is_read_only, sha256_file
from editoria.util.geometry import base_transform
from editoria.util.project import ProjectContext

EXPECTED = [
    "base_1080x1920_30.mp4",
    "base_720x1280_25.mp4",
    "base_1920x1080.mp4",
    "sin_audio.mp4",
    "carpeta con espacios/edición ñ.mp4",
    "generada_ok.mp4",
    "generada_mala.mp4",
    "transcript_fixture.json",
    "rostro_fixture.json",
    "segmentos_fixture.json",
    "probe_fixture.json",
    "captions_fixture.ass",
    "overlay_fixture/00001.png",
    "mix_fixture.wav",
    "emoji_fixture.gif",
    "plan_fixture.yaml",
]


def test_all_fixtures_exist(fixtures_dir: Path) -> None:
    for rel in EXPECTED:
        assert (fixtures_dir / rel).is_file(), rel


def test_base_fixture_properties(base_video: Path) -> None:
    data = ffmpeg.probe(base_video)
    v = next(s for s in data["streams"] if s["codec_type"] == "video")
    assert (v["width"], v["height"], v["r_frame_rate"]) == (1080, 1920, "30/1")
    assert abs(float(data["format"]["duration"]) - 12.0) < 0.1
    assert any(s["codec_type"] == "audio" for s in data["streams"])


def test_no_audio_fixture(fixtures_dir: Path) -> None:
    data = ffmpeg.probe(fixtures_dir / "sin_audio.mp4")
    assert not any(s["codec_type"] == "audio" for s in data["streams"])


def test_ffmpeg_handles_spaces_and_accents(spaced_video: Path, tmp_path: Path) -> None:
    log = tmp_path / "logs" / "comandos.jsonl"
    data = ffmpeg.probe(spaced_video)
    assert data["format"]["duration"]
    ffmpeg.run(
        ["-i", spaced_video.name, "-frames:v", "1", str(tmp_path / "cuadro ñ.png")],
        cwd=spaced_video.parent,
        log_path=log,
    )
    assert (tmp_path / "cuadro ñ.png").exists()
    assert log.read_text(encoding="utf-8").count("\n") == 1


def test_overlay_has_alpha(fixtures_dir: Path) -> None:
    from PIL import Image

    im = Image.open(fixtures_dir / "overlay_fixture" / "00001.png")
    assert im.mode == "RGBA"
    alphas = set(im.getchannel("A").tobytes())
    assert 0 in alphas and max(alphas) > 200


def test_fixture_documents_are_valid(fixtures_dir: Path) -> None:
    tr = read_model(fixtures_dir / "transcript_fixture.json", Transcript)
    assert any(w.flagged for w in tr.words)
    plan = read_model(fixtures_dir / "plan_fixture.yaml", EditPlan)
    assert plan.captions.emphasis[0].word < len(tr.words)


def test_fixture_project(fixture_project: ProjectContext) -> None:
    ctx = fixture_project
    orig = ctx.original_video()
    assert is_read_only(orig)
    assert ctx.load_config().original_sha256 == sha256_file(orig)
    assert ctx.load_probe().width == 1080
    assert ctx.load_transcript().words
    assert ctx.next_version() == "V1"


def test_base_transform() -> None:
    c = Canvas()
    t = base_transform(1080, 1920, c)
    assert t.scale == 1 and not t.upscaled
    t2 = base_transform(720, 1280, c)
    assert t2.upscaled
    t3 = base_transform(1920, 1080, c, face=Box(x=1200, y=100, w=300, h=300))
    assert t3.cropped_horizontal and t3.crop_w == 608 and t3.crop_x > 900
