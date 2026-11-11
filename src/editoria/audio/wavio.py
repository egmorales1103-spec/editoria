"""Minimal WAV reading and media decoding to numpy (all ffmpeg calls go through util.ffmpeg)."""

from __future__ import annotations

import struct
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

from editoria.util import ffmpeg

SAMPLE_RATE = 48_000


class AudioError(RuntimeError):
    """Base class for user-facing audio errors (messages are in Spanish)."""


class NoAudioError(AudioError):
    """The media has no audio stream."""


def read_wav(path: Path | str) -> tuple[np.ndarray, int]:
    """Read a PCM (8/16/24/32-bit) or IEEE-float WAV into float32 ``(frames, channels)``."""
    data = Path(path).read_bytes()
    if data[:4] not in (b"RIFF", b"RF64") or data[8:12] != b"WAVE":
        raise AudioError(f"'{path}' no es un archivo WAV válido.")
    pos = 12
    fmt: tuple[int, int, int, int] | None = None
    payload = b""
    while pos + 8 <= len(data):
        cid = data[pos : pos + 4]
        size = struct.unpack("<I", data[pos + 4 : pos + 8])[0]
        body = data[pos + 8 : pos + 8 + size]
        if cid == b"fmt ":
            tag, ch, sr, _, _, bits = struct.unpack("<HHIIHH", body[:16])
            if tag == 0xFFFE and len(body) >= 26:  # WAVE_FORMAT_EXTENSIBLE
                tag = struct.unpack("<H", body[24:26])[0]
            fmt = (tag, ch, sr, bits)
        elif cid == b"data":
            if size == 0xFFFFFFFF or pos + 8 + size > len(data):
                size = len(data) - pos - 8
            payload = data[pos + 8 : pos + 8 + size]
            break
        pos += 8 + size + (size & 1)
    if fmt is None:
        raise AudioError(f"'{path}' no tiene cabecera 'fmt ' (WAV dañado).")
    tag, ch, sr, bits = fmt
    arr: np.ndarray[Any, Any]
    if tag == 3 and bits == 32:
        arr = np.frombuffer(payload[: len(payload) // 4 * 4], dtype="<f4").astype(np.float32)
    elif tag == 3 and bits == 64:
        arr = np.frombuffer(payload[: len(payload) // 8 * 8], dtype="<f8").astype(np.float32)
    elif tag == 1 and bits == 16:
        arr = np.frombuffer(payload[: len(payload) // 2 * 2], dtype="<i2").astype(np.float32)
        arr /= 32768.0
    elif tag == 1 and bits == 24:
        raw = np.frombuffer(payload[: len(payload) // 3 * 3], dtype=np.uint8).reshape(-1, 3)
        ints = (
            raw[:, 0].astype(np.int32) | (raw[:, 1].astype(np.int32) << 8)
            | (raw[:, 2].astype(np.int32) << 16)
        )  # fmt: skip
        ints = np.where(ints >= 1 << 23, ints - (1 << 24), ints)
        arr = ints.astype(np.float32) / float(1 << 23)
    elif tag == 1 and bits == 32:
        arr = np.frombuffer(payload[: len(payload) // 4 * 4], dtype="<i4").astype(np.float32)
        arr /= 2147483648.0
    elif tag == 1 and bits == 8:
        arr = (np.frombuffer(payload, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    else:
        raise AudioError(f"Formato WAV no soportado (tag={tag}, bits={bits}) en '{path}'.")
    frames = len(arr) // ch
    return arr[: frames * ch].reshape(frames, ch), sr


def audio_stream(media: Path | str) -> dict[str, Any] | None:
    """First audio stream reported by ffprobe, or None."""
    info = ffmpeg.probe(media)
    for s in info.get("streams", []):
        if s.get("codec_type") == "audio":
            s = dict(s)
            s.setdefault("duration", info.get("format", {}).get("duration"))
            return s
    return None


def require_audio(media: Path | str, what: str = "El video base") -> dict[str, Any]:
    stream = audio_stream(media)
    if stream is None:
        raise NoAudioError(
            f"{what} ('{Path(media).name}') no tiene pista de audio. "
            "El audio original manda y EditorIA no sintetiza voz: no se puede mezclar. "
            "Verificá el archivo (ffprobe) o entregá un VIDEO_BASE con audio."
        )
    return stream


def decode_mono(media: Path | str, sr: int = SAMPLE_RATE) -> np.ndarray:
    """Decode the first audio stream to mono float32 at ``sr`` (channels averaged)."""
    require_audio(media, "El archivo")
    with tempfile.TemporaryDirectory(prefix="editoria_audio_") as tmp:
        out = Path(tmp) / "decoded.wav"
        ffmpeg.run(
            [
                "-i",
                str(media),
                "-vn",
                "-map",
                "0:a:0",
                "-ac",
                "1",
                "-ar",
                str(sr),
                "-c:a",
                "pcm_f32le",
                str(out),
            ]
        )
        samples, _ = read_wav(out)
    return samples[:, 0]


def decode_native(media: Path | str, sr: int = SAMPLE_RATE) -> np.ndarray:
    """Decode to float32 ``(frames, channels)`` keeping the channel count, at ``sr``."""
    require_audio(media, "El archivo")
    with tempfile.TemporaryDirectory(prefix="editoria_audio_") as tmp:
        out = Path(tmp) / "decoded.wav"
        ffmpeg.run(
            [
                "-i",
                str(media),
                "-vn",
                "-map",
                "0:a:0",
                "-ar",
                str(sr),
                "-c:a",
                "pcm_f32le",
                str(out),
            ]
        )
        samples, _ = read_wav(out)
    return samples
