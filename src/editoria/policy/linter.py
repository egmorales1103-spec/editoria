"""Policy linter entry points: lint_plan(), lint_data(), lint_file(), has_errors()."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from editoria.policy.context import LintContext
from editoria.policy.rules import RULES, finding
from editoria.schemas import EditPlan, Finding
from editoria.util.project import ProjectContext

_SEVERITY_ORDER = {"ERROR": 0, "WARN": 1}


def _sort_key(f: Finding) -> tuple[int, float, str, str]:
    return (_SEVERITY_ORDER[f.severity], f.t if f.t is not None else -1.0, f.id, f.element or "")


def lint_with(plan: EditPlan, lc: LintContext) -> list[Finding]:
    """Run every rule against an already-loaded context (useful in tests)."""
    findings: list[Finding] = []
    for rule in RULES:
        findings.extend(rule(plan, lc))
    return sorted(findings, key=_sort_key)


def lint_plan(plan: EditPlan, ctx: ProjectContext) -> list[Finding]:
    return lint_with(plan, LintContext.from_project(ctx, plan))


def has_errors(findings: Sequence[Finding]) -> bool:
    return any(f.severity == "ERROR" for f in findings)


def schema_findings(exc: ValidationError) -> list[Finding]:
    out: list[Finding] = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err.get("loc", ()))
        msg = str(err.get("msg", "valor inválido")).removeprefix("Value error, ")
        out.append(finding("SCHEMA", "ERROR", f"{loc or 'plan'}: {msg}", element=loc or None))
    return out


def lint_data(data: Any, ctx: ProjectContext) -> tuple[EditPlan | None, list[Finding]]:
    """Validate raw plan data (SCHEMA) and, when valid, run every policy rule."""
    if not isinstance(data, dict):
        return None, [finding("SCHEMA", "ERROR", "El plan debe ser un mapa YAML/JSON.")]
    try:
        plan = EditPlan.model_validate(data)
    except ValidationError as exc:
        return None, schema_findings(exc)
    return plan, lint_plan(plan, ctx)


def lint_file(path: Path, ctx: ProjectContext) -> tuple[EditPlan | None, list[Finding]]:
    p = Path(path)
    if not p.exists():
        return None, [finding("SCHEMA", "ERROR", f"No existe el plan {p}.")]
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))  # YAML is a superset of JSON
    except yaml.YAMLError as exc:
        return None, [finding("SCHEMA", "ERROR", f"El plan no es YAML válido: {exc}")]
    return lint_data(data, ctx)
