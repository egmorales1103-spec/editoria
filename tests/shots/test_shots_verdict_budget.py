from __future__ import annotations

import json

import pytest

from editoria.contracts import ShotLibrary
from editoria.shots import (
    BudgetError,
    ProjectShotLibrary,
    ShotError,
    budget_status,
    ensure_budget,
    import_shot,
    pack_shot,
    record_credit,
    set_verdict,
)
from editoria.util.files import read_csv_rows
from editoria.util.project import ProjectContext


# ---------------------------------------------------------------- verdict
def test_verdict_writes_csv(packed, fixtures_dir):  # type: ignore[no-untyped-def]
    ctx, _ = packed
    import_shot(ctx, "G01", fixtures_dir / "generada_ok.mp4")
    set_verdict(ctx, "g01", "aceptado", "fondo y rostro iguales", fondo="ok", manos="ok")
    row = read_csv_rows(ctx.generations_registry)[0]
    assert row["veredicto"] == "aceptado"
    assert row["motivo"] == "fondo y rostro iguales"
    assert (row["fondo"], row["manos"], row["identidad"]) == ("ok", "ok", "")
    assert list(row) == list(
        read_csv_rows(ctx.generations_registry)[0]
    )  # column order preserved on rewrite


def test_cannot_accept_without_result(packed):  # type: ignore[no-untyped-def]
    ctx, _ = packed
    with pytest.raises(ShotError, match="no tiene un resultado"):
        set_verdict(ctx, "G01", "aceptado", "sin mirar")
    assert read_csv_rows(ctx.generations_registry)[0]["veredicto"] == "pendiente"


def test_verdict_validation(packed, fixtures_dir):  # type: ignore[no-untyped-def]
    ctx, _ = packed
    with pytest.raises(ShotError, match="Veredicto inválido"):
        set_verdict(ctx, "G01", "pendiente", "x")
    with pytest.raises(ShotError, match="motivo"):
        set_verdict(ctx, "G01", "descartado", "  ")
    with pytest.raises(ShotError, match="No existe la toma"):
        set_verdict(ctx, "G07", "descartado", "x")


def test_retry_respects_max_attempts(fixture_project: ProjectContext, set_config):  # type: ignore[no-untyped-def]
    set_config(fixture_project, tool_limits={"higgsfield_max_clip_s": None, "max_attempts": 2})
    ctx = fixture_project
    pack_shot(ctx, 1.0, 3.0, "plano más cerrado")
    set_verdict(ctx, "G01", "reintentar", "fondo cambia")
    second = pack_shot(ctx, 1.0, 3.0, "plano más cerrado, más suave", retry_of="G01")
    assert (second.id, second.attempt, second.root) == ("G02", 2, "G01")
    with pytest.raises(ShotError, match="intento 2 de 2"):
        set_verdict(ctx, "G02", "reintentar", "otra vez")
    set_verdict(ctx, "G02", "descartado", "se conserva el original")
    with pytest.raises(ShotError, match=r"descartado|reintentar"):
        pack_shot(ctx, 1.0, 3.0, "x", retry_of="G02")


def test_retry_blocked_by_attempt_limit_in_pack(fixture_project: ProjectContext, set_config):  # type: ignore[no-untyped-def]
    set_config(fixture_project, tool_limits={"higgsfield_max_clip_s": None, "max_attempts": 1})
    pack_shot(fixture_project, 1.0, 3.0, "plano más cerrado")
    with pytest.raises(ShotError, match="intento 1 de 1"):
        set_verdict(fixture_project, "G01", "reintentar", "no")


# ---------------------------------------------------------------- library
def test_library_returns_only_accepted(packed, fixtures_dir):  # type: ignore[no-untyped-def]
    ctx, _ = packed
    pack_shot(ctx, 8.5, 10.5, "otra variación sutil")
    import_shot(ctx, "G01", fixtures_dir / "generada_ok.mp4")
    import_shot(ctx, "G02", fixtures_dir / "generada_mala.mp4")
    lib = ProjectShotLibrary()
    assert isinstance(lib, ShotLibrary)
    assert lib.accepted(ctx) == {}  # pending shots are never exposed

    set_verdict(ctx, "G01", "aceptado", "ok")
    set_verdict(ctx, "G02", "descartado", "deriva")
    clips = lib.accepted(ctx)
    assert list(clips) == ["G01"]
    clip = clips["G01"]
    assert (clip.start, clip.end) == (8.5, 10.5)
    assert (clip.width, clip.height) == (1080, 1920)
    assert clip.path.is_file()


# ---------------------------------------------------------------- budget
def test_budget_blocks_without_limit(fixture_project: ProjectContext):
    with pytest.raises(BudgetError, match="No hay un límite"):
        ensure_budget(fixture_project, 0)
    with pytest.raises(BudgetError, match="No hay un límite"):
        ensure_budget(fixture_project, 5)


def test_budget_blocks_when_exceeded(fixture_project: ProjectContext, set_config):  # type: ignore[no-untyped-def]
    set_config(fixture_project, budget={"unit": "creditos", "limit": 20.0, "spent": 0.0})
    ensure_budget(fixture_project, 20)  # exactly the limit is fine
    record_credit(fixture_project, 15, "G01")
    ensure_budget(fixture_project, 5)
    with pytest.raises(BudgetError, match="supera"):
        ensure_budget(fixture_project, 5.5)
    with pytest.raises(BudgetError, match="no es válido"):
        ensure_budget(fixture_project, -1)
    status = budget_status(fixture_project)
    assert (status.limit, status.spent, status.remaining) == (20.0, 15.0, 5.0)


def test_budget_uses_larger_of_ledger_and_yaml(fixture_project: ProjectContext, set_config):  # type: ignore[no-untyped-def]
    set_config(fixture_project, budget={"unit": "creditos", "limit": 20.0, "spent": 18.0})
    record_credit(fixture_project, 1, "x")
    assert budget_status(fixture_project).spent == 18.0
    with pytest.raises(BudgetError):
        ensure_budget(fixture_project, 3)


def test_budget_corrupt_ledger_blocks(fixture_project: ProjectContext, set_config):  # type: ignore[no-untyped-def]
    set_config(fixture_project, budget={"unit": "creditos", "limit": 20.0, "spent": 0.0})
    fixture_project.logs_dir.mkdir(exist_ok=True)
    fixture_project.credits_log.write_text("{no es json\n", encoding="utf-8")
    with pytest.raises(BudgetError, match="dañado"):
        ensure_budget(fixture_project, 1)
    fixture_project.credits_log.write_text(json.dumps({"detail": "sin monto"}) + "\n")
    with pytest.raises(BudgetError, match="amount"):
        ensure_budget(fixture_project, 1)
