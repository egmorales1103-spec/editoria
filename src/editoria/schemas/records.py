"""Records with exact CSV/Markdown layouts taken from the kit templates, assets, QC, feedback."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from editoria.schemas.base import Model, QCStatus, Seconds, Severity, Verdict

# Exact column order of templates/docs/Registro_Generaciones.csv
REGISTRO_COLUMNS: tuple[str, ...] = (
    "id",
    "archivo_origen",
    "entrada",
    "salida",
    "funcion_modelo_real",
    "prompt",
    "ajustes_mostrados",
    "costo_mostrado",
    "archivo_resultado",
    "fondo",
    "identidad",
    "manos",
    "sincronia",
    "veredicto",
    "motivo",
)

# Exact column order of templates/docs/Mapa_Edicion.csv
MAPA_COLUMNS: tuple[str, ...] = (
    "entrada",
    "salida",
    "frase_original",
    "intencion",
    "visual",
    "metodo",
    "referencia",
    "archivo",
    "subtitulo",
    "grafico",
    "sonido",
    "estado",
)


class GenerationRecord(Model):
    """One row of registro_generaciones.csv. Empty strings = not reported by the tool."""

    id: str
    archivo_origen: str = ""
    entrada: str = ""
    salida: str = ""
    funcion_modelo_real: str = ""
    prompt: str = ""
    ajustes_mostrados: str = ""
    costo_mostrado: str = ""
    archivo_resultado: str = ""
    fondo: str = ""
    identidad: str = ""
    manos: str = ""
    sincronia: str = ""
    veredicto: Verdict = "pendiente"
    motivo: str = ""


class EditMapRow(Model):
    """One row of mapa_edicion.csv."""

    entrada: str
    salida: str
    frase_original: str = ""
    intencion: str = ""
    visual: str = ""
    metodo: str = ""
    referencia: str = ""
    archivo: str = ""
    subtitulo: str = ""
    grafico: str = ""
    sonido: str = ""
    estado: str = ""


class AssetEntry(Model):
    id: str
    path: str  # relative to repo root
    kind: Literal["sfx", "font", "emoji", "music"]
    license: str
    license_url: str = ""
    author: str = ""
    source_url: str = ""
    sha256: str = ""
    attribution: str = ""
    suggested_use: str = ""


class AssetManifest(Model):
    assets: list[AssetEntry] = Field(default_factory=list)

    def get(self, asset_id: str) -> AssetEntry | None:
        return next((a for a in self.assets if a.id == asset_id), None)


class QCCheck(Model):
    id: str
    prompt_question: str  # question of §10 of the prompt or rule id it answers
    status: QCStatus
    detail: str = ""
    evidence: list[str] = Field(default_factory=list)


QC_STATUS_LABEL: dict[str, str] = {
    "PASS": "PASS",
    "WARN": "WARN",
    "FAIL": "FAIL",
    "HUMAN": "REVISIÓN HUMANA",
}


class QCReport(Model):
    version: str
    checks: list[QCCheck] = Field(default_factory=list)
    summary: str = ""
    video_sha256: str = ""  # sha256 of the video.mp4 this report checked (deliver compares it)

    def counts(self) -> dict[str, int]:
        out = {k: 0 for k in QC_STATUS_LABEL}
        for c in self.checks:
            out[c.status] += 1
        return out

    @property
    def has_fail(self) -> bool:
        return any(c.status == "FAIL" for c in self.checks)


class FeedbackItem(Model):
    t_in: Seconds
    t_out: Seconds
    element: str = ""
    change: str = ""
    desired: str = ""


class Feedback(Model):
    """Parsed Feedback_V1.md (feedback.json inside the version that received it)."""

    version: str  # version the feedback is about (e.g. V1)
    preferred: str = ""
    keep: str = ""
    change: str = ""
    items: list[FeedbackItem] = Field(default_factory=list)
    quick_review: dict[str, str] = Field(default_factory=dict)


class Finding(Model):
    """Policy-linter finding."""

    id: str  # rule id: P04, P05, ... or SCHEMA
    severity: Severity
    message: str  # Spanish, user facing
    t: Seconds | None = None
    element: str | None = None  # plan element id (v02, g01, sfx[3]...)
