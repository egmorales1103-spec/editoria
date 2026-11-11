"""doctor: OK/FALTA/AVISO table and blocking exit code."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from editoria import doctor
from editoria.cli import app
from editoria.doctor import Check, has_blocking_failures, run_checks
from editoria.util import ffmpeg

runner = CliRunner()


def _by_name(checks: list[Check]) -> dict[str, Check]:
    return {c.name: c for c in checks}


@pytest.fixture
def empty_caches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the whisper and Playwright caches to empty folders."""
    (tmp_path / "hf").mkdir()
    (tmp_path / "pw").mkdir()
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path / "hf"))
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(tmp_path / "pw"))
    return tmp_path


# ---- the real environment ---------------------------------------------------------------------
def test_real_environment_has_ffmpeg_filters_and_libass(projects_dir: Path) -> None:
    checks = _by_name(run_checks(projects_dir))
    assert checks["ffmpeg"].ok and checks["ffprobe"].ok and checks["ffmpeg ≥ 6"].ok
    for name in doctor.REQUIRED_FILTERS:
        assert checks[f"filtro {name}"].ok, name
    assert checks["libass"].ok
    assert checks["Espacio libre"].status in {"OK", "AVISO"}
    assert checks["Permisos de escritura"].ok


# ---- blocking failures ---------------------------------------------------------------------------
def test_missing_ffmpeg_is_blocking_and_explains_the_fix_per_os(
    projects_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def gone(tool: str = "ffmpeg") -> str:
        raise ffmpeg.FFmpegNotFound(tool)

    monkeypatch.setattr(ffmpeg, "executable", gone)
    checks = run_checks(projects_dir)
    by = _by_name(checks)
    assert by["ffmpeg"].status == "FALTA"
    assert "winget install" in by["ffmpeg"].fix
    assert "brew install ffmpeg" in by["ffmpeg"].fix
    assert "apt install ffmpeg" in by["ffmpeg"].fix
    assert has_blocking_failures(checks)


def test_old_ffmpeg_is_blocking(projects_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ffmpeg, "version", lambda: (5, 1))
    by = _by_name(run_checks(projects_dir))
    assert by["ffmpeg ≥ 6"].status == "FALTA" and "5.1" in by["ffmpeg ≥ 6"].detail


def test_missing_filter_is_blocking(projects_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    real = ffmpeg.has_filter
    monkeypatch.setattr(ffmpeg, "has_filter", lambda n: False if n == "scdet" else real(n))
    checks = run_checks(projects_dir)
    by = _by_name(checks)
    assert by["filtro scdet"].status == "FALTA" and by["filtro loudnorm"].ok
    assert has_blocking_failures(checks)


def test_missing_chromium_is_blocking_and_present_chromium_is_ok(
    projects_dir: Path, empty_caches: Path
) -> None:
    by = _by_name(run_checks(projects_dir))
    assert by["Chromium de Playwright"].status == "FALTA"
    assert "playwright install chromium" in by["Chromium de Playwright"].fix
    (empty_caches / "pw" / "chromium-1234").mkdir()
    assert _by_name(run_checks(projects_dir))["Chromium de Playwright"].ok


def test_low_disk_space_levels(projects_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def usage(free_gb: float):  # type: ignore[no-untyped-def]
        return lambda _p: SimpleNamespace(total=1, used=0, free=int(free_gb * 1e9))

    monkeypatch.setattr(doctor.shutil, "disk_usage", usage(0.2))
    assert _by_name(run_checks(projects_dir))["Espacio libre"].status == "FALTA"
    monkeypatch.setattr(doctor.shutil, "disk_usage", usage(3))
    low = _by_name(run_checks(projects_dir))["Espacio libre"]
    assert low.status == "AVISO" and not low.blocking
    monkeypatch.setattr(doctor.shutil, "disk_usage", usage(200))
    assert _by_name(run_checks(projects_dir))["Espacio libre"].ok


def test_unwritable_projects_folder_is_blocking(tmp_path: Path) -> None:
    a_file = tmp_path / "archivo.txt"
    a_file.write_text("x", encoding="utf-8")
    checks = run_checks(a_file / "proyectos")  # parent is a file: cannot create anything there
    assert _by_name(checks)["Permisos de escritura"].status == "FALTA"
    assert has_blocking_failures(checks)


def test_doctor_does_not_create_the_projects_folder(tmp_path: Path) -> None:
    target = tmp_path / "todavia no existe"
    assert _by_name(run_checks(target))["Permisos de escritura"].ok
    assert not target.exists()


# ---- warnings never block ------------------------------------------------------------------------
def test_missing_whisper_model_is_only_a_warning(projects_dir: Path, empty_caches: Path) -> None:
    by = _by_name(run_checks(projects_dir))
    model = by["Modelo whisper en caché"]
    assert model.status == "AVISO" and not model.blocking
    assert not has_blocking_failures([model])
    (empty_caches / "hf" / "models--Systran--faster-whisper-small").mkdir()
    cached = _by_name(run_checks(projects_dir))["Modelo whisper en caché"]
    assert cached.ok and "small" in cached.detail


def test_has_blocking_failures_semantics() -> None:
    ok = Check("a", "OK")
    warn = Check("b", "AVISO", blocking=False)
    soft = Check("c", "FALTA", blocking=False)
    hard = Check("d", "FALTA")
    assert not has_blocking_failures([ok, warn, soft])
    assert has_blocking_failures([ok, hard])
    assert not has_blocking_failures([])


# ---- CLI ---------------------------------------------------------------------------------------------
def test_cli_doctor_exit_codes(monkeypatch: pytest.MonkeyPatch) -> None:
    good = [Check("ffmpeg", "OK"), Check("Modelo whisper en caché", "AVISO", "x", blocking=False)]
    monkeypatch.setattr(doctor, "run_checks", lambda *a, **k: good)
    res = runner.invoke(app, ["doctor"], terminal_width=200)
    assert res.exit_code == 0, res.output
    assert "OK" in res.output and "AVISO" in res.output

    bad = [Check("ffmpeg", "FALTA", "No está en el PATH.", doctor.FFMPEG_FIX)]
    monkeypatch.setattr(doctor, "run_checks", lambda *a, **k: bad)
    res = runner.invoke(app, ["doctor"], terminal_width=200)
    assert res.exit_code == 1
    assert "FALTA" in res.output and "winget" in res.output
