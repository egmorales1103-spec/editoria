"""FFmpegRenderer: runs the filtergraph built by :mod:`editoria.render.filtergraph`."""

from __future__ import annotations

import contextlib
import os
from pathlib import Path

from editoria.render.filtergraph import RenderError, RenderGraph, build_render_graph
from editoria.render.media import probe_media, rel_to
from editoria.schemas import EditPlan, EncodeSettings, RenderInputs, fps_str
from editoria.util import ffmpeg
from editoria.util.project import DELIVERED_MARKER, VIDEO_FILE, ProjectContext

FILTERGRAPH_FILE = "filtergraph.txt"


def filtergraph_path(out: Path) -> Path:
    """`filtergraph.txt` for video.mp4; `<stem>.filtergraph.txt` for any other output."""
    name = FILTERGRAPH_FILE if out.name == VIDEO_FILE else f"{out.stem}.filtergraph.txt"
    return out.parent / name


def script_args(script_rel: str) -> list[str]:
    """`-/filter_complex <file>` (ffmpeg >= 7) or the legacy `-filter_complex_script`."""
    major, _ = ffmpeg.version()
    if major >= 7:
        return ["-/filter_complex", script_rel]
    return ["-filter_complex_script", script_rel]


def encode_args(graph: RenderGraph, enc: EncodeSettings) -> list[str]:
    args = [
        "-map", f"[{graph.video_label}]",
        "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p",
        "-preset", enc.preset, "-crf", str(enc.crf), "-r", fps_str(graph.fps),
    ]  # fmt: skip
    if graph.audio_label is not None:
        args += [
            "-map", f"[{graph.audio_label}]",
            "-c:a", "aac", "-b:a", enc.audio_bitrate, "-ar", str(enc.audio_sr),
        ]  # fmt: skip
    args += ["-movflags", "+faststart"]
    return args


class FFmpegRenderer:
    """Implements :class:`editoria.contracts.Renderer`.

    The command runs with ``cwd`` = the output folder and relative paths; the graph is
    written next to the output (``filtergraph.txt``) so every render is reproducible.
    """

    def __init__(self) -> None:
        self.warnings: list[str] = []
        self.last_graph: RenderGraph | None = None

    def render(
        self,
        plan: EditPlan,
        ctx: ProjectContext,
        inputs: RenderInputs,
        out: Path,
        enc: EncodeSettings,
    ) -> Path:
        out = Path(out).resolve()
        cwd = out.parent
        cwd.mkdir(parents=True, exist_ok=True)
        if (cwd / DELIVERED_MARKER).exists() and out.exists():
            raise RenderError(
                f"{out.name} pertenece a una versión entregada (inmutable). Creá una versión "
                "nueva con 'editoria version new'."
            )
        base_path = ctx.original_video()
        base = probe_media(base_path)
        graph = build_render_graph(plan, inputs, base, base_path, cwd, enc, face=ctx.load_face())
        self.warnings = list(graph.warnings)
        self.last_graph = graph

        script = filtergraph_path(out)
        script.write_text(graph.script, encoding="utf-8", newline="\n")
        tmp = out.with_name(f"{out.stem}.tmp{out.suffix}")
        args = [
            *graph.input_args,
            *script_args(rel_to(script, cwd)),
            *encode_args(graph, enc),
            tmp.name,
        ]
        try:
            ffmpeg.run(args, cwd=cwd)
        except ffmpeg.FFmpegError:
            with contextlib.suppress(OSError):
                tmp.unlink()
            raise
        os.replace(tmp, out)
        return out
