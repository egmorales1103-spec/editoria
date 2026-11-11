"""Generate synthetic test fixtures into tests/.fixtures (gitignored).

Everything is synthetic (testsrc2, tones): no third-party media. Idempotent: a stamp file
records the generator version; bump FIXTURES_VERSION to force regeneration.

Usage:  uv run python scripts/make_fixtures.py [--force] [--out DIR]
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from editoria.schemas import (  # noqa: E402
    AudioInfo,
    Box,
    CaptionsSpec,
    EditPlan,
    Emphasis,
    FaceSample,
    FaceTrack,
    GraphicItem,
    ProbeResult,
    Segment,
    SegmentList,
    SfxCue,
    Transcript,
    TranscriptSegment,
    VideoInterval,
    Word,
    write_model,
)
from editoria.util import ffmpeg  # noqa: E402

FIXTURES_VERSION = "2"
DEFAULT_OUT = ROOT / "tests" / ".fixtures"

DURATION = 12.0
FPS = 30
# Hard cuts of the main fixture (seconds). One mid-phrase, one inside a pause.
CUTS = (4.0, 7.85)
# Speech-like bursts (phrases) and their words. Pauses between phrases are >= 0.4 s.
PHRASES: list[tuple[float, float, str]] = [
    (0.30, 2.20, "Hoy te muestro cómo automatizar"),
    (2.60, 5.00, "las tareas repetitivas de tu equipo"),
    (5.50, 7.60, "con inteligencia artificial y procesos claros"),
    (8.10, 10.40, "para que tu empresa trabaje mejor cada semana"),
    (10.80, 11.70, "Probalo hoy"),
]
FLAGGED_WORD = "repetitivas"  # low probability -> flagged for review (P23)
FACE_BOX = Box(x=340, y=380, w=400, h=480)  # source px on 1080x1920


# ---------------------------------------------------------------------------------------
def _gate_expr() -> str:
    return "+".join(f"between(t,{a:.2f},{b:.2f})" for a, b, _ in PHRASES)


def _speech_expr() -> str:
    # Voiced harmonics with ~5 Hz syllabic modulation, gated by phrases.
    voice = (
        "(sin(2*PI*150*t)+0.5*sin(2*PI*300*t)+0.35*sin(2*PI*450*t)"
        "+0.2*sin(2*PI*900*t)+0.1*sin(2*PI*1800*t))"
    )
    syll = "(0.55+0.45*sin(2*PI*5*t))"
    return f"0.18*{voice}*{syll}*({_gate_expr()})"


def _measure_lufs(path: Path) -> float:
    proc = ffmpeg.run(
        ["-i", path, "-af", "loudnorm=print_format=json", "-f", "null", "-"], check=True
    )
    blob = proc.stderr[proc.stderr.rindex("{") : proc.stderr.rindex("}") + 1]
    return float(json.loads(blob)["input_i"])


def make_speech_wav(out: Path, duration: float = DURATION, target_lufs: float = -20.0) -> None:
    raw = out.with_name(out.stem + "_raw.wav")
    ffmpeg.run(
        [
            "-f", "lavfi",
            "-i", f"aevalsrc=exprs='{_speech_expr()}':s=48000:d={duration}",
            "-ac", "1", "-c:a", "pcm_s16le", raw,
        ]
    )  # fmt: skip
    gain = target_lufs - _measure_lufs(raw)
    ffmpeg.run(["-i", raw, "-af", f"volume={gain:.2f}dB", "-c:a", "pcm_s16le", out])
    raw.unlink()


def make_base(out: Path, w: int, h: int, fps: int, duration: float, wav: Path | None) -> None:
    """testsrc2 in three shots separated by hard cuts (colour/content changes)."""
    a, b = CUTS if duration >= 8.5 else (duration / 3, 2 * duration / 3)
    v = (
        f"testsrc2=s={w}x{h}:r={fps}:d={duration},format=yuv420p,split=3[s0][s1][s2];"
        f"[s0]trim=0:{a},setpts=PTS-STARTPTS[v0];"
        f"[s1]trim={a}:{b},setpts=PTS-STARTPTS,hue=h=120:s=1.4,negate[v1];"
        f"[s2]trim={b}:{duration},setpts=PTS-STARTPTS,hue=h=240[v2];"
        f"[v0][v1][v2]concat=n=3:v=1:a=0,format=yuv420p[v]"
    )
    args: list[str | Path] = []
    if wav is not None:
        args += ["-i", wav]
    args += ["-filter_complex", v, "-map", "[v]"]
    if wav is not None:
        args += ["-map", "0:a", "-c:a", "aac", "-b:a", "192k", "-ar", "48000"]
    args += [
        "-t", str(duration), "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-pix_fmt", "yuv420p", "-r", str(fps), "-movflags", "+faststart", out,
    ]  # fmt: skip
    ffmpeg.run(args)


def make_generated(base: Path, out: Path, start: float, end: float, bad: bool) -> None:
    """Candidate 'generated' shot of [start,end]: ok = same + light noise; bad = drifted bg."""
    if bad:
        vf = (
            "hue=h=60:s=2,eq=brightness=0.08,"
            "drawbox=x=0:y=1200:w=1080:h=720:color=0x3355AA@1:t=fill,"
            "drawgrid=w=90:h=90:t=3:c=white@0.6"
        )
    else:
        vf = "noise=alls=6:allf=t"
    ffmpeg.run(
        [
            "-ss", f"{start}", "-to", f"{end}", "-i", base, "-vf", vf,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", out,
        ]
    )  # fmt: skip


def make_transcript() -> Transcript:
    words: list[Word] = []
    segments: list[TranscriptSegment] = []
    for a, b, text in PHRASES:
        toks = text.split()
        step = (b - a) / len(toks)
        first = len(words)
        for i, tok in enumerate(toks):
            ws = round(a + i * step, 3)
            we = round(a + (i + 1) * step - 0.04, 3)
            flagged = tok == FLAGGED_WORD
            words.append(
                Word(text=tok, start=ws, end=we, prob=0.45 if flagged else 0.93, flagged=flagged)
            )
        segments.append(
            TranscriptSegment(start=a, end=b, text=text, first_word=first, last_word=len(words) - 1)
        )
    return Transcript(language="es", model="fixture", words=words, segments=segments)


def make_face_track() -> FaceTrack:
    samples = [
        FaceSample(t=round(i * 0.5, 2), box=FACE_BOX) for i in range(int(DURATION / 0.5) + 1)
    ]
    return FaceTrack(
        frame_w=1080, frame_h=1920, samples=samples, union_box=FACE_BOX, estimated=False
    )


def make_segments() -> SegmentList:
    roles = ["hook", "body", "body", "example", "closing"]
    return SegmentList(
        segments=[
            Segment(id=f"s{i + 1:02d}", start=a, end=b, text=t, role=roles[i])  # type: ignore[arg-type]
            for i, (a, b, t) in enumerate(PHRASES)
        ]
    )


def make_probe(path: Path) -> ProbeResult:
    data = ffmpeg.probe(path)
    v = next(s for s in data["streams"] if s["codec_type"] == "video")
    a = next((s for s in data["streams"] if s["codec_type"] == "audio"), None)
    return ProbeResult(
        duration_s=float(data["format"]["duration"]),
        width=int(v["width"]),
        height=int(v["height"]),
        fps=v["r_frame_rate"],
        vfr=False,
        rotation=0,
        has_audio=a is not None,
        audio=AudioInfo(codec=a["codec_name"], sr=int(a["sample_rate"]), ch=int(a["channels"]))
        if a
        else None,
        video_codec=v["codec_name"],
        pix_fmt=v["pix_fmt"],
        nb_frames=int(v.get("nb_frames", 0)) or None,
    )


ASS_FIXTURE = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: A,Arial,64,&H00FFFFFF,&H0000D4FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,3,1,2,60,140,560,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.30,0:00:02.16,A,,0,0,0,,Hoy te muestro cómo {\\c&H0000D4FF&}automatizar{\\c}
Dialogue: 0,0:00:02.60,0:00:04.96,A,,0,0,0,,las tareas repetitivas\\Nde tu equipo
Dialogue: 0,0:00:05.50,0:00:07.56,A,,0,0,0,,con inteligencia artificial\\Ny procesos claros
Dialogue: 0,0:00:08.10,0:00:10.36,A,,0,0,0,,para que tu empresa\\Ntrabaje mejor cada semana
Dialogue: 0,0:00:10.80,0:00:11.66,A,,0,0,0,,Probalo hoy
"""


