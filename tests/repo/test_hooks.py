"""Tests for the Claude Code hooks in .claude/hooks (rules P01, P09, P20)."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[2]
HOOKS = REPO / ".claude" / "hooks"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"hook_{name}", HOOKS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


proteger = _load("proteger_original")
presupuesto = _load("guardar_presupuesto")


def payload(tool: str, cwd: Path, **tool_input: str) -> dict:
    return {"tool_name": tool, "cwd": str(cwd), "tool_input": tool_input}


@pytest.fixture()
def work(tmp_path: Path) -> Path:
    """A projects folder with a space and an accent, like the real one on Windows."""
    base = tmp_path / "mis proyectos ñ"
    (base / "proyectos" / "demo" / "00_original").mkdir(parents=True)
    (base / "proyectos" / "demo" / "04_versiones" / "V1").mkdir(parents=True)
    (base / "proyectos" / "demo" / "04_versiones" / "V2").mkdir(parents=True)
    (base / "proyectos" / "demo" / "proyecto.yaml").write_text("slug: demo\n", encoding="utf-8")
    return base


# ----------------------------------------------------------------- proteger_original: files
@pytest.mark.parametrize("tool", ["Write", "Edit", "MultiEdit"])
def test_blocks_writes_to_original(work: Path, tool: str) -> None:
    target = work / "proyectos" / "demo" / "00_original" / "video_base.mp4"
    reason = proteger.decide(payload(tool, work, file_path=str(target)))
    assert reason and "00_original" in reason and "P01" in reason


def test_blocks_relative_path_resolved_against_cwd(work: Path) -> None:
    reason = proteger.decide(
        payload("Write", work, file_path="proyectos/demo/00_original/video_base.sha256")
    )
    assert reason


def test_blocks_original_in_project_outside_proyectos_dir(tmp_path: Path) -> None:
    proj = tmp_path / "otra carpeta" / "slug"
    (proj / "00_original").mkdir(parents=True)
    (proj / "proyecto.yaml").write_text("slug: slug\n", encoding="utf-8")
    reason = proteger.decide(payload("Write", tmp_path, file_path=str(proj / "00_original" / "a")))
    assert reason


def test_allows_unrelated_00_original_folder(tmp_path: Path) -> None:
    other = tmp_path / "x" / "00_original"
    other.mkdir(parents=True)
    assert proteger.decide(payload("Write", tmp_path, file_path=str(other / "a.txt"))) is None


def test_allows_other_project_paths(work: Path) -> None:
    for sub in ("01_analisis/segmentos.json", "04_versiones/V1/plan.yaml", "proyecto.yaml"):
        target = work / "proyectos" / "demo" / sub
        assert proteger.decide(payload("Edit", work, file_path=str(target))) is None


def test_blocks_delivered_version_only(work: Path) -> None:
    v1 = work / "proyectos" / "demo" / "04_versiones" / "V1"
    (v1 / ".entregado").write_text("", encoding="utf-8")
    reason = proteger.decide(payload("Edit", work, file_path=str(v1 / "plan.yaml")))
    assert reason and "V1" in reason and "P20" in reason
    # next version stays editable
    v2_plan = work / "proyectos" / "demo" / "04_versiones" / "V2" / "plan.yaml"
    assert proteger.decide(payload("Edit", work, file_path=str(v2_plan))) is None


def test_version_without_marker_is_editable(work: Path) -> None:
    plan = work / "proyectos" / "demo" / "04_versiones" / "V1" / "plan.yaml"
    assert proteger.decide(payload("Write", work, file_path=str(plan))) is None


# ----------------------------------------------------------------- proteger_original: shell
ORIG = "proyectos/demo/00_original/video_base.mp4"


@pytest.mark.parametrize(
    "command",
    [
        f"rm {ORIG}",
        "rm -f proyectos/demo/00_original/*",
        f"mv {ORIG} /tmp/otro.mp4",
        f"echo hola > {ORIG}",
        "echo hola >> proyectos/demo/00_original/nota.txt",
        f"cp /tmp/x.mp4 {ORIG}",
        f"ffmpeg -y -i entrada.mp4 -c copy {ORIG}",
        "sed -i 's/a/b/' proyectos/demo/00_original/video_base.sha256",
        f"touch {ORIG}",
        f"chmod +w {ORIG}",
        f"ls && rm {ORIG}",
        "Remove-Item proyectos\\demo\\00_original\\video_base.mp4",
        "Set-Content -Path proyectos\\demo\\00_original\\x.txt -Value hola",
        'Copy-Item "C:\\tmp\\x.mp4" "proyectos\\demo\\00_original\\video_base.mp4"',
        f"python -c \"import os; os.remove('{ORIG}')\"",
    ],
)
def test_shell_blocks_mutations_of_original(work: Path, command: str) -> None:
    for tool in ("Bash", "PowerShell"):
        assert proteger.decide(payload(tool, work, command=command)), command


@pytest.mark.parametrize(
    "command",
    [
        f"cp {ORIG} /tmp/copia.mp4",
        f"ffprobe -v error -show_streams {ORIG}",
        f"ffmpeg -y -i {ORIG} -vf scale=540:960 salida.mp4",
        f"ffmpeg -i {ORIG} -f null -",
        f"cat {ORIG}",
        "ls -la proyectos/demo/00_original",
        f"sha256sum {ORIG}",
        "uv run editoria init video.mp4 --slug demo",
        "uv run editoria probe demo",
        "editoria qc demo --version V1",
        "echo hola > proyectos/demo/01_analisis/nota.txt",
        "Get-Content proyectos\\demo\\00_original\\video_base.sha256",
    ],
)
def test_shell_allows_reads_and_editoria(work: Path, command: str) -> None:
    for tool in ("Bash", "PowerShell"):
        assert proteger.decide(payload(tool, work, command=command)) is None, command


def test_shell_blocks_delivered_version(work: Path) -> None:
    v1 = work / "proyectos" / "demo" / "04_versiones" / "V1"
    (v1 / ".entregado").write_text("", encoding="utf-8")
    assert proteger.decide(
        payload("Bash", work, command="rm proyectos/demo/04_versiones/V1/video.mp4")
    )
    assert proteger.decide(
        payload("Bash", work, command="echo x > proyectos/demo/04_versiones/V1/n.md")
    )
    assert (
        proteger.decide(
            payload("Bash", work, command="rm proyectos/demo/04_versiones/V2/video.mp4")
        )
        is None
    )


def test_ignores_other_tools(work: Path) -> None:
    assert (
        proteger.decide(payload("Read", work, file_path=str(work / "proyectos/demo/00_original/a")))
        is None
    )
    assert proteger.decide({"tool_name": "Bash", "tool_input": {}}) is None


# ----------------------------------------------------------------- guardar_presupuesto
def make_project(base: Path, budget: str | None, slug: str = "demo") -> Path:
    proj = base / "proyectos" / slug
    proj.mkdir(parents=True, exist_ok=True)
    text = f"slug: {slug}\nbrand: master-solution\n"
    if budget is not None:
        text += budget
    (proj / "proyecto.yaml").write_text(text, encoding="utf-8")
    return proj


SUBMIT = "uv run editoria shots api submit demo --modelo x"


def test_budget_blocks_without_limit(tmp_path: Path) -> None:
    make_project(tmp_path, "budget:\n  unit: creditos\n  limit: null\n  spent: 0\n")
    reason = presupuesto.decide(payload("Bash", tmp_path, command=SUBMIT))
    assert reason and "budget.limit" in reason and "P09" in reason


def test_budget_blocks_without_budget_section(tmp_path: Path) -> None:
    make_project(tmp_path, None)
    assert presupuesto.decide(payload("PowerShell", tmp_path, command=SUBMIT))


def test_budget_blocks_zero_limit_and_exhausted(tmp_path: Path) -> None:
    make_project(tmp_path, "budget:\n  limit: 0\n  spent: 0\n")
    assert presupuesto.decide(payload("Bash", tmp_path, command=SUBMIT))
    make_project(tmp_path, "budget:\n  limit: 10\n  spent: 10\n")
    reason = presupuesto.decide(payload("Bash", tmp_path, command=SUBMIT))
    assert reason and "agotado" in reason


def test_budget_blocks_missing_project_or_slug(tmp_path: Path) -> None:
    assert presupuesto.decide(payload("Bash", tmp_path, command=SUBMIT))
    assert presupuesto.decide(payload("Bash", tmp_path, command="editoria shots api submit"))


def test_budget_allows_with_authorised_limit(tmp_path: Path) -> None:
    make_project(tmp_path, "budget:\n  unit: creditos\n  limit: 25\n  spent: 4.5\n")
    assert presupuesto.decide(payload("Bash", tmp_path, command=SUBMIT)) is None
    assert (
        presupuesto.decide(payload("Bash", tmp_path, command="editoria shots api submit demo"))
        is None
    )


def test_budget_honours_proyectos_option_and_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    other = tmp_path / "otra ruta"
    make_project(other, "budget:\n  limit: 5\n")
    cwd = tmp_path / "vacio"
    cwd.mkdir()
    cmd = f'editoria --proyectos "{other / "proyectos"}" shots api submit demo'
    assert presupuesto.decide(payload("Bash", cwd, command=cmd)) is None
    assert presupuesto.decide(payload("Bash", cwd, command=SUBMIT))  # no project in cwd
    monkeypatch.setenv("EDITORIA_PROJECTS", str(other / "proyectos"))
    assert presupuesto.decide(payload("Bash", cwd, command=SUBMIT)) is None


def test_budget_ignores_other_commands(tmp_path: Path) -> None:
    make_project(tmp_path, "budget:\n  limit: null\n")
    for cmd in (
        "editoria shots budget demo",
        "editoria shots api status demo",
        "editoria shots api estimate demo",
        "editoria shots pack demo --in 1 --out 2 --cambio x",
        "echo shots api",
    ):
        assert presupuesto.decide(payload("Bash", tmp_path, command=cmd)) is None, cmd
    assert presupuesto.decide(payload("Write", tmp_path, file_path="x")) is None


def test_budget_blocks_inside_compound_command(tmp_path: Path) -> None:
    make_project(tmp_path, "budget:\n  limit: null\n")
    assert presupuesto.decide(payload("Bash", tmp_path, command=f"echo hola && {SUBMIT}"))


def test_budget_fallback_parser_without_pyyaml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "yaml", None)  # makes "import yaml" raise ImportError
    cfg = make_project(
        tmp_path, "budget:\n  unit: creditos\n  limit: 12.5  # autorizado\n  spent: 2\n"
    )
    assert presupuesto._read_budget(cfg / "proyecto.yaml") == (12.5, 2.0)
    cfg = make_project(tmp_path, "budget:\n  limit: null\n  spent: 0\n")
    assert presupuesto._read_budget(cfg / "proyecto.yaml") == (None, 0.0)
    cfg = make_project(tmp_path, "other:\n  limit: 99\n")
    assert presupuesto._read_budget(cfg / "proyecto.yaml") == (None, 0.0)


# ----------------------------------------------------------------- as real subprocesses
def run_hook(name: str, data: dict | str, cwd: Path) -> subprocess.CompletedProcess[bytes]:
    raw = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    return subprocess.run(
        [sys.executable, str(HOOKS / f"{name}.py")],
        input=raw.encode("utf-8"),
        capture_output=True,
        cwd=cwd,
        check=False,
    )


def test_subprocess_exit_codes(work: Path) -> None:
    target = work / "proyectos" / "demo" / "00_original" / "video_base.mp4"
    blocked = run_hook("proteger_original", payload("Write", work, file_path=str(target)), work)
    assert blocked.returncode == 2
    assert "solo lectura" in blocked.stderr.decode("utf-8")  # UTF-8 on every platform
    ok = run_hook("proteger_original", payload("Write", work, file_path=str(work / "x.txt")), work)
    assert ok.returncode == 0 and ok.stderr == b""


def test_subprocess_ignores_invalid_json(tmp_path: Path) -> None:
    for name in ("proteger_original", "guardar_presupuesto"):
        assert run_hook(name, "esto no es json", tmp_path).returncode == 0


def test_subprocess_budget_block(tmp_path: Path) -> None:
    make_project(tmp_path, "budget:\n  limit: null\n")
    res = run_hook("guardar_presupuesto", payload("Bash", tmp_path, command=SUBMIT), tmp_path)
    assert res.returncode == 2 and b"budget.limit" in res.stderr


def test_settings_register_both_hooks() -> None:
    settings = json.loads((REPO / ".claude" / "settings.json").read_text(encoding="utf-8"))
    entries = settings["hooks"]["PreToolUse"]
    commands = {h["command"] for e in entries for h in e["hooks"]}
    assert any("proteger_original.py" in c for c in commands)
    assert any("guardar_presupuesto.py" in c for c in commands)
    matchers = {e["matcher"] for e in entries}
    joined = "|".join(matchers)
    for tool in ("Write", "Edit", "Bash", "PowerShell"):
        assert tool in joined
