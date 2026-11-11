"""``transcribe``: word-level transcript (faster-whisper) with uncertain words flagged (P23).

Backends:
  * ``whisper``: faster-whisper, Spanish, ``word_timestamps``, brand glossary as initial prompt.
    Needs the ``transcribe`` extra and the model in the local cache (or a network download).
  * ``fixture``: copies ``tests/.fixtures/transcript_fixture.json`` (or the file named by
    ``EDITORIA_TRANSCRIPT_FIXTURE``). Used by tests and offline runs; never touches the network.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

from editoria.ingest.errors import IngestError
from editoria.schemas import Transcript, TranscriptSegment, Word, read_model, write_model
from editoria.util import ffmpeg, resources
from editoria.util.files import fmt_ts, sha256_file
from editoria.util.project import TRANSCRIPT_FILE, TRANSCRIPT_REVIEW_FILE, ProjectContext

FLAG_PROB_THRESHOLD = 0.6  # words with prob < threshold are flagged for human review
DEFAULT_MODEL = "large-v3-turbo"
LANGUAGE = "es"
CACHE_DIR = ".cache"
FIXTURE_ENV = "EDITORIA_TRANSCRIPT_FIXTURE"


# ---------------------------------------------------------------------------------------
def flag_uncertain(words: list[Word], threshold: float = FLAG_PROB_THRESHOLD) -> list[Word]:
    """Mark words whose probability is below ``threshold``. Text is never changed (P23)."""
    return [w.model_copy(update={"flagged": w.prob < threshold}) for w in words]


def build_segments(words: list[Word], bounds: list[tuple[int, int]]) -> list[TranscriptSegment]:
    """TranscriptSegments from inclusive (first_word, last_word) index pairs."""
    out: list[TranscriptSegment] = []
    for first, last in bounds:
        chunk = words[first : last + 1]
        if not chunk:
            continue
        out.append(
            TranscriptSegment(
                start=chunk[0].start,
                end=chunk[-1].end,
                text=" ".join(w.text for w in chunk),
                first_word=first,
                last_word=last,
            )
        )
    return out


def default_prompt(glossary: list[str]) -> str:
    """initial_prompt for whisper: nudges the spelling of the brand terms."""
    if not glossary:
        return ""
    return "Glosario: " + ", ".join(glossary) + "."


# ---------------------------------------------------------------------------------------
def extract_audio(video: Path, out_wav: Path) -> None:
    """16 kHz mono PCM of the base audio. Raises IngestError when there is no audio track."""
    info = ffmpeg.probe(video)
    if not any(s.get("codec_type") == "audio" for s in info.get("streams", [])):
        raise IngestError(
            "El video no tiene pista de audio: no hay nada que transcribir. "
            "Exportá el VIDEO_BASE con su audio original."
        )
    ffmpeg.run(
        ["-i", str(video), "-vn", "-map", "0:a:0", "-ac", "1", "-ar", "16000",
         "-c:a", "pcm_s16le", str(out_wav)]
    )  # fmt: skip


def _cache_key(audio_hash: str, model: str, prompt: str) -> str:
    raw = "\n".join([audio_hash, model, LANGUAGE, prompt])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _whisper_words(  # pragma: no cover - needs a real model (slow, not run in tests)
    wav: Path, model_name: str, prompt: str, device: str, compute_type: str
) -> tuple[list[Word], list[tuple[int, int]]]:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise IngestError(
            "Falta faster-whisper. Instalalo con: uv sync --extra transcribe "
            "(o usá --backend fixture para pruebas sin modelo)."
        ) from exc
    model = WhisperModel(model_name, device=device, compute_type=compute_type)
    segs, _info = model.transcribe(
        str(wav),
        language=LANGUAGE,
        word_timestamps=True,
        initial_prompt=prompt or None,
        vad_filter=True,
        condition_on_previous_text=False,
    )
    words: list[Word] = []
    bounds: list[tuple[int, int]] = []
    for seg in segs:
        first = len(words)
        for w in seg.words or []:
            text = w.word.strip()
            if not text:
                continue
            words.append(
                Word(
                    text=text,
                    start=round(float(w.start), 3),
                    end=round(float(w.end), 3),
                    prob=min(max(float(w.probability), 0.0), 1.0),
                )
            )
        if len(words) > first:
            bounds.append((first, len(words) - 1))
    return words, bounds


def _fixture_path() -> Path:
    env = os.environ.get(FIXTURE_ENV)
    default = resources.repo_root() / "tests" / ".fixtures" / "transcript_fixture.json"
    path = Path(env) if env else default
    if not path.exists():
        raise IngestError(
            f"No se encuentra el transcript de fixture ({path}). "
            "Generá los fixtures con: uv run python scripts/make_fixtures.py"
        )
    return path


def transcribe_project(
    ctx: ProjectContext,
    model: str = DEFAULT_MODEL,
    backend: str = "whisper",
    *,
    device: str = "cpu",
    compute_type: str = "int8",
    force: bool = False,
) -> Transcript:
    """Transcribe the project's original; writes transcript.json and transcript_revision.md.

    The raw whisper result is cached by audio hash (+ model + prompt) in
    ``01_analisis/.cache``; ``force`` ignores the cache.
    """
    if backend not in {"whisper", "fixture"}:
        raise IngestError(f"Backend desconocido '{backend}': usá 'whisper' o 'fixture'.")
    video = ctx.original_video()

    with tempfile.TemporaryDirectory(prefix="editoria-audio-") as tmp:
        wav = Path(tmp) / "audio.wav"
        with ffmpeg.command_log(ctx.commands_log):
            extract_audio(video, wav)
        audio_hash = sha256_file(wav)

        if backend == "fixture":
            fixture = read_model(_fixture_path(), Transcript)
            words, segments, model_used = fixture.words, fixture.segments, fixture.model
        else:
            try:
                glossary = ctx.load_brand().glossary
            except FileNotFoundError:
                glossary = []
            prompt = default_prompt(glossary)
            key = _cache_key(audio_hash, model, prompt)
            cache = ctx.analysis_dir / CACHE_DIR / f"whisper_{key}.json"
            if cache.exists() and not force:
                cached = read_model(cache, Transcript)
                words, segments = cached.words, cached.segments
            else:
                words, bounds = _whisper_words(wav, model, prompt, device, compute_type)
                segments = build_segments(words, bounds)
                write_model(
                    cache,
                    Transcript(
                        language=LANGUAGE,
                        model=model,
                        words=words,
                        segments=segments,
                        audio_sha256=audio_hash,
                    ),
                )
            model_used = model

    transcript = Transcript(
        language=LANGUAGE,
        model=model_used,
        words=flag_uncertain(words),
        segments=segments,
        audio_sha256=audio_hash,
    )
    write_model(ctx.analysis(TRANSCRIPT_FILE), transcript)
    ctx.analysis(TRANSCRIPT_REVIEW_FILE).write_text(
        render_revision(transcript), encoding="utf-8", newline="\n"
    )
    return transcript


# ---------------------------------------------------------------------------------------
def render_revision(tr: Transcript) -> str:
    """Markdown for the human review: text by segment with times; doubtful words highlighted."""
    flagged = [w for w in tr.words if w.flagged]
    lines = [
        "# Revisión de la transcripción",
        "",
        f"Modelo: `{tr.model}` · idioma: `{tr.language}` · palabras: {len(tr.words)} · "
        f"dudosas: {len(flagged)}",
        "",
        "Las palabras entre `[[ ]]` tienen baja confianza (menos de "
        f"{FLAG_PROB_THRESHOLD:.0%}): escuchalas en el video antes de aprobar los subtítulos. "
        "El texto no se corrigió automáticamente.",
        "",
        "## Texto por tiempo",
        "",
    ]
    segments = tr.segments
    if not segments and tr.words:
        segments = build_segments(tr.words, [(0, len(tr.words) - 1)])
    for seg in segments:
        text = " ".join(
            f"[[{w.text}]]" if w.flagged else w.text
            for w in tr.words[seg.first_word : seg.last_word + 1]
        )
        lines.append(f"- `{fmt_ts(seg.start)}–{fmt_ts(seg.end)}` {text}")
    lines += ["", "## Palabras dudosas", ""]
    if flagged:
        lines += ["| Tiempo | Palabra | Confianza |", "|---|---|---|"]
        lines += [f"| {fmt_ts(w.start)} | {w.text} | {w.prob:.2f} |" for w in flagged]
    else:
        lines.append("Ninguna: todas las palabras superan el umbral de confianza.")
    lines.append("")
    return "\n".join(lines)
