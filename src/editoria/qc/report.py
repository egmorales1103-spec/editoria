"""qc/qc.json + qc/qc.md writers."""

from __future__ import annotations

from pathlib import Path

from editoria.schemas import QC_STATUS_LABEL, QCReport, write_model

QC_JSON = "qc.json"
QC_MD = "qc.md"


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def render_markdown(report: QCReport) -> str:
    lines = [
        f"# Control de calidad — {report.version}",
        "",
        f"**Resumen:** {report.summary}",
        "",
        "| Estado | Chequeo | Pregunta / regla | Detalle |",
        "|---|---|---|---|",
    ]
    order = {"FAIL": 0, "WARN": 1, "HUMAN": 2, "PASS": 3}
    for c in sorted(report.checks, key=lambda c: order[c.status]):
        lines.append(
            f"| **{QC_STATUS_LABEL[c.status]}** | `{c.id}` | {_cell(c.prompt_question)} | "
            f"{_cell(c.detail)} |"
        )
    lines += ["", "## Evidencia", ""]
    for c in report.checks:
        if not c.evidence:
            continue
        lines.append(f"### `{c.id}` — {QC_STATUS_LABEL[c.status]}")
        lines += [f"- {e}" for e in c.evidence]
        lines.append("")
    lines += [
        "---",
        "REVISIÓN HUMANA = no se puede verificar automáticamente; requiere mirar el video.",
        "",
    ]
    return "\n".join(lines)


def write_report(report: QCReport, qc_dir: Path) -> tuple[Path, Path]:
    qc_dir.mkdir(parents=True, exist_ok=True)
    js = write_model(qc_dir / QC_JSON, report)
    md = qc_dir / QC_MD
    md.write_text(render_markdown(report), encoding="utf-8", newline="\n")
    return js, md
