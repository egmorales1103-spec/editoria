"""Errors raised by the shots module. Messages are Spanish and user facing."""

from __future__ import annotations


class ShotError(RuntimeError):
    """A recoverable problem with a shot operation (bad input, missing step, rejected file)."""


class BudgetError(ShotError):
    """No authorised credit limit, or the requested cost would exceed it (P09)."""
