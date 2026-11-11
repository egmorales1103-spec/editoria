"""measure_loudness and check_voice (cross-correlation) on synthetic media."""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pytest

from editoria.audio import check_voice, measure_loudness
from editoria.audio.voice import cross_correlate
from editoria.audio.wavio import NoAudioError
from editoria.util import ffmpeg

FRAME_MS = 1000 / 30


def test_measure_loudness_matches_ebur128(spaced_video: Path) -> None:
    m = measure_loudness(spaced_video)
    proc = ffmpeg.run(
        [
            "-nostats",
            "-i",
            str(spaced_video),
            "-vn",
            "-af",
            "ebur128=peak=true:framelog=quiet",
            "-f",
            "null",
            "-",
        ]
    )
    found = re.search(r"I:\s+(-?[\d.]+) LUFS", proc.stderr)
    assert found is not None
    tp = float(re.findall(r"Peak:\s+(-?[\d.]+) dBFS", proc.stderr)[-1])
    assert m.integrated_lufs == pytest.approx(float(found.group(1)), abs=0.2)
    assert m.true_peak_db == pytest.approx(tp, abs=0.15)
    assert m.clipped_samples == 0
    assert m.duration_s == pytest.approx(12.0, abs=0.05)


def test_clipping_is_counted(tmp_path: Path, spaced_video: Path) -> None:
    hot = tmp_path / "caliente ñ.wav"
    ffmpeg.run(
        ["-i", str(spaced_video), "-vn", "-af", "volume=25dB", "-c:a", "pcm_s16le", str(hot)]
    )
    m = measure_loudness(hot)
    assert m.clipped_samples > 100
    assert m.true_peak_db >= -0.1


def test_measure_requires_audio(fixtures_dir: Path) -> None:
    with pytest.raises(NoAudioError, match="no tiene pista de audio"):
        measure_loudness(fixtures_dir / "sin_audio.mp4")


def test_voice_identity_is_in_sync(base_video: Path, spaced_video: Path) -> None:
    res = check_voice(base_video, spaced_video)
    assert abs(res.offset_ms) < 1.0
    assert res.similarity > 0.99


def test_voice_after_aac_encode_stays_within_one_frame(base_video: Path, audio_work: Path) -> None:
    out = audio_work / "re codificado ñ.mp4"
    ffmpeg.run(["-i", str(base_video), "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", str(out)])
    res = check_voice(base_video, out)
    assert abs(res.offset_ms) <= FRAME_MS
    assert res.similarity > 0.95


@pytest.mark.parametrize("mode", ["adelay", "itsoffset"])
def test_voice_detects_artificial_200ms_delay(
    base_video: Path, audio_work: Path, mode: str
) -> None:
    out = audio_work / f"retrasado {mode} ñ.mp4"
    if mode == "adelay":
        ffmpeg.run(["-i", str(base_video), "-af", "adelay=200:all=1", "-c:v", "copy", str(out)])
    else:
        ffmpeg.run(
            [
                "-i",
                str(base_video),
                "-itsoffset",
                "0.2",
                "-i",
                str(base_video),
                "-map",
                "0:v",
                "-map",
                "1:a",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                str(out),
            ]
        )
    res = check_voice(base_video, out)
    assert res.offset_ms == pytest.approx(200.0, abs=FRAME_MS)
    assert res.similarity > 0.9


def test_voice_detects_advanced_audio(base_video: Path, audio_work: Path) -> None:
    out = audio_work / "adelantado ñ.wav"
    ffmpeg.run(
        [
            "-i",
            str(base_video),
            "-vn",
            "-af",
            "atrim=start=0.2,asetpts=PTS-STARTPTS",
            "-c:a",
            "pcm_s16le",
            str(out),
        ]
    )
    res = check_voice(base_video, out)
    assert res.offset_ms == pytest.approx(-200.0, abs=FRAME_MS)


def test_voice_similarity_low_for_other_audio(base_video: Path, noise_base: Path) -> None:
    assert check_voice(base_video, noise_base).similarity < 0.3


def test_voice_requires_audio(base_video: Path, fixtures_dir: Path) -> None:
    with pytest.raises(NoAudioError):
        check_voice(base_video, fixtures_dir / "sin_audio.mp4")


def test_cross_correlate_subsample_precision() -> None:
    rng = np.random.default_rng(1)
    sr = 16000
    a = rng.standard_normal(sr * 3)
    b = np.concatenate([np.zeros(1600), a])[: len(a)]  # +100 ms
    lag, sim = cross_correlate(a, b, sr)
    assert lag == pytest.approx(0.1, abs=1e-4)
    assert sim > 0.9
