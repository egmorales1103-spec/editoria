"""DefaultPlanTools: implements editoria.contracts.PlanTools."""

from __future__ import annotations

from editoria.planning.draft import Window, draft_plan
from editoria.policy.linter import lint_plan
from editoria.schemas import EditPlan, Finding, StylePreset
from editoria.util.project import ProjectContext


class DefaultPlanTools:
    """Draft a plan for a style and lint it against the policies (section 6)."""

    def draft(
        self, ctx: ProjectContext, style: StylePreset, window: Window | None = None
    ) -> EditPlan:
        return draft_plan(ctx, style, window=window)

    def lint(self, plan: EditPlan, ctx: ProjectContext) -> list[Finding]:
        return lint_plan(plan, ctx)
