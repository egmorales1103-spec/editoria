"""Sound design and mixing (owner: A4): SFX catalogue, mix, loudness and voice checks."""

from editoria.audio.density import check_sfx_density
from editoria.audio.loudness import Loudness, measure_loudness
from editoria.audio.mix import FFmpegAudioMixer, mix_for_version
from editoria.audio.sfx import CUES, SfxInfo, list_sfx, resolve_sfx
from editoria.audio.voice import check_voice
from editoria.audio.wavio import AudioError, NoAudioError

__all__ = [
    "CUES",
    "AudioError",
    "FFmpegAudioMixer",
    "Loudness",
    "NoAudioError",
    "SfxInfo",
    "check_sfx_density",
    "check_voice",
    "list_sfx",
    "measure_loudness",
    "mix_for_version",
    "resolve_sfx",
]
