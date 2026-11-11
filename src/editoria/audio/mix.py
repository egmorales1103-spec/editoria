"""Mix of base audio + SFX (+ optional ducked music) with two-pass linear loudnorm.

Signal flow (all inside one ffmpeg filtergraph, run through ``util.ffmpeg``)::

    base audio -> aresample 48 kHz ------------------------------+
    SFX n      -> volume(gain_db) -> adelay(at) ------------------+--> amix(normalize=0)
    music      -> volume -> sidechaincompress(key = voice) -------+        |
                                                                          loudnorm (2 pass,
                                                                          linear=true)

The voice only goes through resampling and the final constant gain of the linear loudnorm:
no EQ, compression or limiting. If the requested loudness cannot be reached linearly without
exceeding the true-peak ceiling, the target is lowered (never compressed) and a warning is
logged.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from editoria.audio.density import check_sfx_density
from editoria.audio.loudness import (
    loudnorm_measure,
    measure_loudness,
    parse_loudnorm_json,
)
from editoria.audio.sfx import resolve_sfx
from editoria.audio.voice import check_voice as _check_voice
from editoria.audio.wavio import SAMPLE_RATE, AudioError, decode_mono, read_wav, require_audio
from editoria.policy.immutable import ensure_not_delivered
from editoria.schemas import (
    EditPlan,
    MixResult,
    MixSpec,
    MusicSpec,
    SfxCue,
    VoiceCheck,
    write_model,
)
from editoria.util import ffmpeg, resources
from editoria.util.log import warn
from editoria.util.project import ProjectContext

TP_MARGIN_DB = 0.1  # internal safety margin under the requested true-peak ceiling
TP_CHECK_DB = 0.03  # re-render if the measured peak is above (ceiling - this)
MAX_RETRIES = 4
MUSIC_FADE_S = 1.5
FRAME = 960  # 20 ms analysis frames @ 48 kHz

# Ducking: sidechaincompress with a high ratio; the threshold is derived from the voice level
# so the music drops by ~duck_db while the voice is present (calibrated in tests).
DUCK_RATIO = 20.0
DUCK_ATTACK_MS = 12.0
DUCK_RELEASE_MS = 350.0
DUCK_CALIBRATION_DB = 7.6  # measured: ffmpeg detector reads ~7.6 dB above the median voice RMS


@lru_cache(maxsize=1)
def amix_has_normalize() -> bool:
    """True when this ffmpeg's amix supports ``normalize`` (7.1+)."""
    out = ffmpeg.run(["-h", "filter=amix"]).stdout
    return "normalize" in out


@dataclass(frozen=True)
class _Placed:
    cue: SfxCue
    path: Path
    delay_samples: int


def duck_threshold(voice: np.ndarray, duck_db: float) -> float:
    """Linear threshold so the compressor removes ~|duck_db| dB while the voice speaks."""
    depth = abs(duck_db)
    n = len(voice) // FRAME
    if n == 0 or depth == 0:
        return 1.0
    frames = voice[: n * FRAME].reshape(n, FRAME)
    rms = np.sqrt((frames.astype(np.float64) ** 2).mean(axis=1))
    active = rms > rms.max() * 10 ** (-25 / 20)
    level = float(np.median(rms[active])) if active.any() else float(rms.max())
    level_db = 20 * math.log10(max(level, 1e-6))
    thr_db = level_db - depth / (1.0 - 1.0 / DUCK_RATIO) + DUCK_CALIBRATION_DB
    return float(min(max(10 ** (thr_db / 20), 0.000976563), 1.0))


def duck_filter(voice: np.ndarray, duck_db: float) -> str:
    """The ``sidechaincompress`` filter (music = main input, voice = sidechain)."""
    thr = duck_threshold(voice, duck_db)
    return (
        f"sidechaincompress=threshold={thr:.6f}:ratio={DUCK_RATIO}:"
        f"attack={DUCK_ATTACK_MS}:release={DUCK_RELEASE_MS}:knee=1.5:"
        "detection=rms:link=average"
    )