def make_overlay_sequence(out_dir: Path, fps: int = FPS, seconds: float = 1.5) -> None:
    """RGBA PNG sequence 600x200: transparent background, yellow card, growing black bar."""
    from PIL import Image, ImageDraw

    out_dir.mkdir(parents=True, exist_ok=True)
    n = round(fps * seconds)
    for i in range(n):
        im = Image.new("RGBA", (600, 200), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle((20, 20, 580, 180), radius=24, fill=(255, 212, 0, 242))
        d.rectangle((40, 80, 40 + int(500 * (i + 1) / n), 120), fill=(0, 0, 0, 255))
        im.save(out_dir / f"{i + 1:05d}.png")


def make_emoji_gif(out: Path) -> None:
    ffmpeg.run(
        [
            "-f", "lavfi", "-i", "testsrc=s=128x128:r=15:d=1",
            "-vf", "split[a][b];[a]palettegen=max_colors=32[p];[b][p]paletteuse",
            "-loop", "0", out,
        ]
    )  # fmt: skip


def make_plan() -> EditPlan:
    return EditPlan(
        version="V1",
        style="A",
        brand="master-solution",
        video=[
            VideoInterval(id="v01", in_=0.0, out=2.4, method="original"),
            VideoInterval(
                id="v02", in_=2.4, out=4.0, method="reframe", zoom=1.15, anchor="face", motion="cut"
            ),
            VideoInterval(id="v03", in_=4.0, out=12.0, method="original"),
        ],
        captions=CaptionsSpec(style="A", emphasis=[Emphasis(word=4), Emphasis(word=17)]),
        graphics=[
            GraphicItem(
                id="g01",
                template="palabra_clave",
                in_=0.3,
                out=1.8,
                zone="upper",
                params={"texto": "Automatizá"},
            ),
            GraphicItem(id="e01", emoji="E01", in_=6.2, out=7.4, zone="upper_right"),
        ],
        sfx=[
            SfxCue(cue="pop", at=0.3, gain_db=-14, ref="g01"),
            SfxCue(cue="whoosh", at=2.38, gain_db=-16, ref="v02"),
        ],
        notes="Plan de fixture: usa reencuadre, gráfico, emoji y SFX.",
    )


# ---------------------------------------------------------------------------------------
def ensure_fixtures(out: Path = DEFAULT_OUT, force: bool = False) -> Path:
    stamp = out / ".stamp"
    if not force and stamp.exists() and stamp.read_text().strip() == FIXTURES_VERSION:
        return out
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    speech = out / "speech_12s.wav"
    make_speech_wav(speech)
    base = out / "base_1080x1920_30.mp4"
    make_base(base, 1080, 1920, 30, DURATION, speech)

    lowres_wav = out / "speech_6s.wav"
    make_speech_wav(lowres_wav, duration=6.0)
    make_base(out / "base_720x1280_25.mp4", 720, 1280, 25, 6.0, lowres_wav)
    make_base(out / "base_1920x1080.mp4", 1920, 1080, 30, 6.0, lowres_wav)
    make_base(out / "sin_audio.mp4", 1080, 1920, 30, 4.0, None)

    spaced = out / "carpeta con espacios"
    spaced.mkdir()
    shutil.copy2(base, spaced / "edición ñ.mp4")

    make_generated(base, out / "generada_ok.mp4", 8.5, 10.5, bad=False)
    make_generated(base, out / "generada_mala.mp4", 8.5, 10.5, bad=True)

    write_model(out / "transcript_fixture.json", make_transcript())
    write_model(out / "rostro_fixture.json", make_face_track())
    write_model(out / "segmentos_fixture.json", make_segments())
    write_model(out / "probe_fixture.json", make_probe(base))

    (out / "captions_fixture.ass").write_text(ASS_FIXTURE, encoding="utf-8", newline="\n")
    make_overlay_sequence(out / "overlay_fixture")
    ffmpeg.run(
        [
            "-i",
            base,
            "-vn",
            "-ac",
            "1",
            "-ar",
            "48000",
            "-c:a",
            "pcm_s16le",
            out / "mix_fixture.wav",
        ]
    )
    make_emoji_gif(out / "emoji_fixture.gif")
    write_model(out / "plan_fixture.yaml", make_plan())

    for tmp in (speech, lowres_wav):
        tmp.unlink()
    stamp.write_text(FIXTURES_VERSION)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ns = ap.parse_args()
    out = ensure_fixtures(ns.out, force=ns.force)
    files = [p for p in sorted(out.rglob("*")) if p.is_file()]
    for p in files:
        if p.suffix != ".png":
            print(p.relative_to(out))
    print(f"{len(files)} archivos en {out}")


if __name__ == "__main__":
    main()
