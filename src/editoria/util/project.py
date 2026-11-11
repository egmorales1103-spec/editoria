"""ProjectContext: every path of a per-video workspace (proyectos/<slug>/)."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from editoria.schemas import (
    BrandProfile,
    CutList,
    EditPlan,
    FaceTrack,
    ProbeResult,
    ProjectConfig,
    SegmentList,
    SilenceList,
    StylePreset,
    Transcript,
    read_model,
    write_model,
)
from editoria.util import resources

ORIGINAL_DIR = "00_original"
ANALYSIS_DIR = "01_analisis"
SHOTS_DIR = "02_tomas"
PROPOSALS_DIR = "03_propuestas"
VERSIONS_DIR = "04_versiones"
LOGS_DIR = "logs"

# 01_analisis/
PROBE_FILE = "probe.json"
TRANSCRIPT_FILE = "transcript.json"
TRANSCRIPT_REVIEW_FILE = "transcript_revision.md"
SILENCES_FILE = "silencios.json"
CUTS_FILE = "cortes.json"
FACE_FILE = "rostro.json"
SEGMENTS_FILE = "segmentos.json"
EDIT_MAP_FILE = "mapa_edicion.csv"

# 04_versiones/Vn/
PLAN_FILE = "plan.yaml"
VIDEO_FILE = "video.mp4"
FEEDBACK_FILE = "feedback.json"
DELIVERED_MARKER = ".entregado"

_VERSION_RE = re.compile(r"^V(\d+)$")


class ProjectNotFound(FileNotFoundError):
    pass


_projects_override: Path | None = None


def set_projects_dir(path: Path | None) -> None:
    global _projects_override
    _projects_override = Path(path) if path else None


def projects_dir() -> Path:
    """`--proyectos` > EDITORIA_PROJECTS > ./proyectos."""
    if _projects_override is not None:
        return _projects_override
    env = os.environ.get("EDITORIA_PROJECTS")
    return Path(env) if env else Path.cwd() / "proyectos"


@dataclass(frozen=True)
class ProjectContext:
    root: Path

    # ---- construction -------------------------------------------------------------------
    @classmethod
    def open(cls, slug: str, base: Path | None = None) -> ProjectContext:
        root = (base or projects_dir()) / slug
        if not (root / "proyecto.yaml").exists():
            raise ProjectNotFound(
                f"No existe el proyecto '{slug}' en {root.parent}. Creálo con 'editoria init'."
            )
        return cls(root)

    @classmethod
    def create(cls, slug: str, base: Path | None = None) -> ProjectContext:
        ctx = cls((base or projects_dir()) / slug)
        for d in ctx.all_dirs():
            d.mkdir(parents=True, exist_ok=True)
        return ctx

    def all_dirs(self) -> list[Path]:
        return [
            self.original_dir,
            self.analysis_dir,
            self.shots_packs_dir,
            self.shots_results_dir,
            self.shots_comparisons_dir,
            self.proposals_dir,
            self.versions_dir,
            self.logs_dir,
        ]

    # ---- folders ------------------------------------------------------------------------
    @property
    def slug(self) -> str:
        return self.root.name

    @property
    def config_path(self) -> Path:
        return self.root / "proyecto.yaml"

    @property
    def original_dir(self) -> Path:
        return self.root / ORIGINAL_DIR

    @property
    def analysis_dir(self) -> Path:
        return self.root / ANALYSIS_DIR

    @property
    def shots_dir(self) -> Path:
        return self.root / SHOTS_DIR

    @property
    def shots_packs_dir(self) -> Path:
        return self.shots_dir / "higgsfield" / "paquetes"

    @property
    def shots_results_dir(self) -> Path:
        return self.shots_dir / "higgsfield" / "resultados"

    @property
    def shots_comparisons_dir(self) -> Path:
        return self.shots_dir / "comparativas"

    @property
    def generations_registry(self) -> Path:
        return self.shots_dir / "registro_generaciones.csv"

    @property
    def proposals_dir(self) -> Path:
        return self.root / PROPOSALS_DIR

    @property
    def versions_dir(self) -> Path:
        return self.root / VERSIONS_DIR

    @property
    def logs_dir(self) -> Path:
        return self.root / LOGS_DIR

    @property
    def commands_log(self) -> Path:
        return self.logs_dir / "comandos.jsonl"

    @property
    def credits_log(self) -> Path:
        return self.logs_dir / "creditos.jsonl"

    def analysis(self, name: str) -> Path:
        return self.analysis_dir / name

    # ---- original -----------------------------------------------------------------------
    def original_video(self) -> Path:
        cands = [
            p
            for p in sorted(self.original_dir.glob("video_base.*"))
            if p.suffix.lower() != ".sha256"
        ]
        if not cands:
            raise FileNotFoundError(
                "Falta el VIDEO_BASE en 00_original/. Ejecutá 'editoria init <video>'."
            )
        return cands[0]

    def original_sha256_path(self) -> Path:
        return self.original_dir / "video_base.sha256"

    # ---- versions -----------------------------------------------------------------------
    def version_dir(self, version: str) -> Path:
        if not _VERSION_RE.match(version):
            raise ValueError(f"Versión inválida '{version}' (se espera V1, V2, ...).")
        return self.versions_dir / version

    def versions(self) -> list[str]:
        if not self.versions_dir.exists():
            return []
        found = [p.name for p in self.versions_dir.iterdir() if _VERSION_RE.match(p.name)]
        return sorted(found, key=lambda v: int(v[1:]))

    def next_version(self) -> str:
        vs = self.versions()
        return f"V{int(vs[-1][1:]) + 1}" if vs else "V1"

    def is_delivered(self, version: str) -> bool:
        return (self.version_dir(version) / DELIVERED_MARKER).exists()

    # ---- loaders ------------------------------------------------------------------------
    def load_config(self) -> ProjectConfig:
        return read_model(self.config_path, ProjectConfig)

    def save_config(self, cfg: ProjectConfig) -> None:
        write_model(self.config_path, cfg)

    def load_probe(self) -> ProbeResult:
        return read_model(self.analysis(PROBE_FILE), ProbeResult)

    def load_transcript(self) -> Transcript:
        return read_model(self.analysis(TRANSCRIPT_FILE), Transcript)

    def load_face(self) -> FaceTrack | None:
        p = self.analysis(FACE_FILE)
        return read_model(p, FaceTrack) if p.exists() else None

    def load_segments(self) -> SegmentList:
        return read_model(self.analysis(SEGMENTS_FILE), SegmentList)

    def load_silences(self) -> SilenceList | None:
        p = self.analysis(SILENCES_FILE)
        return read_model(p, SilenceList) if p.exists() else None

    def load_cuts(self) -> CutList | None:
        p = self.analysis(CUTS_FILE)
        return read_model(p, CutList) if p.exists() else None

    def load_plan(self, version: str) -> EditPlan:
        return read_model(self.version_dir(version) / PLAN_FILE, EditPlan)

    def load_brand(self) -> BrandProfile:
        return resources.load_brand(self.load_config().brand)

    def load_style(self, style_id: str) -> StylePreset:
        return resources.load_style(style_id)
