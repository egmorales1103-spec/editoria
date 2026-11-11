"""FFmpegAudioMixer: loudness, true peak, clipping, SFX timing, music ducking, errors."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pytest

from editoria.audio import (
    CUES,
    FFmpegAudioMixer,
    NoAudioError,
    check_voice,
    measure_loudness,
    mix_for_version,
    resolve_sfx,
)
from editoria.audio.mix import duck_filter
from editoria.audio.wavio import AudioError, decode_mono, read_wav
from editoria.contracts import AudioMixer
from editoria.schemas import MixResult, MixSpec, MusicSpec, SfxCue, read_model
from editoria.util import ffmpeg
from editoria.util.project import ProjectContext

FRAME_MS = 1000 / 30


def load_mono(path: Path) -> np.ndarray:
    x, _ = read_wav(path)
    return x[:, 0]


BASIC_CUES = [
    SfxCue(cue="pop", at=0.3),
    SfxCue(cue="whoosh", at=2.38, gain_db=-16),
    SfxCue(cue="ding", at=5.2),
    SfxCue(cue="teclado", at=7.7, variant=2),
]


def test_mixer_implements_contract() -> None:
    assert isinstance(FFmpegAudioMixer(), AudioMixer)


def test_default_mix_hits_targets_on_spaced_path(spaced_video: Path, audio_work: Path) -> None:
    out = audio_work / "salida mix ñ" / "mezcla.wav"
    res = FFmpegAudioMixer().mix(spaced_video, BASIC_CUES, None, MixSpec(), out)
    assert res.wav == out and out.exists()
    assert res.lufs == pytest.approx(-14.0, abs=1.0)
    assert res.true_peak <= -1.0
    assert res.clipped_samples == 0
    assert res.lra is not None
    # independent re-measurement
    again = measure_loudness(out)
    assert again.integrated_lufs == pytest.approx(-14.0, abs=1.0)
    assert again.true_peak_db <= -1.0
    assert again.clipped_samples == 0
    info = ffmpeg.probe(out)["streams"][0]
    assert info["codec_name"] == "pcm_s16le" and int(info["sample_rate"]) == 48000
    assert float(info["duration"]) == pytest.approx(12.0, abs=0.02)


def test_voice_is_untouched_by_the_mix(spaced_video: Path, audio_work: Path) -> None:
    out = audio_work / "voz ñ.wav"
    FFmpegAudioMixer().mix(spaced_video, BASIC_CUES, None, MixSpec(), out)
    res = check_voice(spaced_video, out)
    assert abs(res.offset_ms) <= FRAME_MS
    assert res.similarity > 0.95


def test_voice_to_sfx_reports_overlap_ratio(base_video: Path, audio_work: Path) -> None:
    mixer = FFmpegAudioMixer()
    loud = mixer.mix(
        base_video, [SfxCue(cue="pop", at=0.5, gain_db=-14)], None, MixSpec(), audio_work / "a.wav"
    )
    soft = mixer.mix(
        base_video, [SfxCue(cue="pop", at=0.5, gain_db=-24)], None, MixSpec(), audio_work / "b.wav"
    )
    assert loud.voice_to_sfx_db is not None and soft.voice_to_sfx_db is not None
    assert soft.voice_to_sfx_db - loud.voice_to_sfx_db == pytest.approx(10.0, abs=0.1)
    assert 5 < loud.voice_to_sfx_db < 30
    # An SFX placed in a pause shares no frames with the voice.
    in_pause = mixer.mix(
        base_video, [SfxCue(cue="click", at=5.1)], None, MixSpec(), audio_work / "c.wav"
    )
    assert in_pause.voice_to_sfx_db is None
    none = mixer.mix(base_video, [], None, MixSpec(), audio_work / "d.wav")
    assert none.voice_to_sfx_db is None


def test_custom_targets_are_honoured(base_video: Path, audio_work: Path) -> None:
    spec = MixSpec(target_lufs=-18.0, true_peak_db=-2.0)
    res = FFmpegAudioMixer().mix(base_video, BASIC_CUES, None, spec, audio_work / "m18.wav")
    assert res.lufs == pytest.approx(-18.0, abs=1.0)
    assert res.true_peak <= -2.0


def test_unreachable_loudness_never_compresses_the_voice(
    base_video: Path, audio_work: Path
) -> None:
    """-6 LUFS cannot be reached linearly under -1 dBTP: lower the target, keep the dynamics."""
    spec = MixSpec(target_lufs=-6.0, true_peak_db=-1.0)
    res = FFmpegAudioMixer().mix(base_video, [], None, spec, audio_work / "m6.wav")
    assert res.true_peak <= -1.0
    assert res.lufs < -6.5
    src = measure_loudness(base_video)
    # a constant gain keeps peak-to-loudness ratio (compression would shrink it)
    assert (res.true_peak - res.lufs) == pytest.approx(
        src.true_peak_db - src.integrated_lufs, abs=0.3
    )


def test_sfx_onsets_match_requested_times(noise_base: Path, audio_work: Path) -> None:
    cues: list[SfxCue] = []
    t = 0.5
    for cue in CUES:
        for variant in (1, 2, 3):
            cues.append(SfxCue(cue=cue, at=t, variant=variant, gain_db=-12))
            t += 1.4
    out = audio_work / "onsets.wav"
    FFmpegAudioMixer().mix(noise_base, cues, None, MixSpec(), out)
    mix = load_mono(out)
    sr = 48000
    pre = 0.05
    for c in cues:
        ref = load_mono(resolve_sfx(c.cue, c.variant))
        start = int((c.at - pre) * sr)
        seg = mix[start : start + len(ref) + int(2 * pre * sr)]
        corr = np.correlate(seg, ref, mode="valid")
        norm = np.sqrt(
            np.array([np.sum(seg[i : i + len(ref)] ** 2) for i in range(len(corr))])
            * np.sum(ref**2)
        )
        ncc = corr / np.maximum(norm, 1e-12)
        k = int(np.argmax(ncc))
        assert ncc[k] > 0.98, (c.cue, c.variant, ncc[k])
        onset_error_ms = (k / sr - pre) * 1000
        assert abs(onset_error_ms) <= 10.0, (c.cue, c.variant, onset_error_ms)
    # no hot spots at all
    assert measure_loudness(out).clipped_samples == 0


def test_cue_beyond_the_end_is_skipped(base_video: Path, audio_work: Path) -> None:
    out = audio_work / "tarde.wav"
    res = FFmpegAudioMixer().mix(base_video, [SfxCue(cue="pop", at=99.0)], None, MixSpec(), out)
    assert res.voice_to_sfx_db is None
    assert float(ffmpeg.probe(out)["streams"][0]["duration"]) == pytest.approx(12.0, abs=0.02)


def test_unknown_cue_and_variant_give_spanish_errors(base_video: Path, audio_work: Path) -> None:
    with pytest.raises(AudioError, match="no existe"):
        FFmpegAudioMixer().mix(
            base_video, [SfxCue(cue="trompeta", at=1.0)], None, MixSpec(), audio_work / "x.wav"
        )
    with pytest.raises(AudioError, match="variante 7"):
        FFmpegAudioMixer().mix(
            base_video,
            [SfxCue(cue="pop", at=1.0, variant=7)],
            None,
            MixSpec(),
            audio_work / "x.wav",
        )


def test_base_without_audio_is_a_clear_error(fixtures_dir: Path, audio_work: Path) -> None:
    with pytest.raises(NoAudioError, match="no tiene pista de audio"):
        FFmpegAudioMixer().mix(
            fixtures_dir / "sin_audio.mp4", BASIC_CUES, None, MixSpec(), audio_work / "n.wav"
        )


def test_stereo_base_keeps_two_channels(stereo_base: Path, audio_work: Path) -> None:
    out = audio_work / "estereo ñ.wav"
    res = FFmpegAudioMixer().mix(stereo_base, BASIC_CUES, None, MixSpec(), out)
    assert ffmpeg.probe(out)["streams"][0]["channels"] == 2
    assert res.lufs == pytest.approx(-14.0, abs=1.0)
    assert res.true_peak <= -1.0


def test_legacy_amix_fallback_matches_normalize0(base_video: Path, audio_work: Path) -> None:
    new = FFmpegAudioMixer(legacy_amix=False).mix(
        base_video, BASIC_CUES, None, MixSpec(), audio_work / "n0.wav"
    )
    old = FFmpegAudioMixer(legacy_amix=True).mix(
        base_video, BASIC_CUES, None, MixSpec(), audio_work / "old.wav"
    )
    assert old.lufs == pytest.approx(new.lufs, abs=0.2)
    a, b = load_mono(new.wav), load_mono(old.wav)
    n = min(len(a), len(b))
    assert np.max(np.abs(a[:n] - b[:n])) < 0.01


def test_music_is_looped_ducked_and_mixed(
    base_video: Path, music_wav: Path, audio_work: Path
) -> None:
    out = audio_work / "con música ñ.wav"
    music = MusicSpec(path=str(music_wav), asset_id="musica_test", gain_db=-20.0)
    res = FFmpegAudioMixer().mix(base_video, BASIC_CUES, music, MixSpec(), out)
    assert res.lufs == pytest.approx(-14.0, abs=1.0)
    assert res.true_peak <= -1.0
    assert res.clipped_samples == 0
    assert float(ffmpeg.probe(out)["streams"][0]["duration"]) == pytest.approx(12.0, abs=0.02)
    sim = check_voice(base_video, out)
    assert sim.similarity > 0.9 and abs(sim.offset_ms) <= FRAME_MS
    # the looped music must still be audible at the very end of the 12 s clip (4 s source)
    tail = load_mono(out)[int(10.2 * 48000) : int(10.8 * 48000)]
    assert 20 * np.log10(np.sqrt(np.mean(tail**2)) + 1e-9) > -60


def test_music_relative_path_uses_music_root(
    base_video: Path, music_wav: Path, audio_work: Path
) -> None:
    music = MusicSpec(path=music_wav.name, asset_id="musica_test")
    res = FFmpegAudioMixer(music_root=music_wav.parent).mix(
        base_video, [], music, MixSpec(), audio_work / "rel.wav"
    )
    assert res.lufs == pytest.approx(-14.0, abs=1.0)
    with pytest.raises(AudioError, match="No se encontró la música"):
        FFmpegAudioMixer().mix(
            base_video,
            [],
            MusicSpec(path="no/existe.mp3", asset_id="x"),
            MixSpec(),
            audio_work / "z.wav",
        )


@pytest.mark.parametrize("duck_db", [-6.0, -10.0, -14.0])
def test_ducking_depth_follows_duck_db(base_video: Path, audio_work: Path, duck_db: float) -> None:
    """Pink noise through the sidechain compressor keyed by the voice drops ~|duck_db| dB."""
    voice = decode_mono(base_video)
    noise = audio_work / "ruido rosa.wav"
    ffmpeg.run(
        [
            "-f",
            "lavfi",
            "-i",
            "anoisesrc=color=pink:a=0.3:d=12:r=48000:seed=5",
            "-c:a",
            "pcm_f32le",
            str(noise),
        ]
    )
    out = audio_work / f"duck {abs(duck_db):.0f}.wav"
    ffmpeg.run(
        [
            "-i",
            str(noise),
            "-i",
            str(base_video),
            "-filter_complex",
            f"[0:a]aformat=channel_layouts=mono[m];[m][1:a]{duck_filter(voice, duck_db)}[o]",
            "-map",
            "[o]",
            "-c:a",
            "pcm_f32le",
            str(out),
        ]
    )
    ducked, _ = read_wav(out)
    plain, _ = read_wav(noise)

    def rms_db(x: np.ndarray, a: float, b: float) -> float:
        seg = x[int(a * 48000) : int(b * 48000), 0]
        return float(20 * np.log10(np.sqrt(np.mean(seg**2))))

    for a, b in ((0.8, 2.0), (3.0, 4.8), (8.5, 10.2)):
        drop = rms_db(plain, a, b) - rms_db(ducked, a, b)
        assert drop == pytest.approx(abs(duck_db), abs=2.0), (a, b, drop)


def test_mix_for_version_writes_wav_and_json(
    fixture_project: ProjectContext, fixtures_dir: Path
) -> None:
    ctx = fixture_project
    vdir = ctx.version_dir("V1")
    vdir.mkdir(parents=True)
    shutil.copy2(fixtures_dir / "plan_fixture.yaml", vdir / "plan.yaml")
    res = mix_for_version(ctx, "V1")
    wav = vdir / "audio" / "mezcla.wav"
    meta = vdir / "audio" / "mezcla.json"
    assert wav.exists() and meta.exists()
    stored = read_model(meta, MixResult)
    assert stored.lufs == res.lufs and stored.wav == wav
    assert json.loads(meta.read_text(encoding="utf-8"))["true_peak"] <= -1.0
    assert res.lufs == pytest.approx(-14.0, abs=1.0)
    voice = check_voice(ctx.original_video(), wav)
    assert abs(voice.offset_ms) <= FRAME_MS
