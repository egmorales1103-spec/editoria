"""qc module: automatic quality control (A5)."""

from editoria.qc.analysis import correlate_voice
from editoria.qc.control import QUESTIONS, DefaultQualityControl, summarize
from editoria.qc.report import QC_JSON, QC_MD, render_markdown, write_report

__all__ = [
    "QC_JSON",
    "QC_MD",
    "QUESTIONS",
    "DefaultQualityControl",
    "correlate_voice",
    "render_markdown",
    "summarize",
    "write_report",
]
