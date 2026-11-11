#!/usr/bin/env python
"""Deterministic synthesis of the bundled EditorIA sound effects (CC0-1.0).

Six cues (pop, click, whoosh, ding, teclado, impacto_suave), three variants each, written as
48 kHz mono 16-bit WAV files into ``assets/sfx/`` together with ``manifest.yaml``.

Everything is synthesised from scratch with numpy (oscillators, filtered noise, envelopes):
no samples from third parties are used, so the output can be released under CC0-1.0.
The generator is deterministic (fixed seed, no dependence on the clock or the environment) and
the WAV header is written by a fixed writer, so the sha256 values in the manifest are
reproducible.

Usage::

    uv run python scripts/gen_sfx.py            # (re)write WAV files + manifest
    uv run python scripts/gen_sfx.py --check    # verify files and hashes, write nothing
"""

from __future__ import annotations

import argparse
import hashlib
import io
import sys
import wave
from collections.abc import Callable
from pathlib import Path

import numpy as np

SR = 48_000
SEED = 20_261_111
PEAK_DBFS = -1.0
VARIANTS = (1, 2, 3)
CUES = ("pop", "click", "whoosh", "ding", "teclado", "impacto_suave")
LICENSE = "CC0-1.0"
LICENSE_URL = "https://creativecommons.org/publicdomain/zero/1.0/"
AUTHOR = "EditorIA contributors"
SOURCE = "scripts/gen_sfx.py (síntesis propia, determinística)"

SUGGESTED_USE = {
    "pop": "Acento corto al aparecer una palabra clave, un ícono o un emoji.",
    "click": "Acento seco y discreto para ítems de lista, botones o cambios de paso.",
    "whoosh": "Movimiento breve: transición entre planos o desplazamiento de un gráfico.",
    "ding": "Confirmación o logro: un resultado, un dato cumplido o un cierre de idea.",
    "teclado": "Tecleo corto para texto que se escribe, mensajes o ejemplos de uso.",
    "impacto_suave": "Énfasis grave y suave sobre una frase o dato importante (sin golpe duro).",
}

Array = np.ndarray


# ---------------------------------------------------------------------------------------
# Small DSP toolbox (numpy only).
# ---------------------------------------------------------------------------------------
def _t(n: int) -> Array:
    return np.arange(n, dtype=np.float64) / SR


def _n(seconds: float) -> int:
    return round(seconds * SR)


def _fft_filter(x: Array, lo: float | None, hi: float | None, order: int = 3) -> Array:
    """Zero-phase Butterworth-magnitude band filter applied in the frequency domain."""
    n = len(x)
    size = 1 << (n - 1).bit_length()
    spec = np.fft.rfft(x, size)
    f = np.fft.rfftfreq(size, 1.0 / SR)
    mag = np.ones_like(f)
    if hi is not None:
        mag *= 1.0 / np.sqrt(1.0 + (f / hi) ** (2 * order))
    if lo is not None:
        ratio = np.where(f > 0, lo / np.maximum(f, 1e-9), 1e9)
        mag *= 1.0 / np.sqrt(1.0 + ratio ** (2 * order))
    return np.asarray(np.fft.irfft(spec * mag, size)[:n])


def _noise(rng: np.random.Generator, n: int) -> Array:
    return rng.standard_normal(n)


def _exp_env(n: int, tau: float, attack: float = 0.0008) -> Array:
    t = _t(n)
    env = np.exp(-t / tau)
    if attack > 0:
        env *= 1.0 - np.exp(-t / (attack / 3.0))
    return np.asarray(env)


def _fade_out(x: Array, seconds: float) -> Array:
    k = min(_n(seconds), len(x))
    if k > 1:
        x = x.copy()
        x[-k:] *= 0.5 * (1.0 + np.cos(np.linspace(0.0, np.pi, k)))
    return x


def _fade_in(x: Array, seconds: float) -> Array:
    k = min(_n(seconds), len(x))
    if k > 1:
        x = x.copy()
        x[:k] *= 0.5 * (1.0 - np.cos(np.linspace(0.0, np.pi, k)))
    return x


