"""Export JSON Schemas of the public file formats to <repo>/schemas/json/."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from editoria.schemas import (
    AssetManifest,
    BrandProfile,
    EditPlan,
    FaceTrack,
    Feedback,
    ProbeResult,
    ProjectConfig,
    QCReport,
    SegmentList,
    StylePreset,
    Transcript,
)

EXPORTED: dict[str, type[BaseModel]] = {
    "plan": EditPlan,
    "proyecto": ProjectConfig,
    "probe": ProbeResult,
    "transcript": Transcript,
    "segmentos": SegmentList,
    "rostro": FaceTrack,
    "estilo": StylePreset,
    "marca": BrandProfile,
    "qc": QCReport,
    "feedback": Feedback,
    "manifest": AssetManifest,
}


def export_all(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, model in EXPORTED.items():
        p = out_dir / f"{name}.schema.json"
        schema = model.model_json_schema(by_alias=True)
        p.write_text(
            json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
        written.append(p)
    return written


if __name__ == "__main__":  # pragma: no cover
    from editoria.util.resources import repo_root

    for path in export_all(repo_root() / "schemas" / "json"):
        print(path)
