"""Policy linter (A2): executable checks for the rules of section 6 (P04…P17, BRAND)."""

from editoria.policy.context import LintContext
from editoria.policy.immutable import (
    ImmutableTargetError,
    delivered_version_of,
    ensure_not_delivered,
    ensure_writable_path,
)
from editoria.policy.linter import has_errors, lint_data, lint_file, lint_plan, lint_with
from editoria.policy.report import print_findings, summary

__all__ = [
    "ImmutableTargetError",
    "LintContext",
    "delivered_version_of",
    "ensure_not_delivered",
    "ensure_writable_path",
    "has_errors",
    "lint_data",
    "lint_file",
    "lint_plan",
    "lint_with",
    "print_findings",
    "summary",
]
