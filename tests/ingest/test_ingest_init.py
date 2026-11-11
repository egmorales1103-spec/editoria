"""init: copy + hash + read-only (P01) and explicit video path (P02)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from editoria.cli import app
from editoria.ingest import IngestError, init_project
from editoria.ingest.workspace import slugify, validate_video
from editoria.util.files import is_read_only, sha256_file
from editoria.util.project import ProjectContext

runner = CliRunner()


def _flat(text: str) -> str:
    return " ".join(text.split())


# ---- P01: copy, hash, read-only -------------------------------------------------------------
def test_init_copies_original_with_hash_and_read_only(
    spaced_video: Path, projects_dir: Path
) -> None:
    before = sha256_file(spaced_video)
    ctx = init_project(spaced_video, "demo", "master-solution")

    original = ctx.original_video()
    assert original.name == "video_base.mp4"
    assert spaced_video.exists(), "init debe copiar, nunca mover"
    assert sha256_file(spaced_video) == before
    assert sha256_file(original) == before
    assert is_read_only(original)
    digest, name = ctx.original_sha256_path().read_text(encoding="utf-8").split()
    assert (digest, name) == (before, "video_base.mp4")

    cfg = ctx.load_config()
    assert cfg.slug == "demo"
    assert cfg.original == "00_original/video_base.mp4"
    assert cfg.original_sha256 == before
    assert cfg.source_name == "edición ñ.mp4"
    for d in ctx.all_dirs():
        assert d.is_dir()
    assert ProjectContext.open("demo").root == ctx.root


def test_init_hash_matches_disk_and_original_refuses_writes(ingested: ProjectContext) -> None:
    assert sha256_file(ingested.original_video()) == ingested.load_config().original_sha256
    with pytest.raises(PermissionError):
        ingested.original_video().open("ab")


def test_init_keeps_extension_in_lower_case(
    fixtures_dir: Path, projects_dir: Path, tmp_path: Path
) -> None:
    src = tmp_path / "Mi Video.MOV"
    src.write_bytes((fixtures_dir / "base_720x1280_25.mp4").read_bytes())
    ctx = init_project(src, "mov", "master-solution")
    assert ctx.original_video().name == "video_base.mov"


def test_init_never_overwrites_existing_slug(
    spaced_video: Path, base_video: Path, projects_dir: Path
) -> None:
    ctx = init_project(spaced_video, "demo", "master-solution")
    digest = sha256_file(ctx.original_video())
    with pytest.raises(IngestError, match="Ya existe el proyecto 'demo'"):
        init_project(base_video, "demo", "master-solution")
    assert sha256_file(ctx.original_video()) == digest
    assert ctx.load_config().source_name == "edición ñ.mp4"


def test_init_rejects_bad_slug_and_unknown_brand(spaced_video: Path, projects_dir: Path) -> None:
    with pytest.raises(IngestError, match="Slug inválido"):
        init_project(spaced_video, "Mi Proyecto!", "master-solution")
    with pytest.raises(IngestError, match="No existe la marca"):
        init_project(spaced_video, "ok", "marca-inexistente")
    assert list(projects_dir.iterdir()) == []


def test_init_leaves_nothing_behind_when_the_file_is_not_a_video(
    tmp_path: Path, projects_dir: Path
) -> None:
    fake = tmp_path / "texto.mp4"
    fake.write_text("no soy un video", encoding="utf-8")
    with pytest.raises(IngestError, match="no se pudo leer como video"):
        init_project(fake, "falso", "master-solution")
    assert list(projects_dir.iterdir()) == []


# ---- P02: explicit path ---------------------------------------------------------------------
def test_validate_video_accepts_an_explicit_existing_file(spaced_video: Path) -> None:
    assert validate_video(spaced_video) == spaced_video


@pytest.mark.parametrize("missing", [None, "", "   "])
def test_p02_missing_video_asks_only_for_the_file(missing: str | None) -> None:
    with pytest.raises(IngestError) as exc:
        validate_video(None if missing is None else Path(missing))
    msg = str(exc.value)
    assert "Falta el VIDEO_BASE" in msg
    assert "--brand" not in msg  # asks only for the file


def test_p02_nonexistent_video_and_folders_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(IngestError, match="No existe el VIDEO_BASE"):
        validate_video(tmp_path / "no existe.mp4")
    with pytest.raises(IngestError, match="es una carpeta"):
        validate_video(tmp_path)


def test_p02_reference_folder_is_not_a_valid_base(base_video: Path, tmp_path: Path) -> None:
    ref_dir = tmp_path / "02_Referencias_Usuario"
    ref_dir.mkdir()
    ref = ref_dir / "ref.mp4"
    ref.write_bytes(base_video.read_bytes())
    with pytest.raises(IngestError, match="referencia"):
        validate_video(ref)
    ok_dir = tmp_path / "grabaciones"
    ok_dir.mkdir()
    fine = ok_dir / "ref.mp4"
    fine.write_bytes(base_video.read_bytes())
    assert validate_video(fine) == fine


def test_slugify() -> None:
    assert slugify("Edición Ñandú 1!") == "edicion-nandu-1"
    assert slugify("!!!") == "proyecto"


# ---- CLI --------------------------------------------------------------------------------------
def test_cli_init_without_video_asks_for_the_video(projects_dir: Path) -> None:
    res = runner.invoke(app, ["init", "--slug", "x"])
    assert res.exit_code == 1
    assert "Falta el VIDEO_BASE" in _flat(res.output)
    assert list(projects_dir.iterdir()) == []


def test_cli_init_with_missing_file(projects_dir: Path) -> None:
    res = runner.invoke(app, ["init", str(projects_dir / "nada.mp4"), "--slug", "x"])
    assert res.exit_code == 1
    assert "No existe el VIDEO_BASE" in _flat(res.output)


def test_cli_init_ok_and_duplicate_slug(spaced_video: Path, projects_dir: Path) -> None:
    res = runner.invoke(app, ["init", str(spaced_video), "--slug", "demo"])
    assert res.exit_code == 0, res.output
    assert "creado" in res.output
    assert os.path.exists(projects_dir / "demo" / "00_original" / "video_base.mp4")
    again = runner.invoke(app, ["init", str(spaced_video), "--slug", "demo"])
    assert again.exit_code == 1
    assert "Ya existe el proyecto" in _flat(again.output)


def test_cli_init_derives_slug_from_file_name(spaced_video: Path, projects_dir: Path) -> None:
    res = runner.invoke(app, ["init", str(spaced_video)])
    assert res.exit_code == 0, res.output
    assert (projects_dir / "edicion-n" / "proyecto.yaml").exists()
