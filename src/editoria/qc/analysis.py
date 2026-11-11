"""Measurements for QC: decode errors, black/freeze, loudness, MP4 atoms, clipping, voice."""

from __future__ import annotations

import math
import re
import struct
import tempfile
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from editoria.schemas import VoiceCheck
from editoria.util import ffmpeg

Span = tuple[float, float]

BLACK_FILTER = "blackdetect=d=0.1:pix_th=0.10"
FREEZE_FILTER = "freezedetect=n=-60dB:d=0.5"

_BLACK_RE = re.compile(r"black_start:\s*([\d.]+)\s+black_end:\s*([\d.]+)")
_FREEZE_START_RE = re.compile(r"freeze_start:\s*([\d.]+)")
_FREEZE_END_RE = re.compile(r"freeze_end:\s*([\d.]+)")
_I_RE = re.compile(r"I:\s*(-?[\d.]+|-inf)\s*LUFS")
_LRA_RE = re.compile(r"LRA:\s*(-?[\d.]+)\s*LU")
_TP_RE = re.compile(r"Peak:\s*(-?[\d.]+|-inf)\s*dBFS")
_LEVEL_RE = re.compile(r"\[(error|fatal|panic)\]")


@dataclass
class VideoAnalysis:
    decode_errors: list[str] = field(default_factory=list)
    black: list[Span] = field(default_factory=list)
    freeze: list[Span] = field(default_factory=list)
    lufs: float | None = None
    lra: float | None = None
    true_peak: float | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "decode_errors": list(self.decode_errors),
            "black": [list(s) for s in self.black],
            "freeze": [list(s) for s in self.freeze],
            "lufs": _finite(self.lufs),
            "lra": self.lra,
            "true_peak": _finite(self.true_peak),
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> VideoAnalysis:
        def spans(key: str) -> list[Span]:
            return [(float(a), float(b)) for a, b in data.get(key, [])]

        def opt(key: str) -> float | None:
            v = data.get(key)
            if v == "-inf":
                return float("-inf")
            return None if v is None else float(v)

        return cls(
            decode_errors=[str(e) for e in data.get("decode_errors", [])],
            black=spans("black"),
            freeze=spans("freeze"),
            lufs=opt("lufs"),
            lra=opt("lra"),
            true_peak=opt("true_peak"),
        )


def _finite(x: float | None) -> float | str | None:
    """JSON has no -inf: keep it as the string '-inf'."""
    if x is not None and math.isinf(x):
        return "-inf"
    return x


def _num(text: str) -> float:
    return float("-inf") if text == "-inf" else float(text)


def parse_black(log: str) -> list[Span]:
    return [(float(a), float(b)) for a, b in _BLACK_RE.findall(log)]


def parse_freeze(log: str, duration: float) -> list[Span]:
    starts = [float(x) for x in _FREEZE_START_RE.findall(log)]
    ends = [float(x) for x in _FREEZE_END_RE.findall(log)]
    spans: list[Span] = []
    for i, s in enumerate(starts):
        spans.append((s, ends[i] if i < len(ends) else duration))
    return spans


def analyze_media(path: Path, *, audio: bool, duration: float) -> VideoAnalysis:
    """One full decode pass: decode errors, black/freeze spans and (optionally) EBU R128."""
    graph = f"[0:v]{BLACK_FILTER},{FREEZE_FILTER}[v]"
    maps = ["-map", "[v]"]
    if audio:
        graph += ";[0:a]ebur128=peak=true[a]"
        maps += ["-map", "[a]"]
    proc = ffmpeg.run(
        ["-v", "level+info", "-nostats", "-i", path.name, "-filter_complex", graph, *maps,
         "-f", "null", "-"],
        cwd=path.parent,
        check=False,
    )  # fmt: skip
    log = proc.stderr
    res = VideoAnalysis()
    res.decode_errors = [ln.strip() for ln in log.splitlines() if _LEVEL_RE.search(ln)]
    if proc.returncode != 0 and not res.decode_errors:
        res.decode_errors = [f"ffmpeg terminó con código {proc.returncode}"]
    res.black = parse_black(log)
    res.freeze = parse_freeze(log, duration)
    if audio:
        summary = log[log.rfind("Summary:") :] if "Summary:" in log else log
        if m := _I_RE.search(summary):
            res.lufs = _num(m.group(1))
        if m := _LRA_RE.search(summary):
            res.lra = float(m.group(1))
        if m := _TP_RE.search(summary):
            res.true_peak = _num(m.group(1))
    return res


