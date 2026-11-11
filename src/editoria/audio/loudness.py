"""Loudness measurement: integrated LUFS, loudness range, true peak and clipping."""

from __future__ import annotations

import json
import math
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from editoria.audio.wavio import decode_native, require_audio
from editoria.util import ffmpeg

CLIP_THRESHOLD = 0.99995  # |x| at or above this is full scale (int16 max is 0.99997)
_JSON_RE = re.compile(r"\{[^{}]*\}", re.DOTALL)


@dataclass(frozen=True)
class Loudness:
    """Result of :func:`measure_loudness` (levels in dB, loudness in LUFS)."""

    integrated_lufs: float
    true_peak_db: float  # dBTP, 4x oversampled
    lra: float
    sample_peak_db: float
    clipped_samples: int
    duration_s: float


def to_db(value: float) -> float:
    return 20.0 * math.log10(value) if value > 0 else float("-inf")


def true_peak_db(samples: np.ndarray, oversample: int = 4) -> float:
    """Inter-sample peak in dBFS via FFT (band-limited) interpolation, over all channels."""
    peak = 0.0
    pad = 2048
    for ch in range(samples.shape[1]):
        x = np.concatenate([np.zeros(pad), samples[:, ch].astype(np.float64), np.zeros(pad)])
        n = len(x)
        spec = np.fft.rfft(x)
        up = np.fft.irfft(spec, n * oversample) * oversample
        peak = max(peak, float(np.abs(up).max()), float(np.abs(x).max()))
    return to_db(peak)


def parse_loudnorm_json(stderr: str) -> dict[str, Any]:
    """Last JSON block printed by ``loudnorm=print_format=json``."""
    blocks = _JSON_RE.findall(stderr)
    if not blocks:
        raise RuntimeError("loudnorm no devolvió mediciones.")
    result: dict[str, Any] = json.loads(blocks[-1])
    return result


def _f(value: Any) -> float:
    text = str(value).strip().lower()
    if text in {"-inf", "-infinity"}:
        return float("-inf")
    if text in {"inf", "infinity"}:
        return float("inf")
    return float(text)


def loudnorm_measure(
    graph_prefix: str, inputs: list[str | Path], *, target_i: float, target_tp: float
) -> dict[str, float]:
    """First loudnorm pass over a filtergraph that ends in the label ``[pre]``."""
    flt = f"{graph_prefix};[pre]loudnorm=I={target_i}:TP={target_tp}:LRA=50:print_format=json[out]"
    proc = ffmpeg.run([*inputs, "-filter_complex", flt, "-map", "[out]", "-f", "null", "-"])
    raw = parse_loudnorm_json(proc.stderr)
    return {
        "input_i": _f(raw["input_i"]),
        "input_tp": _f(raw["input_tp"]),
        "input_lra": _f(raw["input_lra"]),
        "input_thresh": _f(raw["input_thresh"]),
        "target_offset": _f(raw["target_offset"]),
    }


def measure_loudness(path: Path | str) -> Loudness:
    """Integrated loudness (BS.1770 via loudnorm), LRA, true peak and clipped samples.

    Works on WAV or any media with an audio stream (e.g. the final MP4).
    """
    require_audio(path, "El archivo")
    proc = ffmpeg.run(
        [
            "-nostats",
            "-i",
            str(path),
            "-vn",
            "-map",
            "0:a:0",
            "-af",
            "loudnorm=I=-14:TP=-1:LRA=50:print_format=json",
            "-f",
            "null",
            "-",
        ]
    )
    raw = parse_loudnorm_json(proc.stderr)
    samples = decode_native(path)
    peak = float(np.abs(samples).max()) if samples.size else 0.0
    clipped = int((np.abs(samples) >= CLIP_THRESHOLD).sum())
    return Loudness(
        integrated_lufs=_f(raw["input_i"]),
        true_peak_db=round(true_peak_db(samples), 2) if samples.size else float("-inf"),
        lra=_f(raw["input_lra"]),
        sample_peak_db=round(to_db(peak), 2),
        clipped_samples=clipped,
        duration_s=len(samples) / 48_000.0,
    )


def tmp_dir() -> tempfile.TemporaryDirectory[str]:
    return tempfile.TemporaryDirectory(prefix="editoria_audio_")
