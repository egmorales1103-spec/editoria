"""plan draft: the three styles on the fixture project pass the linter without ERROR."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from editoria.cli import app
from editoria.contracts import PlanTools
from editoria.planning import DefaultPlanTools, draft_plan, find_emphasis, parse_window
from editoria.policy import has_errors, lint_plan
from editoria.schemas import EditPlan, Word, read_model
from editoria.util.project import ProjectContext

runner = CliRunner()
CUTS = (4.0, 7.85)


def _check_structure(plan: EditPlan, ctx: ProjectContext) -> None:
    words = ctx.load_transcript().words
    # video track: contiguous, ordered, reframes never span a camera cut
    for a, b in zip(plan.video, plan.video[1:], strict=False):
        assert abs(a.out - b.in_) < 1e-6
    for v in plan.video:
        if v.method == "reframe":
            assert not any(v.in_ < c < v.out for c in CUTS), v
            assert v.zoom is not None and 1.0 < v.zoom <= 1.25
    # hook graphic inside the hook segment (s01 0.3-2.2)
    assert len(plan.graphics) == 1
    g = plan.graphics[0]
    assert g.template in ("titulo_gancho", "palabra_clave")
    assert 0.3 <= g.in_ < g.out <= 2.2 + 1e-6
    # SFX only at graphic entries and reframe starts
    starts = {g.in_ for g in plan.graphics} | {v.in_ for v in plan.video if v.method == "reframe"}
    for cue in plan.sfx:
        assert any(abs(cue.at - s) <= 0.05 for s in starts), cue
    # emphasis on glossary terms ("automatizar", "inteligencia artificial", "procesos")
    emph = {words[e.word].text for e in plan.captions.emphasis}
    assert "automatizar" in emph


@pytest.mark.parametrize("style_id", ["A", "B", "C"])
def test_draft_passes_linter(project: ProjectContext, style_id: str) -> None:
    style = project.load_style(style_id)
    plan = DefaultPlanTools().draft(project, style)
    assert plan.style == style_id and plan.captions.style == style_id
    findings = lint_plan(plan, project)
    assert not has_errors(findings), findings
    _check_structure(plan, project)
    assert plan.sfx, "con manifest con licencia el borrador agrega SFX"


@pytest.mark.parametrize("style_id", ["A", "B", "C"])
def test_draft_without_cuts_or_manifests(
    fixture_project: ProjectContext, style_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No cortes.json and no SFX manifest: still lint-clean (SFX are omitted with a note)."""
    from editoria.schemas import AssetManifest
    from editoria.util import resources

    monkeypatch.setattr(resources, "load_sfx_manifest", lambda: AssetManifest())
    plan = draft_plan(fixture_project, fixture_project.load_style(style_id))
    findings = lint_plan(plan, fixture_project)
    assert not has_errors(findings), findings
    assert plan.sfx == []
    assert "manifest" in plan.notes


def test_reframe_ends_at_cut(project: ProjectContext) -> None:
    plan = draft_plan(project, project.load_style("A"))
    reframes = [v for v in plan.video if v.method == "reframe"]
    assert reframes, plan.video
    # cadence 7 s: the idea change at 5.5 s opens a reframe that must stop at the 7.85 s cut
    assert reframes[0].in_ == pytest.approx(5.5)
    assert reframes[0].out == pytest.approx(7.85)


def test_draft_window(project: ProjectContext) -> None:
    plan = draft_plan(project, project.load_style("C"), window=(5.0, 11.0))
    assert plan.window == (5.0, 11.0)
    assert plan.video[0].in_ == pytest.approx(5.0) and plan.video[-1].out == pytest.approx(11.0)
    for g in plan.graphics:
        assert 5.0 <= g.in_ < g.out <= 11.0
    for cue in plan.sfx:
        assert 5.0 <= cue.at <= 11.0
    assert not has_errors(lint_plan(plan, project))


def test_default_tools_satisfy_contract() -> None:
    assert isinstance(DefaultPlanTools(), PlanTools)


def test_find_emphasis_terms_and_figures() -> None:
    words = [
        Word(text=t, start=i * 0.6, end=i * 0.6 + 0.5, prob=0.9)
        for i, t in enumerate(
            ["Con", "inteligencia", "artificial", "ahorrás", "40%", "del", "tiempo"]
        )
    ]
    picks = find_emphasis(words, ["inteligencia artificial", "IA"])
    assert picks == [1, 2, 4]


def test_parse_window() -> None:
    assert parse_window("2-9,5") == (2.0, 9.5)
    with pytest.raises(ValueError):
        parse_window("9-2")
    with pytest.raises(ValueError):
        parse_window("abc")


def test_cli_plan_draft_default_and_out(project: ProjectContext) -> None:
    res = runner.invoke(app, ["plan", "draft", "demo", "--style", "b"], terminal_width=200)
    assert res.exit_code == 0, res.output
    target = project.proposals_dir / "plan_B.yaml"
    plan = read_model(target, EditPlan)
    assert plan.style == "B"

    out = project.root / "carpeta con espacios" / "plan ñ.yaml"
    res = runner.invoke(
        app,
        ["plan", "draft", "demo", "--style", "A", "--out", str(out), "--window", "0-6"],
        terminal_width=200,
    )
    assert res.exit_code == 0, res.output
    assert read_model(out, EditPlan).window == (0.0, 6.0)

    res = runner.invoke(app, ["plan", "draft", "demo", "--style", "Z"], terminal_width=200)
    assert res.exit_code != 0
