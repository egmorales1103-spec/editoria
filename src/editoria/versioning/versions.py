"""``version new``: create the next immutable version from a version that has parsed feedback."""

from __future__ import annotations

from editoria.ingest.errors import IngestError
from editoria.schemas import Feedback, read_model, write_model
from editoria.util.project import FEEDBACK_FILE, PLAN_FILE, ProjectContext


def new_version(ctx: ProjectContext, from_version: str) -> str:
    """Copy ``from_version``'s plan to the next version and return its name (P20).

    Requires ``feedback.json`` in the source version; never overwrites an existing version.
    """
    try:
        src = ctx.version_dir(from_version)
    except ValueError as exc:
        raise IngestError(str(exc)) from exc
    if not src.is_dir():
        raise IngestError(f"No existe la versión {from_version} del proyecto '{ctx.slug}'.")
    plan_path = src / PLAN_FILE
    if not plan_path.exists():
        raise IngestError(f"{from_version} no tiene plan.yaml: no hay nada que copiar.")
    feedback_path = src / FEEDBACK_FILE
    if not feedback_path.exists():
        raise IngestError(
            f"Falta el feedback de {from_version}: no se crea una versión nueva sin feedback "
            f"parseado. Ejecutá 'editoria feedback parse {ctx.slug} <Feedback.md> "
            f"--version {from_version}'."
        )
    feedback = read_model(feedback_path, Feedback)
    if feedback.version != from_version:
        raise IngestError(
            f"El feedback de {from_version} corresponde a {feedback.version}. "
            "Volvé a ejecutar 'feedback parse' con la versión correcta."
        )

    new = f"V{int(from_version[1:]) + 1}"
    target = ctx.version_dir(new)
    if target.exists():
        raise IngestError(f"Ya existe {new}. Las versiones no se sobrescriben.")

    plan = ctx.load_plan(from_version).model_copy(update={"version": new})
    target.mkdir(parents=True, exist_ok=False)
    try:
        write_model(target / PLAN_FILE, plan)
    except BaseException:
        (target / PLAN_FILE).unlink(missing_ok=True)
        target.rmdir()
        raise
    return new