def _svf_bandpass(x: Array, fc: Array, q: float) -> Array:
    """Chamberlin state-variable band-pass with a per-sample centre frequency (Hz)."""
    out = np.empty_like(x)
    low = 0.0
    band = 0.0
    damp = 1.0 / q
    coef = 2.0 * np.sin(np.pi * np.minimum(fc, SR / 6.0) / SR)
    for i in range(len(x)):
        low += coef[i] * band
        high = x[i] - low - damp * band
        band += coef[i] * high
        out[i] = band
    return out


def _place(dst: Array, src: Array, at: float) -> None:
    i = _n(at)
    j = min(len(dst), i + len(src))
    if i < j:
        dst[i:j] += src[: j - i]


# ---------------------------------------------------------------------------------------
# Cue synthesis. Each function returns a float array (any scale; normalised later).
# ---------------------------------------------------------------------------------------
def synth_pop(variant: int, rng: np.random.Generator) -> Array:
    """Soft bubble pop: short sine with a fast downward pitch glide and a tiny air transient."""
    f_start, f_end, tau_p = {1: (880, 360, 0.016), 2: (1010, 430, 0.014), 3: (740, 310, 0.019)}[
        variant
    ]
    n = _n(0.24)
    t = _t(n)
    freq = f_end + (f_start - f_end) * np.exp(-t / tau_p)
    phase = 2 * np.pi * np.cumsum(freq) / SR
    body = np.sin(phase) * _exp_env(n, 0.042, attack=0.0015)
    body += 0.22 * np.sin(2 * phase) * _exp_env(n, 0.018, attack=0.0015)
    air = _fft_filter(_noise(rng, n), 2500, 7500) * _exp_env(n, 0.0022, attack=0.0004)
    x = body + 0.10 * air / max(np.abs(air).max(), 1e-9)
    return _fade_out(x, 0.05)


def synth_click(variant: int, rng: np.random.Generator) -> Array:
    """Dry, clean UI click: band-limited noise tick plus a damped resonance."""
    f_res, tau_n, lo, hi = {
        1: (2300, 0.0035, 1800, 6500),
        2: (3000, 0.0030, 2400, 7500),
        3: (1800, 0.0042, 1400, 5200),
    }[variant]
    n = _n(0.11)
    t = _t(n)
    tick = _fft_filter(_noise(rng, n), lo, hi) * _exp_env(n, tau_n, attack=0.0003)
    tick /= max(np.abs(tick).max(), 1e-9)
    ring = np.sin(2 * np.pi * f_res * t) * _exp_env(n, 0.0065, attack=0.0003)
    thock = np.sin(2 * np.pi * 620 * t) * _exp_env(n, 0.009, attack=0.0004)
    x = 0.85 * tick + 0.55 * ring + 0.28 * thock
    return _fade_out(x, 0.03)


def synth_whoosh(variant: int, rng: np.random.Generator) -> Array:
    """Airy swoosh: noise through a sweeping band-pass with a fast swell and a long soft tail."""
    dur, f0, f1, q, tau, rise = {
        1: (0.62, 500.0, 4300.0, 3.0, 0.21, 0.035),
        2: (0.78, 3800.0, 420.0, 2.6, 0.26, 0.045),
        3: (0.52, 750.0, 5200.0, 3.4, 0.18, 0.028),
    }[variant]
    n = _n(dur)
    t = _t(n)
    sweep = (t / dur) ** 0.7
    fc = f0 * (f1 / f0) ** sweep
    src = _noise(rng, n)
    # Two cascaded band-passes: a steeper skirt than a single one makes the sweep audible.
    air = _svf_bandpass(_svf_bandpass(src, fc, q), fc, q)
    air /= np.sqrt(fc / 1000.0)  # noise power grows with bandwidth: keep the level even
    # A softer layer an octave below follows the sweep and gives the movement some body.
    low = _svf_bandpass(src, fc * 0.45, 1.4) / np.sqrt(fc * 0.45 / 1000.0)
    low *= np.abs(air).max() / max(np.abs(low).max(), 1e-9)
    env = (1.0 - np.exp(-t / rise)) * np.exp(-t / tau)
    x = (air + 0.30 * low) * env
    return _fade_out(x, 0.12)


