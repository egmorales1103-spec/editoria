"""versioning: feedback parsing from the real template and immutable versions (P20)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from editoria.cli import app
from editoria.ingest import IngestError
from editoria.schemas import Feedback, FeedbackItem, read_model
from editoria.util.project import ProjectContext
from editoria.versioning import new_version, parse_feedback, save_feedback
from editoria.versioning.feedback import parse_range, parse_time

runner = CliRunner()
REPO = Path(__file__).resolve().parents[2]
TEMPLATE = REPO / "templates" / "docs" / "Feedback_V1.md"
EXAMPLE_ROW = "| 00:00–00:00 | Toma / ritmo / subtítulo / gráfico / sonido | | |"


def _flat(text: str) -> str:
    return " ".join(text.split())


def completed_template(*rows: str) -> str:
    """The REAL template with the general impression filled and ``rows`` replacing the example."""
    text = TEMPLATE.read_text(encoding="utf-8")
    assert EXAMPLE_ROW in text, "la plantilla cambió: actualizar el test"
    text = text.replace(
        "- Propuesta que prefiero: A / B / C / combinación concreta.",
        "- Propuesta que prefiero: B con los gráficos de la C.",
    )
    text = text.replace("- Quiero conservar:", "- Quiero conservar: el ritmo del arranque.")
    text = text.replace("- Quiero cambiar:", "- Quiero cambiar: menos efectos al final.")
    text = text.replace(
        "- ¿Me reconozco sin cambios artificiales de cara o cuerpo?",
        "- ¿Me reconozco sin cambios artificiales de cara o cuerpo? Sí",
    )
    text = text.replace(
        "- ¿La voz domina la mezcla?", "- ¿La voz domina la mezcla?: No siempre, bajar el pop"
    )
    return text.replace(EXAMPLE_ROW, "\n".join(rows))


@pytest.fixture
def delivered(fixture_project: ProjectContext, fixtures_dir: Path) -> ProjectContext:
    """'demo' with a V1 plan (as if produced by the director)."""
    v1 = fixture_project.version_dir("V1")
    v1.mkdir(parents=True)
    shutil.copy2(fixtures_dir / "plan_fixture.yaml", v1 / "plan.yaml")
    return fixture_project


def _md(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "Feedback V1 ñ.md"
    path.write_text(text, encoding="utf-8")
    return path


# ---- time formats -----------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("cell", "expected"),
    [
        ("00:12–00:15", (12.0, 15.0)),
        ("00:12-00:15", (12.0, 15.0)),
        ("0:12 — 0:15", (12.0, 15.0)),
        ("01:02.5–01:04", (62.5, 64.0)),
        ("12.5-14", (12.5, 14.0)),
        ("12,5 – 14,25", (12.5, 14.25)),
        ("7", (7.0, 7.0)),
        ("00:30", (30.0, 30.0)),
        ("1:01:01", (3661.0, 3661.0)),
    ],
)
def test_parse_range_accepts_every_supported_format(
    cell: str, expected: tuple[float, float]
) -> None:
    assert parse_range(cell) == expected


@pytest.mark.parametrize("cell", ["", "pronto", "00:75-00:80", "00:20-00:10", "1:2:3:4"])
def test_parse_range_rejects_nonsense(cell: str) -> None:
    with pytest.raises(ValueError, match=r"."):
        parse_range(cell)


def test_parse_time_values() -> None:
    assert parse_time("02:03.5") == 123.5
    assert parse_time("45") == 45.0


# ---- parse_feedback on the real template --------------------------------------------------------
def test_untouched_template_is_rejected_as_empty() -> None:
    # An empty feedback must not be saved: it would block the real one (R2 review).
    with pytest.raises(IngestError, match="vacío"):
        parse_feedback(TEMPLATE, "V1")


def test_completed_template_is_parsed(tmp_path: Path) -> None:
    md = _md(
        tmp_path,
        completed_template(
            "| 00:02–00:04.5 | subtítulo | Más grande | Que se lea en una mirada |",
            "| 0:07 - 0:09 | gráfico | Quitar el emoji | Solo la palabra clave |",
            "| 12.5–14 | sonido | Bajar el pop | -20 dB |",
            "| 01:05 | ritmo | Cortar la pausa | Sin silencio |",
            "| | | | |",
            "| 00:00–00:00 | Toma / ritmo / subtítulo / gráfico / sonido | | |",
        ),
    )
    fb = parse_feedback(md, "V1")
    assert fb.preferred == "B con los gráficos de la C."
    assert fb.keep == "el ritmo del arranque."
    assert fb.change == "menos efectos al final."
    assert fb.items == [
        FeedbackItem(
            t_in=2.0, t_out=4.5, element="subtítulo", change="Más grande",
            desired="Que se lea en una mirada",
        ),
        FeedbackItem(
            t_in=7.0, t_out=9.0, element="gráfico", change="Quitar el emoji",
            desired="Solo la palabra clave",
        ),
        FeedbackItem(t_in=12.5, t_out=14.0, element="sonido", change="Bajar el pop", desired="-20 dB"),
        FeedbackItem(
            t_in=65.0, t_out=65.0, element="ritmo", change="Cortar la pausa", desired="Sin silencio"
        ),
    ]  # fmt: skip
    assert fb.quick_review == {
        "¿Me reconozco sin cambios artificiales de cara o cuerpo?": "Sí",
        "¿La voz domina la mezcla?": "No siempre, bajar el pop",
    }


def test_empty_and_example_rows_are_ignored(tmp_path: Path) -> None:
    md = _md(
        tmp_path,
        completed_template(
            "| 00:00–00:00 | Toma / ritmo / subtítulo / gráfico / sonido | | |",
            "| | | | |",
            "| 00:05–00:07 | subtítulo | | |",
        ),
    )
    assert parse_feedback(md, "V1").items == []


def test_row_with_content_but_bad_time_is_an_error_not_a_guess(tmp_path: Path) -> None:
    md = _md(
        tmp_path,
        completed_template(
            "| al principio | subtítulo | Más grande | Legible |",
            "| 00:05–00:07 | gráfico | Quitar | |",
        ),
    )
    with pytest.raises(IngestError) as exc:
        parse_feedback(md, "V1")
    assert "al principio" in str(exc.value) or "Más grande" in str(exc.value)
    assert "no se entiende el tiempo" in str(exc.value)


def test_invalid_version_and_missing_file(tmp_path: Path) -> None:
    with pytest.raises(IngestError, match="Versión inválida"):
        parse_feedback(TEMPLATE, "v1")
    with pytest.raises(IngestError, match="No existe el archivo"):
        parse_feedback(tmp_path / "nada.md", "V1")


# ---- save_feedback / feedback parse CLI -------------------------------------------------------
def test_save_feedback_writes_json_and_does_not_overwrite(
    delivered: ProjectContext, tmp_path: Path
) -> None:
    fb = parse_feedback(
        _md(tmp_path, completed_template("| 00:02–00:04 | subtítulo | Más grande | Legible |")),
        "V1",
    )
    out = save_feedback(delivered, fb)
    assert out == delivered.version_dir("V1") / "feedback.json"
    assert read_model(out, Feedback) == fb
    with pytest.raises(IngestError, match="--force"):
        save_feedback(delivered, fb)
    save_feedback(delivered, fb, force=True)


def test_save_feedback_needs_an_existing_version(
    fixture_project: ProjectContext,
) -> None:
    with pytest.raises(IngestError, match="No existe la versión V1"):
        save_feedback(fixture_project, Feedback(version="V1"))


def test_cli_feedback_parse(delivered: ProjectContext, tmp_path: Path) -> None:
    md = _md(tmp_path, completed_template("| 00:02–00:04 | subtítulo | Más grande | Legible |"))
    res = runner.invoke(app, ["feedback", "parse", "demo", str(md)])
    assert res.exit_code == 0, res.output
    assert "1 cambio(s)" in _flat(res.output)
    assert read_model(delivered.version_dir("V1") / "feedback.json", Feedback).items[0].t_in == 2.0
    again = runner.invoke(app, ["feedback", "parse", "demo", str(md)])
    assert again.exit_code == 1 and "feedback.json" in _flat(again.output)


def test_cli_feedback_parse_bad_row(delivered: ProjectContext, tmp_path: Path) -> None:
    md = _md(tmp_path, completed_template("| ayer | gráfico | Quitar | Nada |"))
    res = runner.invoke(app, ["feedback", "parse", "demo", str(md)])
    assert res.exit_code == 1
    assert "Corregí estas filas" in _flat(res.output)
    assert not (delivered.version_dir("V1") / "feedback.json").exists()


# ---- P20: version new --------------------------------------------------------------------------
def test_p20_new_version_requires_parsed_feedback(delivered: ProjectContext) -> None:
    with pytest.raises(IngestError, match="Falta el feedback de V1"):
        new_version(delivered, "V1")
    assert delivered.versions() == ["V1"]


def test_p20_new_version_copies_the_plan_when_feedback_exists(
    delivered: ProjectContext, tmp_path: Path
) -> None:
    save_feedback(
        delivered,
        parse_feedback(
            _md(tmp_path, completed_template("| 00:02–00:04 | sonido | Bajar | -20 dB |")), "V1"
        ),
    )
    v1_plan = (delivered.version_dir("V1") / "plan.yaml").read_bytes()
    assert new_version(delivered, "V1") == "V2"

    assert delivered.versions() == ["V1", "V2"]
    plan2 = delivered.load_plan("V2")
    plan1 = delivered.load_plan("V1")
    assert plan2.version == "V2"
    assert plan2.model_dump(exclude={"version"}) == plan1.model_dump(exclude={"version"})
    assert (delivered.version_dir("V1") / "plan.yaml").read_bytes() == v1_plan, "V1 intacta"


def test_p20_new_version_never_overwrites_an_existing_version(
    delivered: ProjectContext, tmp_path: Path
) -> None:
    save_feedback(
        delivered,
        parse_feedback(_md(tmp_path, completed_template("| 00:02 | sonido | Bajar | x |")), "V1"),
    )
    new_version(delivered, "V1")
    marker = delivered.version_dir("V2") / "notas.txt"
    marker.write_text("trabajo en curso", encoding="utf-8")
    with pytest.raises(IngestError, match="Ya existe V2"):
        new_version(delivered, "V1")
    assert marker.read_text(encoding="utf-8") == "trabajo en curso"
    assert delivered.versions() == ["V1", "V2"]


def test_p20_new_version_errors(delivered: ProjectContext, tmp_path: Path) -> None:
    with pytest.raises(IngestError, match="No existe la versión V7"):
        new_version(delivered, "V7")
    with pytest.raises(IngestError, match="Versión inválida"):
        new_version(delivered, "primera")
    # feedback.json that belongs to another version is rejected
    fb = Feedback(version="V3")
    (delivered.version_dir("V1") / "feedback.json").write_text(
        fb.model_dump_json(), encoding="utf-8"
    )
    with pytest.raises(IngestError, match="corresponde a V3"):
        new_version(delivered, "V1")
    # a version without plan has nothing to copy
    (delivered.version_dir("V1") / "plan.yaml").unlink()
    with pytest.raises(IngestError, match=r"no tiene plan\.yaml"):
        new_version(delivered, "V1")


def test_cli_version_new(delivered: ProjectContext, tmp_path: Path) -> None:
    refused = runner.invoke(app, ["version", "new", "demo", "--from", "V1"])
    assert refused.exit_code == 1
    assert "Falta el feedback de V1" in _flat(refused.output)
    assert not delivered.version_dir("V2").exists()

    md = _md(tmp_path, completed_template("| 00:02–00:04 | sonido | Bajar | -20 dB |"))
    assert runner.invoke(app, ["feedback", "parse", "demo", str(md)]).exit_code == 0
    ok = runner.invoke(app, ["version", "new", "demo", "--from", "V1"])
    assert ok.exit_code == 0, ok.output
    assert "Creada V2" in _flat(ok.output)
    assert (delivered.version_dir("V2") / "plan.yaml").exists()
    again = runner.invoke(app, ["version", "new", "demo", "--from", "V1"])
    assert again.exit_code == 1 and "Ya existe V2" in _flat(again.output)
