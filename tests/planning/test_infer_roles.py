"""Provisional roles let the three proposals differ even before the director fills roles."""

from __future__ import annotations

from editoria.planning.draft import draft_plan, infer_roles
from editoria.schemas import Segment, SegmentList, write_model
from editoria.util.project import SEGMENTS_FILE, ProjectContext


def _seg(i: int, role: str | None = None) -> Segment:
    return Segment(id=f"s{i}", start=float(i), end=i + 0.9, text=f"frase {i}", role=role)  # type: ignore[arg-type]


def test_infer_roles_only_when_none_set() -> None:
    roles = [s.role for s in infer_roles([_seg(i) for i in range(4)])]
    assert roles == ["hook", "body", "body", "closing"]
    manual = [_seg(0, "hook"), _seg(1), _seg(2), _seg(3)]
    assert infer_roles(manual) == manual  # director's work is never overwritten
    assert [s.role for s in infer_roles([_seg(0), _seg(1)])] == [None, None]


def test_proposals_differ_without_director_roles(fixture_project: ProjectContext) -> None:
    ctx = fixture_project
    segs = ctx.load_segments().segments
    write_model(
        ctx.analysis(SEGMENTS_FILE),
        SegmentList(segments=[s.model_copy(update={"role": None}) for s in segs]),
    )
    kinds = {
        sid: frozenset(
            g.template or f"emoji:{g.emoji}" for g in draft_plan(ctx, ctx.load_style(sid)).graphics
        )
        for sid in "ABC"
    }
    assert len(set(kinds.values())) == 3, kinds