def synth_ding(variant: int, rng: np.random.Generator) -> Array:
    """Glassy bell: a few inharmonic partials with individual decays and a soft mallet tick."""
    f0 = {1: 1568.0, 2: 1318.5, 3: 1760.0}[variant]
    dur = 1.15
    n = _n(dur)
    t = _t(n)
    partials = [  # (ratio, amplitude, decay seconds)
        (1.0, 1.00, 0.42),
        (2.0, 0.18, 0.22),
        (2.76, 0.30, 0.20),
        (5.40, 0.12, 0.10),
        (8.93, 0.05, 0.05),
    ]
    x = np.zeros(n)
    for k, (ratio, amp, tau) in enumerate(partials):
        f = f0 * ratio
        shimmer = 1.0 + 0.0035 * (1 if k % 2 == 0 else -1)
        x += amp * np.sin(2 * np.pi * f * t) * np.exp(-t / tau)
        x += 0.35 * amp * np.sin(2 * np.pi * f * shimmer * t + 0.7 * k) * np.exp(-t / tau)
    x *= 1.0 - np.exp(-t / 0.0007)
    mallet = _fft_filter(_noise(rng, n), 1800, 6000) * _exp_env(n, 0.0025, attack=0.0003)
    x += 0.10 * mallet / max(np.abs(mallet).max(), 1e-9) * np.abs(x).max()
    return _fade_out(x, 0.25)


def synth_teclado(variant: int, rng: np.random.Generator) -> Array:
    """Short burst of soft keystrokes (thock plus a light top click), irregular timing."""
    gaps = {
        1: [0.0, 0.085, 0.17, 0.30, 0.385],
        2: [0.0, 0.10, 0.19, 0.27, 0.40, 0.49],
        3: [0.0, 0.075, 0.20, 0.285],
    }[variant]
    center = {1: 2200.0, 2: 1700.0, 3: 2800.0}[variant]
    dur = gaps[-1] + 0.14
    out = np.zeros(_n(dur))
    for idx, at in enumerate(gaps):
        key_n = _n(0.11)
        t = _t(key_n)
        jitter = float(rng.uniform(0.85, 1.2))
        amp = float(rng.uniform(0.65, 1.0)) if idx else 1.0
        top = _fft_filter(_noise(rng, key_n), center * jitter * 0.6, center * jitter * 1.9)
        top = top / max(np.abs(top).max(), 1e-9) * _exp_env(key_n, 0.0045, attack=0.0003)
        thock = np.sin(2 * np.pi * 190 * jitter * t) * _exp_env(key_n, 0.011, attack=0.0005)
        key = amp * (0.8 * top + 0.5 * thock)
        _place(out, key, at)
    return _fade_out(out, 0.06)


def synth_impacto_suave(variant: int, rng: np.random.Generator) -> Array:
    """Soft low thud: pitch-dropping sine, a muffled noise transient and a faint warm tail."""
    f_start, f_end, tau_p, tau_a = {
        1: (125.0, 52.0, 0.075, 0.20),
        2: (100.0, 46.0, 0.090, 0.24),
        3: (150.0, 60.0, 0.060, 0.17),
    }[variant]
    n = _n(0.95)
    t = _t(n)
    freq = f_end + (f_start - f_end) * np.exp(-t / tau_p)
    phase = 2 * np.pi * np.cumsum(freq) / SR
    sub = np.sin(phase) * _exp_env(n, tau_a, attack=0.004)
    sub += 0.45 * np.sin(2 * phase) * _exp_env(n, tau_a * 0.6, attack=0.004)
    thud = _fft_filter(_noise(rng, n), None, 420, order=2) * _exp_env(n, 0.03, attack=0.002)
    thud *= 0.9 * np.abs(sub).max() / max(np.abs(thud).max(), 1e-9)
    tail = _fft_filter(_noise(rng, n), 90, 1100, order=2) * _exp_env(n, 0.26, attack=0.02)
    tail *= 0.08 * np.abs(sub).max() / max(np.abs(tail).max(), 1e-9)
    x = sub + 0.5 * thud + tail
    return _fade_out(x, 0.18)


SYNTH: dict[str, Callable[[int, np.random.Generator], Array]] = {
    "pop": synth_pop,
    "click": synth_click,
    "whoosh": synth_whoosh,
    "ding": synth_ding,
    "teclado": synth_teclado,
    "impacto_suave": synth_impacto_suave,
}


