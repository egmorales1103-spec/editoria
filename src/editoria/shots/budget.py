"""Credit budget guard (P09): no authorised limit -> nothing paid may be submitted.

``logs/creditos.jsonl`` is the ledger: one JSON object per line with ``amount`` and ``detail``.
``proyecto.yaml`` holds the authorised ``budget.limit``; ``budget.spent`` there is treated as
credits already spent before the ledger existed, and the larger of the two figures is used so the
guard errs on the side of caution.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass

from editoria.shots.errors import BudgetError
from editoria.util.log import append_jsonl, read_jsonl
from editoria.util.project import ProjectContext

_EPS = 1e-9


@dataclass(frozen=True)
class BudgetStatus:
    unit: str
    limit: float | None
    spent: float

    @property
    def remaining(self) -> float | None:
        return None if self.limit is None else max(self.limit - self.spent, 0.0)


def ledger_total(ctx: ProjectContext) -> float:
    """Sum of ``amount`` in logs/creditos.jsonl."""
    try:
        rows = read_jsonl(ctx.credits_log)
    except json.JSONDecodeError as exc:
        raise BudgetError(
            f"El registro de créditos {ctx.credits_log} está dañado ({exc}). "
            "Corregilo antes de gastar créditos."
        ) from exc
    total = 0.0
    for row in rows:
        amount = row.get("amount")
        if isinstance(amount, bool) or not isinstance(amount, int | float):
            raise BudgetError(
                f"Una línea de {ctx.credits_log} no tiene un 'amount' numérico. "
                "Corregila antes de gastar créditos."
            )
        total += float(amount)
    return total


def budget_status(ctx: ProjectContext) -> BudgetStatus:
    budget = ctx.load_config().budget
    return BudgetStatus(
        unit=budget.unit, limit=budget.limit, spent=max(ledger_total(ctx), budget.spent)
    )


def ensure_budget(ctx: ProjectContext, cost: float) -> None:
    """Raise :class:`BudgetError` unless ``cost`` fits in the authorised limit.

    Without a limit in ``proyecto.yaml`` (``budget.limit``) every cost is blocked, even 0.
    """
    status = budget_status(ctx)
    if status.limit is None:
        raise BudgetError(
            "No hay un límite de créditos autorizado en proyecto.yaml (budget.limit). "
            "Sin límite no se puede enviar nada que consuma créditos. "
            "Pedile ese único dato a quien administra el proyecto y registralo antes de continuar."
        )
    if not math.isfinite(cost) or cost < 0:
        raise BudgetError(f"El costo a verificar no es válido: {cost}.")
    remaining = status.remaining or 0.0
    if cost > remaining + _EPS:
        raise BudgetError(
            f"El costo ({cost:g} {status.unit}) supera lo que queda del límite autorizado: "
            f"límite {status.limit:g}, gastado {status.spent:g}, restante {remaining:g} "
            f"{status.unit}. No se envía."
        )


def record_credit(ctx: ProjectContext, amount: float, detail: str) -> None:
    """Append credits that were really consumed (as shown by the tool) to the ledger.

    This only records; it never blocks, because the credits are already spent. Use
    :func:`ensure_budget` BEFORE spending.
    """
    if not math.isfinite(amount) or amount < 0:
        raise BudgetError(f"El monto de créditos no es válido: {amount}.")
    unit = ctx.load_config().budget.unit
    append_jsonl(ctx.credits_log, {"amount": float(amount), "unit": unit, "detail": detail})
