"""transcribe: fixture backend, flagged words (P23), revision file, cache, errors."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from editoria.cli import app
from editoria.ingest import IngestError, init_project, transcribe_project
from editoria.ingest import transcribe as tr_mod
from editoria.ingest.transcribe import (
    FLAG_PROB_THRESHOLD,
    build_segments,
    default_prompt,
    flag_uncertain,
    render_revision,
)
from editoria.schemas import Transcript, Word, read_model
from editoria.util.project import ProjectContext

runner = CliRunner()


def _word(text: str, prob: float, start: float = 0.0) -> Word:
    return Word(text=text, start=start, end=start + 0.3, prob=prob)


# ---- P23 ------------------------------------------------------------------------------------
def test_p23_low_probability_words_are_flagged_and_text_untouched() -> None:
    words = [_word("hola", 0.95), _word("repetitivas", 0.45), _word("equipo", 0.59)]
    out = flag_uncertain(words)
    assert [w.flagged for w in out] == [False, True, True]
    assert [w.text for w in out] == ["hola", "repetitivas", "equipo"]


def test_p23_threshold_boundary_is_not_flagged() -> None:
    assert FLAG_PROB_THRESHOLD == 0.6
    out = flag_uncertain([_word("justo", 0.6), _word("seguro", 0.99), _word("dudo", 0.5999)])
    assert [w.flagged for w in out] == [False, False, True]


def test_p23_flags_are_recomputed_even_if_the_source_says_otherwise() -> None:
    stale = Word(text="x", start=0, end=1, prob=0.2, flagged=False)
    assert flag_uncertain([stale])[0].flagged is True
    fresh = Word(text="y", start=0, end=1, prob=0.9, flagged=True)
    assert flag_uncertain([fresh])[0].flagged is False


# ---- fixture backend --------------------------------------------------------------------------
def test_transcribe_fixture_backend_writes_transcript_and_revision(
    ingested: ProjectContext,
) -> None:
    tr = transcribe_project(ingested, backend="fixture")
    assert tr.language == "es"
    assert len(tr.words) == 27
    flagged = [w.text for w in tr.words if w.flagged]
    assert flagged == ["repetitivas"]
    assert len(tr.audio_sha256) == 64

    on_disk = ingested.load_transcript()
    assert on_disk == tr

    md = ingested.analysis("transcript_revision.md").read_text(encoding="utf-8")
    assert "[[repetitivas]]" in md
    assert "00:00.30" in md and "00:02.60" in md  # times
    assert "| 00:03.50 | repetitivas | 0.45 |" in md or "repetitivas | 0.45" in md
    assert "[[automatizar]]" not in md


def test_transcribe_fixture_backend_respects_override_env(
    ingested: ProjectContext, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    custom = Transcript(
        model="custom", words=[_word("hola", 0.9), _word("mundo", 0.3, 0.4)], segments=[]
    )
    path = tmp_path / "mi transcript ñ.json"
    path.write_text(custom.model_dump_json(), encoding="utf-8")
    monkeypatch.setenv("EDITORIA_TRANSCRIPT_FIXTURE", str(path))
    tr = transcribe_project(ingested, backend="fixture")
    assert [w.text for w in tr.words] == ["hola", "mundo"]
    assert [w.flagged for w in tr.words] == [False, True]
    assert tr.model == "custom"


def test_transcribe_missing_fixture_file_is_a_spanish_error(
    ingested: ProjectContext, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EDITORIA_TRANSCRIPT_FIXTURE", str(tmp_path / "no existe.json"))
    with pytest.raises(IngestError, match="No se encuentra el transcript de fixture"):
        transcribe_project(ingested, backend="fixture")


def test_transcribe_unknown_backend(ingested: ProjectContext) -> None:
    with pytest.raises(IngestError, match="Backend desconocido"):
        transcribe_project(ingested, backend="nube")


def test_transcribe_video_without_audio(fixtures_dir: Path, projects_dir: Path) -> None:
    ctx = init_project(fixtures_dir / "sin_audio.mp4", "mudo", "master-solution")
    with pytest.raises(IngestError, match="no tiene pista de audio"):
        transcribe_project(ctx, backend="fixture")


def test_audio_hash_is_stable_between_runs(ingested: ProjectContext) -> None:
    first = transcribe_project(ingested, backend="fixture").audio_sha256
    second = transcribe_project(ingested, backend="fixture").audio_sha256
    assert first == second


# ---- whisper backend (mocked: the real model is never run in tests) ----------------------------
def test_whisper_backend_uses_glossary_prompt_and_cache(
    ingested: ProjectContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, str, str]] = []

    def fake(
        wav: Path, model: str, prompt: str, device: str, compute: str
    ) -> tuple[list[Word], list[tuple[int, int]]]:
        calls.append((model, prompt, compute))
        return [_word("Hola", 0.9), _word("IA", 0.4, 0.4), _word("hoy", 0.8, 0.8)], [(0, 1), (2, 2)]

    monkeypatch.setattr(tr_mod, "_whisper_words", fake)
    tr = transcribe_project(ingested, model="small", backend="whisper")
    assert calls and calls[0][0] == "small"
    assert "Master Solution" in calls[0][1] and calls[0][1].startswith("Glosario:")
    assert calls[0][2] == "int8"
    assert [w.flagged for w in tr.words] == [False, True, False]
    assert [(s.first_word, s.last_word) for s in tr.segments] == [(0, 1), (2, 2)]
    assert tr.model == "small"
    cache_files = list((ingested.analysis_dir / ".cache").glob("whisper_*.json"))
    assert len(cache_files) == 1

    again = transcribe_project(ingested, model="small", backend="whisper")
    assert len(calls) == 1, "el audio ya transcrito sale de la caché"
    assert again.words == tr.words

    transcribe_project(ingested, model="small", backend="whisper", force=True)
    assert len(calls) == 2
    transcribe_project(ingested, model="large-v3-turbo", backend="whisper")
    assert len(calls) == 3, "otro modelo = otra clave de caché"


# ---- helpers ----------------------------------------------------------------------------------
def test_default_prompt_and_segments() -> None:
    assert default_prompt([]) == ""
    assert default_prompt(["IA", "CRM"]) == "Glosario: IA, CRM."
    words = [_word("a", 0.9), _word("b", 0.9, 0.5), _word("c", 0.9, 1.0)]
    segs = build_segments(words, [(0, 1), (2, 2), (5, 4)])
    assert [(s.text, s.first_word, s.last_word) for s in segs] == [("a b", 0, 1), ("c", 2, 2)]


def test_revision_without_flags_says_so() -> None:
    tr = Transcript(model="x", words=[_word("hola", 0.9)])
    md = render_revision(tr)
    assert "Ninguna" in md and "[[hola]]" not in md


# ---- CLI --------------------------------------------------------------------------------------
def test_cli_transcribe_fixture(ingested: ProjectContext) -> None:
    res = runner.invoke(app, ["transcribe", "demo", "--backend", "fixture"])
    assert res.exit_code == 0, res.output
    assert "27 palabras" in res.output and "1 dudosa" in res.output
    data = json.loads(ingested.analysis("transcript.json").read_text(encoding="utf-8"))
    assert data["words"][0]["text"] == "Hoy"
    assert read_model(ingested.analysis("transcript.json"), Transcript).words[3].flagged is False


def test_cli_transcribe_without_audio_fails_in_spanish(
    fixtures_dir: Path, projects_dir: Path
) -> None:
    init_project(fixtures_dir / "sin_audio.mp4", "mudo", "master-solution")
    res = runner.invoke(app, ["transcribe", "mudo", "--backend", "fixture"])
    assert res.exit_code == 1
    assert "no tiene pista de audio" in " ".join(res.output.split())
