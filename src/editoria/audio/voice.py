"""Voice integrity check: cross-correlation between the base audio and a final render."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from editoria.audio.wavio import audio_stream, decode_mono
from editoria.schemas import VoiceCheck

CHECK_SR = 16_000
MAX_LAG_S = 1.0


def _pow2(n: int) -> int:
    return 1 << (max(n, 2) - 1).bit_length()


def cross_correlate(
    ref: np.ndarray, test: np.ndarray, sr: int, max_lag_s: float = MAX_LAG_S
) -> tuple[float, float]:
    """Return ``(lag_seconds, similarity)``: positive lag = ``test`` is delayed vs ``ref``.

    Similarity is the normalised cross-correlation at the peak, computed over the overlapping
    part only (so a pure delay of an identical signal scores ~1).
    """
    la, lb = len(ref), len(test)
    if la == 0 or lb == 0:
        return 0.0, 0.0
    a = ref.astype(np.float64)
    b = test.astype(np.float64)
    size = _pow2(la + lb)
    corr = np.fft.irfft(np.fft.rfft(b, size) * np.conj(np.fft.rfft(a, size)), size)
    max_lag = min(int(max_lag_s * sr), la - 1, lb - 1)
    lags = np.arange(-max_lag, max_lag + 1)
    c = corr[lags % size]
    ca = np.concatenate([[0.0], np.cumsum(a * a)])
    cb = np.concatenate([[0.0], np.cumsum(b * b)])
    lo = np.maximum(0, -lags)  # first ref index in the overlap
    hi = np.minimum(la, lb - lags)  # one past the last ref index
    valid = (hi - lo) >= 0.5 * min(la, lb)
    ea = ca[np.clip(hi, 0, la)] - ca[np.clip(lo, 0, la)]
    eb = cb[np.clip(hi + lags, 0, lb)] - cb[np.clip(lo + lags, 0, lb)]
    norm = np.sqrt(np.maximum(ea * eb, 1e-30))
    ncc = np.where(valid, c / norm, -np.inf)
    k = int(np.argmax(ncc))
    peak = float(ncc[k])
    if not np.isfinite(peak):
        return 0.0, 0.0
    frac = 0.0
    if 0 < k < len(ncc) - 1 and np.isfinite(ncc[k - 1]) and np.isfinite(ncc[k + 1]):
        y0, y1, y2 = ncc[k - 1], ncc[k], ncc[k + 1]
        denom = y0 - 2 * y1 + y2
        if abs(denom) > 1e-12:
            frac = float(np.clip(0.5 * (y0 - y2) / denom, -1.0, 1.0))
    return (float(lags[k]) + frac) / sr, float(np.clip(peak, 0.0, 1.0))


def _start_time(media: Path | str) -> float:
    """Start time (s) of the first audio stream; ffmpeg drops a leading gap when decoding."""
    stream = audio_stream(media)
    try:
        return float((stream or {}).get("start_time", 0.0))
    except (TypeError, ValueError):
        return 0.0


def check_voice(
    base_video: Path | str, final_media: Path | str, max_lag_s: float = MAX_LAG_S
) -> VoiceCheck:
    """Offset (ms, positive = final is late) and similarity (0..1) of the voice vs the base."""
    ref = decode_mono(base_video, CHECK_SR)
    test = decode_mono(final_media, CHECK_SR)
    lag, sim = cross_correlate(ref, test, CHECK_SR, max_lag_s)
    lag += _start_time(final_media) - _start_time(base_video)
    return VoiceCheck(offset_ms=round(lag * 1000.0, 3), similarity=round(sim, 4))
