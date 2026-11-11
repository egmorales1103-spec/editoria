"""analyze: silences, cuts, face zone, segments and the edit map for a project."""

from __future__ import annotations

from editoria.analysis.detectors import detect_cuts, detect_silences
from editoria.analysis.face import detect_faces
from editoria.analysis.segments import build_segments, write_edit_map
from editoria.ingest.errors import IngestError
from editoria.ingest.probe import probe_project
from editoria.schemas import SegmentList, read_model, write_model
from editoria.util import ffmpeg
from editoria.util.project import (
    CUTS_FILE,
    EDIT_MAP_FILE,
    FACE_FILE,
    PROBE_FILE,
    SEGMENTS_FILE,
    SILENCES_FILE,
    TRANSCRIPT_FILE,
    ProjectContext,
)


def _director_work(path) -> bool:  # type: ignore[no-untyped-def]
    """True when segmentos.json already holds decisions of the director (role/intent...)."""
    if not path.exists():
        return False
    try:
        current = read_model(path, SegmentList)
    except Exception:
        return False
    return any(s.role or s.intent or s.visual or s.reference or s.method for s in current.segments)


def analyze_project(ctx: ProjectContext, *, force: bool = False) -> SegmentList:
    """Run every analysis and write silencios/cortes/rostro/segmentos/mapa_edicion.

    Needs ``transcript.json``. Refuses to overwrite a ``segmentos.json`` the director already
    filled in (role/intent...) unless ``force`` is True.
    """
    if not ctx.analysis(TRANSCRIPT_FILE).exists():
        raise IngestError(
            f"Falta la transcripción: ejecutá 'editoria transcribe {ctx.slug}' antes de analizar."
        )
    if not force and _director_work(ctx.analysis(SEGMENTS_FILE)):
        raise IngestError(
            "segmentos.json ya tiene decisiones del director (rol/intención). "
            "No se sobrescribe: usá --force si querés regenerarlo."
        )
    transcript = ctx.load_transcript()
    with ffmpeg.command_log(ctx.commands_log):
        probe = probe_project(ctx) if not ctx.analysis(PROBE_FILE).exists() else ctx.load_probe()
        video = ctx.original_video()
        silences = detect_silences(video, probe.duration_s, has_audio=probe.has_audio)
        cuts = detect_cuts(video)
        face = detect_faces(video, probe.display_width, probe.display_height, probe.duration_s)
    segments = build_segments(transcript)
    write_model(ctx.analysis(SILENCES_FILE), silences)
    write_model(ctx.analysis(CUTS_FILE), cuts)
    write_model(ctx.analysis(FACE_FILE), face)
    write_model(ctx.analysis(SEGMENTS_FILE), segments)
    write_edit_map(ctx.analysis(EDIT_MAP_FILE), segments)
    return segments