def new_spans(found: list[Span], reference: list[Span], tol: float = 0.1) -> list[Span]:
    """Spans of ``found`` that do not overlap any ``reference`` span (± tol)."""
    out = []
    for a, b in found:
        if not any(a < rb + tol and ra - tol < b for ra, rb in reference):
            out.append((a, b))
    return out


def mp4_top_atoms(path: Path) -> list[tuple[str, int]]:
    """Top-level MP4 boxes as (type, offset)."""
    atoms: list[tuple[str, int]] = []
    size_total = path.stat().st_size
    with path.open("rb") as fh:
        offset = 0
        while offset + 8 <= size_total:
            fh.seek(offset)
            header = fh.read(8)
            if len(header) < 8:
                break
            size, kind = struct.unpack(">I4s", header)
            if size == 1:
                size = struct.unpack(">Q", fh.read(8))[0]
            elif size == 0:
                size = size_total - offset
            atoms.append((kind.decode("latin-1"), offset))
            if size < 8:
                break
            offset += size
    return atoms


def is_faststart(path: Path) -> tuple[bool, list[tuple[str, int]]]:
    atoms = mp4_top_atoms(path)
    pos = {k: off for k, off in reversed(atoms)}
    ok = "moov" in pos and "mdat" in pos and pos["moov"] < pos["mdat"]
    return ok, atoms


def decode_pcm(
    path: Path, *, sr: int, mono: bool, max_s: float | None = None
) -> tuple[np.ndarray, int]:
    """Decode the first audio stream to int16 samples (frames x channels)."""
    with tempfile.TemporaryDirectory(prefix="editoria_qc_") as tmp:
        wav = Path(tmp) / "a.wav"
        args: list[str] = ["-i", path.name, "-vn", "-map", "0:a:0"]
        if max_s is not None:
            args += ["-t", f"{max_s:.3f}"]
        if mono:
            args += ["-ac", "1"]
        args += ["-ar", str(sr), "-c:a", "pcm_s16le", str(wav)]
        ffmpeg.run(args, cwd=path.parent)
        with wave.open(str(wav), "rb") as wf:
            ch = wf.getnchannels()
            data = np.frombuffer(wf.readframes(wf.getnframes()), dtype="<i2")
    return data.reshape(-1, ch), sr


def count_clipped(path: Path, sr: int = 48000) -> int:
    """Samples at (or beyond) full scale after decoding."""
    data, _ = decode_pcm(path, sr=sr, mono=False)
    return int(np.count_nonzero(np.abs(data.astype(np.int32)) >= 32766))


def correlate_voice(
    reference: Path, candidate: Path, *, sr: int = 8000, max_s: float = 60.0, max_lag_s: float = 1.0
) -> VoiceCheck:
    """Fallback voice check: normalised cross-correlation of the two soundtracks.

    ``offset_ms`` > 0 means the candidate's voice comes later than the reference.
    """
    a, _ = decode_pcm(reference, sr=sr, mono=True, max_s=max_s)
    b, _ = decode_pcm(candidate, sr=sr, mono=True, max_s=max_s)
    x = a[:, 0].astype(np.float64)
    y = b[:, 0].astype(np.float64)
    n = min(len(x), len(y))
    if n < sr // 4:
        return VoiceCheck(offset_ms=0.0, similarity=0.0)
    x = x[:n] - x[:n].mean()
    y = y[:n] - y[:n].mean()
    denom = float(np.sqrt(np.dot(x, x) * np.dot(y, y)))
    if denom <= 0:
        return VoiceCheck(offset_ms=0.0, similarity=0.0)
    size = 1 << int(np.ceil(np.log2(2 * n)))
    corr = np.fft.irfft(np.fft.rfft(y, size) * np.conj(np.fft.rfft(x, size)), size)
    max_lag = int(max_lag_s * sr)
    lags = np.concatenate([np.arange(0, max_lag + 1), np.arange(-max_lag, 0)])
    vals = np.concatenate([corr[: max_lag + 1], corr[size - max_lag :]])
    i = int(np.argmax(vals))
    lag = int(lags[i])
    similarity = float(max(0.0, min(1.0, vals[i] / denom)))
    return VoiceCheck(offset_ms=round(lag * 1000.0 / sr, 2), similarity=round(similarity, 4))
