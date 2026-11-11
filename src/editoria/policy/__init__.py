"""Policy linter (A2): executable checks for the rules of section 6 (P04…P17, BRAND)."""

from editoria.policy.context import LintContext
from editoria.policy.linter import has_errors, lint_data, lint_file, lint_plan, lint_with
from editoria.policy.report import print_findings, summary

__all__ = [
    "LintContext",
    "has_errors",
    "lint_data",
    "lint_file",
    "lint_plan",
    "lint_with",
    "print_findings",
    "summary",
]
