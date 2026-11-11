from __future__ import annotations

from typer.testing import CliRunner

from editoria.cli import app

runner = CliRunner()

TOP_LEVEL = [
    "doctor",
    "init",
    "probe",
    "transcribe",
    "analyze",
    "version",
    "feedback",
    "plan",
    "captions",
    "graphics",
    "audio",
    "render",
    "contact-sheet",
    "qc",
    "shots",
    "propose",
    "deliver",
    "run",
]

SUBCOMMANDS = {
    "version": ["new"],
    "feedback": ["parse"],
    "plan": ["draft", "lint"],
    "captions": ["build"],
    "graphics": ["list", "preview", "render"],
    "audio": ["sfx", "mix", "check-voice"],
    "shots": ["pack", "import", "compare", "verdict", "budget"],
}


def test_help_lists_every_command() -> None:
    res = runner.invoke(app, ["--help"], terminal_width=200)
    assert res.exit_code == 0, res.output
    for cmd in TOP_LEVEL:
        assert cmd in res.output, f"falta '{cmd}' en --help"


def test_groups_list_subcommands() -> None:
    for group, subs in SUBCOMMANDS.items():
        res = runner.invoke(app, [group, "--help"], terminal_width=200)
        assert res.exit_code == 0, res.output
        for sub in subs:
            assert sub in res.output, f"falta '{group} {sub}'"


def test_version_flag() -> None:
    res = runner.invoke(app, ["--version"])
    assert res.exit_code == 0 and "editoria" in res.output