# ---------------------------------------------------------------------------------------
# Rendering / writing
# ---------------------------------------------------------------------------------------
def render(cue: str, variant: int) -> Array:
    """Float samples in [-1, 1] with a sample peak of PEAK_DBFS, DC removed, faded in/out."""
    rng = np.random.default_rng([SEED, CUES.index(cue), variant])
    x = SYNTH[cue](variant, rng)
    x = x - x.mean()
    x = _fade_in(x, 0.0004)
    x = _fade_out(x, 0.012)  # DC removal above leaves a step: close the tail exactly at 0
    x = x / np.abs(x).max() * 10 ** (PEAK_DBFS / 20.0)
    return x


def to_pcm16(x: Array) -> Array:
    return np.round(np.clip(x, -1.0, 1.0) * 32767.0).astype("<i2")


def wav_bytes(pcm: Array) -> bytes:
    """Canonical 44-byte-header WAV (mono, 48 kHz, 16-bit); same input -> same bytes."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.astype("<i2").tobytes())
    return buf.getvalue()


def sfx_id(cue: str, variant: int) -> str:
    return f"{cue}_{variant}"


def generate_all() -> dict[str, bytes]:
    """``{<cue>_<n>: wav bytes}`` for every cue and variant."""
    return {sfx_id(cue, v): wav_bytes(to_pcm16(render(cue, v))) for cue in CUES for v in VARIANTS}


def build_manifest(files: dict[str, bytes]):  # type: ignore[no-untyped-def]
    from editoria.schemas import AssetEntry, AssetManifest

    assets = []
    for cue in CUES:
        for v in VARIANTS:
            asset_id = sfx_id(cue, v)
            assets.append(
                AssetEntry(
                    id=asset_id,
                    path=f"assets/sfx/{asset_id}.wav",
                    kind="sfx",
                    license=LICENSE,
                    license_url=LICENSE_URL,
                    author=AUTHOR,
                    source_url=SOURCE,
                    sha256=hashlib.sha256(files[asset_id]).hexdigest(),
                    attribution="No requerida (CC0-1.0). Autoría: EditorIA contributors.",
                    suggested_use=f"{SUGGESTED_USE[cue]} (variante {v})",
                )
            )
    return AssetManifest(assets=assets)


def write_all(out_dir: Path) -> int:
    from editoria.schemas import write_model

    out_dir.mkdir(parents=True, exist_ok=True)
    files = generate_all()
    for asset_id, data in files.items():
        (out_dir / f"{asset_id}.wav").write_bytes(data)
    write_model(out_dir / "manifest.yaml", build_manifest(files))
    total = sum(len(d) for d in files.values())
    print(f"{len(files)} archivos escritos en {out_dir} ({total / 1024:.0f} KiB).")
    return 0


def check_all(out_dir: Path) -> int:
    from editoria.schemas import AssetManifest, read_model

    manifest = read_model(out_dir / "manifest.yaml", AssetManifest)
    files = generate_all()
    bad = 0
    for asset_id, data in files.items():
        entry = manifest.get(asset_id)
        on_disk = out_dir / f"{asset_id}.wav"
        digest = hashlib.sha256(data).hexdigest()
        if entry is None or entry.sha256 != digest:
            print(f"DIFERENTE (manifest): {asset_id}")
            bad += 1
        if not on_disk.exists() or hashlib.sha256(on_disk.read_bytes()).hexdigest() != digest:
            print(f"DIFERENTE (archivo): {asset_id}")
            bad += 1
    print("OK: los WAV y el manifest coinciden." if not bad else f"{bad} diferencias.")
    return 1 if bad else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Genera los SFX CC0 de EditorIA.")
    default_out = Path(__file__).resolve().parents[1] / "assets" / "sfx"
    parser.add_argument("--out", type=Path, default=default_out, help="carpeta de salida")
    parser.add_argument("--check", action="store_true", help="verifica sin escribir")
    args = parser.parse_args(argv)
    return check_all(args.out) if args.check else write_all(args.out)


if __name__ == "__main__":
    sys.exit(main())
