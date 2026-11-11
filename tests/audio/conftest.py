"""Fixtures for the audio tests: synthetic media only, no network."""

from __future__ import annotations

from pathlib import Path

import pytest

from editoria.util import ffmpeg


@pytest.fixture(scope="session")
def audio_work(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Work folder with a space and accents, on purpose."""
    return tmp_path_factory.mktemp("audio carpeta ñ")


@pytest.fixture(scope="session")
def noise_base(audio_work: Path) -> Path:
    """27 s mono video whose audio is faint noise: SFX dominate the mix (onset tests)."""
    out = audio_work / "base ruido ñ.mp4"
    ffmpeg.run(
        [
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=320x240:r=30:d=27",
            "-f",
            "lavfi",
            "-i",
            "anoisesrc=a=0.003:d=27:r=48000:seed=7",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "pcm_s16le",
            "-ac",
            "1",
            str(out),
        ]
    )
    return out


@pytest.fixture(scope="session")
def stereo_base(audio_work: Path, base_video: Path) -> Path:
    out = audio_work / "base estéreo.mp4"
    ffmpeg.run(["-i", str(base_video), "-c:v", "copy", "-ac", "2", "-c:a", "aac", str(out)])
    return out


@pytest.fixture(scope="session")
def music_wav(audio_work: Path) -> Path:
    """4 s of pink noise: shorter than the base so looping is exercised."""
    out = audio_work / "música ñ.wav"
    ffmpeg.run(
        [
            "-f",
            "lavfi",
            "-i",
            "anoisesrc=color=pink:a=0.3:d=4:r=44100:seed=3",
            "-c:a",
            "pcm_s16le",
            str(out),
        ]
    )
    return out