class FFmpegAudioMixer:
    """Implements :class:`editoria.contracts.AudioMixer`.

    ``sfx_dir`` overrides ``assets/sfx``; ``music_root`` is where relative ``MusicSpec.path``
    values are resolved (e.g. the project folder). ``legacy_amix`` forces the fallback used
    with ffmpeg builds whose amix has no ``normalize`` option.
    """

    def __init__(
        self,
        sfx_dir: Path | None = None,
        music_root: Path | None = None,
        legacy_amix: bool | None = None,
    ) -> None:
        self.sfx_dir = sfx_dir
        self.music_root = music_root
        self.legacy_amix = (not amix_has_normalize()) if legacy_amix is None else legacy_amix

    # ---- public API -----------------------------------------------------------------------
    def check_voice(self, base_video: Path, final_media: Path) -> VoiceCheck:
        return _check_voice(base_video, final_media)

    def mix(
        self,
        base_video: Path,
        cues: list[SfxCue],
        music: MusicSpec | None,
        spec: MixSpec,
        out_wav: Path,
    ) -> MixResult:
        stream = require_audio(base_video)
        duration = float(stream.get("duration") or 0.0)
        if duration <= 0:
            duration = ffmpeg.media_duration(base_video)
        channels = int(stream.get("channels") or 1)
        layout = "mono" if channels == 1 else "stereo"

        placed: list[_Placed] = []
        for cue in sorted(cues, key=lambda c: c.at):
            if cue.at >= duration:
                warn(f"SFX '{cue.cue}' en {cue.at:.2f} s queda fuera del audio ({duration:.2f} s).")
                continue
            path = resolve_sfx(cue.cue, cue.variant, self.sfx_dir)
            placed.append(_Placed(cue, path, round(cue.at * SAMPLE_RATE)))

        music_path = self._resolve_music(music) if music else None
        inputs: list[str | Path] = ["-i", str(base_video)]
        for p in placed:
            inputs += ["-i", str(p.path)]
        if music_path:
            inputs += ["-i", str(music_path)]

        voice = decode_mono(base_video, SAMPLE_RATE)
        graph = self._graph(placed, music, music_path, spec, duration, layout, voice)
        out_wav = Path(out_wav)
        out_wav.parent.mkdir(parents=True, exist_ok=True)

        meas = loudnorm_measure(
            graph, inputs, target_i=spec.target_lufs, target_tp=spec.true_peak_db
        )
        if not math.isfinite(meas["input_i"]) or meas["input_i"] <= -69.9:
            raise AudioError(
                "El audio base es silencio (o está por debajo de -70 LUFS): no hay nada que "
                "normalizar. Revisá que el VIDEO_BASE tenga la voz."
            )

        ceiling = spec.true_peak_db - TP_MARGIN_DB
        target_i = spec.target_lufs
        # Linear mode only works if the needed gain keeps the peak under the ceiling.
        excess = meas["input_tp"] + (target_i - meas["input_i"]) - ceiling
        if excess > 0:
            warn(
                f"No se alcanzan {spec.target_lufs:.1f} LUFS sin superar {spec.true_peak_db:.1f} "
                f"dBTP de forma lineal: se normaliza a {target_i - excess:.1f} LUFS para no "
                "comprimir la voz."
            )
            target_i -= excess
        loud = None
        for _ in range(MAX_RETRIES):
            self._render_final(graph, inputs, meas, target_i, ceiling, out_wav)
            loud = measure_loudness(out_wav)
            over = loud.true_peak_db - (spec.true_peak_db - TP_CHECK_DB)
            if over <= 0:
                break
            target_i -= over + 0.05
        assert loud is not None
        if loud.true_peak_db > spec.true_peak_db:
            warn(f"El true peak final ({loud.true_peak_db:.2f} dBTP) supera {spec.true_peak_db}.")

        return MixResult(
            wav=out_wav,
            lufs=round(loud.integrated_lufs, 2),
            true_peak=round(loud.true_peak_db, 2),
            lra=round(loud.lra, 2),
            clipped_samples=loud.clipped_samples,
            voice_to_sfx_db=self._voice_to_sfx(voice, placed),
        )

    # ---- graph ----------------------------------------------------------------------------
    def _graph(
        self,
        placed: Sequence[_Placed],
        music: MusicSpec | None,
        music_path: Path | None,
        spec: MixSpec,
        duration: float,
        layout: str,
        voice: np.ndarray,
    ) -> str:
        fmt = f"aformat=sample_fmts=fltp:channel_layouts={layout}"
        parts: list[str] = []
        has_music = music_path is not None and music is not None
        if has_music:
            parts.append(f"[0:a]aresample={SAMPLE_RATE},{fmt},asplit=2[vmix][vkey]")
        else:
            parts.append(f"[0:a]aresample={SAMPLE_RATE},{fmt}[vmix]")
        labels = ["[vmix]"]
        for i, p in enumerate(placed):
            chain = (
                f"[{i + 1}:a]aresample={SAMPLE_RATE},"
                "aformat=sample_fmts=fltp:channel_layouts=mono"
                f",volume={p.cue.gain_db:.3f}dB"
            )
            if p.delay_samples > 0:
                chain += f",adelay={p.delay_samples}S:all=1"
            if layout == "stereo":
                chain += ",pan=stereo|c0=c0|c1=c0"
            parts.append(f"{chain}[s{i}]")
            labels.append(f"[s{i}]")
        if has_music and music is not None:
            idx = len(placed) + 1
            fade_st = max(duration - MUSIC_FADE_S, 0.0)
            parts.append(
                f"[{idx}:a]aresample={SAMPLE_RATE},{fmt},volume={music.gain_db:.3f}dB,"
                f"aloop=loop=-1:size=2147483647,atrim=duration={duration:.6f},"
                f"asetpts=PTS-STARTPTS,afade=t=in:d=0.4,"
                f"afade=t=out:st={fade_st:.6f}:d={min(MUSIC_FADE_S, duration):.6f}[mus]"
            )
            parts.append(f"[mus][vkey]{duck_filter(voice, spec.duck_db)}[duck]")
            labels.append("[duck]")
        n = len(labels)
        if n == 1:
            parts.append("[vmix]anull[mixed]")
        elif not self.legacy_amix:
            parts.append(
                f"{''.join(labels)}amix=inputs={n}:duration=first:dropout_transition=0:"
                "normalize=0[mixed]"
            )
        else:  # amix without normalize: keep every input alive so the 1/n scale is constant
            padded = [labels[0]]
            for k, lab in enumerate(labels[1:]):
                parts.append(f"{lab}apad[p{k}]")
                padded.append(f"[p{k}]")
            parts.append(
                f"{''.join(padded)}amix=inputs={n}:duration=first:dropout_transition=0,"
                f"volume={n}[mixed]"
            )
        parts.append(f"[mixed]aresample={SAMPLE_RATE}[pre]")
        return ";".join(parts)

    # ---- loudnorm pass 2 ------------------------------------------------------------------
    @staticmethod
    def _render_final(
        graph: str,
        inputs: list[str | Path],
        meas: dict[str, float],
        target_i: float,
        ceiling: float,
        out_wav: Path,
    ) -> None:
        for _ in range(3):
            ln = (
                f"loudnorm=I={target_i:.2f}:TP={ceiling:.2f}:LRA=50:"
                f"measured_I={meas['input_i']:.2f}:measured_TP={meas['input_tp']:.2f}:"
                f"measured_LRA={meas['input_lra']:.2f}:measured_thresh={meas['input_thresh']:.2f}:"
                f"offset={meas['target_offset']:.2f}:linear=true:print_format=json"
            )
            flt = f"{graph};[pre]{ln},aresample={SAMPLE_RATE},aformat=sample_fmts=s16[out]"
            proc = ffmpeg.run(
                [
                    *inputs,
                    "-filter_complex",
                    flt,
                    "-map",
                    "[out]",
                    "-c:a",
                    "pcm_s16le",
                    "-ar",
                    str(SAMPLE_RATE),
                    "-fflags",
                    "+bitexact",
                    str(out_wav),
                ]
            )
            kind = str(parse_loudnorm_json(proc.stderr).get("normalization_type", "linear"))
            if kind == "linear":
                return
            target_i -= 0.5  # fell back to dynamic: lower the target until linear holds
        warn("loudnorm no pudo usar el modo lineal; la voz podría haber sido comprimida.")

    # ---- helpers --------------------------------------------------------------------------
    def _resolve_music(self, music: MusicSpec) -> Path:
        p = Path(music.path)
        candidates: list[Path] = []
        if p.is_absolute():
            candidates.append(p)
        else:
            if self.music_root:
                candidates.append(self.music_root / p)
            candidates.append(resources.repo_root() / p)
            candidates.append(Path.cwd() / p)
        for c in candidates:
            if c.exists():
                return c
        raise AudioError(f"No se encontró la música '{music.path}' (asset {music.asset_id}).")

    @staticmethod
    def _voice_to_sfx(voice: np.ndarray, placed: Sequence[_Placed]) -> float | None:
        """Voice / SFX power ratio (dB) over the 20 ms frames where both are active."""
        if not placed:
            return None
        bus = np.zeros(len(voice), dtype=np.float64)
        for p in placed:
            wav, sr = read_wav(p.path)
            x = wav[:, 0].astype(np.float64) if sr == SAMPLE_RATE else decode_mono(p.path)
            x = x * 10 ** (p.cue.gain_db / 20.0)
            end = min(len(bus), p.delay_samples + len(x))
            if end > p.delay_samples:
                bus[p.delay_samples : end] += x[: end - p.delay_samples]
        n = len(voice) // FRAME
        if n == 0:
            return None
        vp = (voice[: n * FRAME].astype(np.float64).reshape(n, FRAME) ** 2).mean(axis=1)
        sp = (bus[: n * FRAME].reshape(n, FRAME) ** 2).mean(axis=1)
        v_active = vp > float(np.max(vp)) * 10 ** (-25 / 10)
        s_active = (
            sp > float(np.max(sp)) * 10 ** (-40 / 10) if np.max(sp) > 0 else np.zeros(n, bool)
        )
        both = v_active & s_active
        if not both.any():
            return None
        return round(10 * math.log10(vp[both].sum() / sp[both].sum()), 2)


def mix_for_version(ctx: ProjectContext, version: str) -> MixResult:
    """Mix the plan of ``version`` over the project's original audio.

    Writes ``<version>/audio/mezcla.wav`` and ``mezcla.json`` (MixResult). SFX density
    problems are reported as warnings (the plan linter is the gate).
    """
    ensure_not_delivered(ctx, version)  # audio/ of a delivered version is immutable
    plan: EditPlan = ctx.load_plan(version)
    out_dir = ctx.version_dir(version) / "audio"
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        style = ctx.load_style(plan.style)
        for msg in check_sfx_density(plan.sfx, style):
            warn(msg)
    except FileNotFoundError:
        pass
    mixer = FFmpegAudioMixer(music_root=ctx.root)
    result = mixer.mix(
        ctx.original_video(), list(plan.sfx), plan.music, plan.mix, out_dir / "mezcla.wav"
    )
    write_model(out_dir / "mezcla.json", result)
    return result
