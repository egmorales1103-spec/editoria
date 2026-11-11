"""The ONLY entry point to ffmpeg/ffprobe. Every module must go through run()/probe().

Windows rules (spaces, accents): arguments are passed as a list (no shell); callers that
build filtergraphs referencing files should set ``cwd`` to the folder that contains them and
use relative paths, or escape with :func:`escape_filter_path`.
"""

from __future__ import annotations

import contextvars
import json
import re
import shutil
import subprocess
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from editoria.util.log import append_jsonl

Tool = Literal["ffmpeg", "ffprobe"]

_command_log: contextvars.ContextVar[Path | None] = contextvars.ContextVar(
    "editoria_command_log", default=None
)


class FFmpegError(RuntimeError):
    def __init__(self, cmd: Sequence[str], returncode: int, stderr: str) -> None:
        self.cmd = list(cmd)
        self.returncode = returncode
        self.stderr = stderr
        tail = "\n".join(stderr.strip().splitlines()[-15:])
        super().__init__(f"{Path(cmd[0]).stem} terminó con código {returncode}:\n{tail}")


class FFmpegNotFound(RuntimeError):
    pass


def set_command_log(path: Path | None) -> contextvars.Token[Path | None]:
    """Route subsequent run() calls to ``path`` (usually ProjectContext.commands_log)."""
    return _command_log.set(path)


@contextmanager
def command_log(path: Path | None) -> Iterator[None]:
    token = _command_log.set(path)
    try:
        yield
    finally:
        _command_log.reset(token)


@lru_cache(maxsize=4)
def executable(tool: Tool = "ffmpeg") -> str:
    exe = shutil.which(tool)
    if not exe:
        raise FFmpegNotFound(
            f"No se encontró '{tool}' en el PATH. "
            "Ejecutá 'editoria doctor' para ver cómo instalarlo."
        )
    return exe


def run(
    args: Sequence[str | Path],
    *,
    tool: Tool = "ffmpeg",
    cwd: Path | str | None = None,
    log_path: Path | None = None,
    check: bool = True,
    timeout: float | None = None,
    overwrite: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run ffmpeg/ffprobe with ``args`` (without the executable).

    For ffmpeg, ``-hide_banner -nostdin`` (and ``-y`` when ``overwrite``) are prepended.
    The call is appended to ``log_path`` or to the context command log (logs/comandos.jsonl).
    """
    exe = executable(tool)
    pre: list[str] = ["-hide_banner"]
    if tool == "ffmpeg":
        pre.append("-nostdin")
        if overwrite:
            pre.append("-y")
    cmd = [exe, *pre, *(str(a) for a in args)]
    t0 = time.perf_counter()
    proc = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd is not None else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    target = log_path or _command_log.get()
    if target is not None:
        append_jsonl(
            target,
            {
                "tool": tool,
                "args": [str(a) for a in args],
                "cwd": str(cwd) if cwd is not None else None,
                "returncode": proc.returncode,
                "duration_s": round(time.perf_counter() - t0, 3),
            },
        )
    if check and proc.returncode != 0:
        raise FFmpegError(cmd, proc.returncode, proc.stderr)
    return proc


def probe(path: Path | str, *, cwd: Path | str | None = None) -> dict[str, Any]:
    """ffprobe JSON (format + streams) for ``path``."""
    proc = run(
        ["-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        tool="ffprobe",
        cwd=cwd,
    )
    data: dict[str, Any] = json.loads(proc.stdout or "{}")
    return data


_VERSION_RE = re.compile(r"version\s+n?(\d+)\.(\d+)")


@lru_cache(maxsize=1)
def version() -> tuple[int, int]:
    """(major, minor) of ffmpeg. Git snapshots ('N-12345-g...') return (999, 0)."""
    out = run(["-version"], check=True).stdout
    m = _VERSION_RE.search(out)
    if m:
        return int(m.group(1)), int(m.group(2))
    if re.search(r"version\s+N-\d+", out):
        return 999, 0
    return 0, 0


@lru_cache(maxsize=1)
def _filters() -> frozenset[str]:
    out = run(["-filters"], check=True).stdout
    names = set()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 3 and re.fullmatch(r"[A-Z.|]{2,4}", parts[0]):
            names.add(parts[1])
    return frozenset(names)


def has_filter(name: str) -> bool:
    return name in _filters()


def escape_filter_path(path: Path | str) -> str:
    """Escape a path for use as a filter option value inside a filtergraph.

    Prefer relative paths with ``cwd``; this handles drive letters, quotes and spaces.
    """
    s = str(path).replace("\\", "/")
    s = s.replace("'", r"'\\\''")
    s = s.replace(":", r"\:")
    return f"'{s}'"


def media_duration(path: Path | str, *, cwd: Path | str | None = None) -> float:
    data = probe(path, cwd=cwd)
    return float(data.get("format", {}).get("duration", 0.0))
