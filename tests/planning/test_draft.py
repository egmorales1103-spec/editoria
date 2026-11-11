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
    # hook graphic inside the hook segment (s01 0.3-2.2), then the style's own graphics
    g = plan.graphics[0]
    assert g.template in ("titulo_gancho", "palabra_clave")
    assert 0.3 <= g.in_ < g.out <= 2.2 + 1e-6
    assert [x.id for x in plan.graphics] == [f"g{i + 1:02d}" for i in range(len(plan.graphics))]
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


# ---- distinct proposals (§8: "claramente distintas en composición, ritmo y gráficos") -------
def _template_set(plan: EditPlan) -> frozenset[str]:
    return frozenset(g.template or f"emoji {g.emoji}" for g in plan.graphics)


def test_three_drafts_have_distinct_graphics(fixture_project: ProjectContext) -> None:
    plans = {sid: draft_plan(fixture_project, fixture_project.load_style(sid)) for sid in "ABC"}
    sets = {sid: _template_set(p) for sid, p in plans.items()}
    assert len(set(sets.values())) == 3, sets
    assert "palabra_clave" in sets["A"]
    assert {"titulo_gancho", "checklist"} <= sets["B"]
    assert "titulo_gancho" in sets["C"]
    for sid, plan in plans.items():
        style = fixture_project.load_style(sid)
        assert all(
            g.template in style.graphics.allowed_templates for g in plan.graphics if g.template
        )
        assert not has_errors(lint_plan(plan, fixture_project)), (
            sid,
            lint_plan(plan, fixture_project),
        )


def test_draft_b_checklist_is_literal(project: ProjectContext) -> None:
    plan = draft_plan(project, project.load_style("B"))
    segs = project.load_segments().segments
    hook = next(g for g in plan.graphics if g.template == "titulo_gancho")
    assert hook.params["texto"].lower() in segs[0].text.lower()
    checklist = next(g for g in plan.graphics if g.template == "checklist")
    items = checklist.params["items"]
    assert 2 <= len(items) <= 3
    dev = [s.text.lower() for s in segs if s.role in ("body", "example")]
    for item in items:
        assert any(item.lower() in text for text in dev), item
    assert checklist.in_ >= hook.out
    assert checklist.zone == "lower"  # the fixture face is in the upper half
    assert not has_errors(lint_plan(plan, project))


def test_draft_c_upper_hook_and_closing_emoji(project: ProjectContext) -> None:
    plan = draft_plan(project, project.load_style("C"))
    hook = next(g for g in plan.graphics if g.template == "titulo_gancho")
    assert hook.params["texto"] == "HOY TE MUESTRO CÓMO AUTOMATIZAR"
    emoji = next(g for g in plan.graphics if g.is_emoji)
    assert emoji.emoji == "E03"
    assert 10.8 <= emoji.in_ < emoji.out <= 11.7 + 1e-6  # closing segment s05
    assert not has_errors(lint_plan(plan, project))


def test_draft_c_without_licensed_emoji(
    project: ProjectContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from editoria.schemas import AssetManifest
    from editoria.util import resources

    monkeypatch.setattr(resources, "load_external_manifest", lambda: AssetManifest())
    plan = draft_plan(project, project.load_style("C"))
    assert not any(g.is_emoji for g in plan.graphics)
    assert "emoji" in plan.notes


# ---- determinism ---------------------------------------------------------------------------
@pytest.mark.parametrize("style_id", ["A", "B", "C"])
def test_draft_is_deterministic(project: ProjectContext, style_id: str) -> None:
    style = project.load_style(style_id)
    first = draft_plan(project, style)
    second = draft_plan(project, style)
    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_cli_plan_draft_twice_writes_identical_files(project: ProjectContext) -> None:
    target = project.proposals_dir / "plan_C.yaml"
    contents = []
    for _ in range(2):
        res = runner.invoke(app, ["plan", "draft", "demo", "--style", "C"], terminal_width=200)
        assert res.exit_code == 0, res.output
        contents.append(target.read_bytes())
    assert contents[0] == contents[1]


# ---- write guards --------------------------------------------------------------------------
def test_cli_plan_draft_refuses_delivered_version_and_original(project: ProjectContext) -> None:
    from editoria.util.project import DELIVERED_MARKER

    vdir = project.version_dir("V1")
    vdir.mkdir(parents=True)
    (vdir / DELIVERED_MARKER).write_text("V1", encoding="utf-8")
    target = vdir / "plan.yaml"
    res = runner.invoke(app, ["plan", "draft", "demo", "--out", str(target)], terminal_width=200)
    assert res.exit_code != 0
    assert "entregada" in res.output and not target.exists()

    nested = vdir / "sub carpeta" / "plan.yaml"
    res = runner.invoke(app, ["plan", "draft", "demo", "--out", str(nested)], terminal_width=200)
    assert res.exit_code != 0 and not nested.exists()

    original = project.original_dir / "plan.yaml"
    res = runner.invoke(app, ["plan", "draft", "demo", "--out", str(original)], terminal_width=200)
    assert res.exit_code != 0
    assert "00_original" in res.output and not original.exists()

    elsewhere = project.root / "otra" / "00_original" / "p.yaml"
    res = runner.invoke(app, ["plan", "draft", "demo", "--out", str(elsewhere)], terminal_width=200)
    assert res.exit_code != 0 and not elsewhere.exists()
