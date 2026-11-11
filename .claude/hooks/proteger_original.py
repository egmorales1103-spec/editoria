#!/usr/bin/env python3
"""PreToolUse hook: protect the original video and delivered versions (rules P01 / P20).

Blocks (exit code 2, message on stderr) any attempt by Write, Edit, MultiEdit, NotebookEdit,
Bash or PowerShell to modify:

* ``proyectos/<slug>/00_original/**``: the untouched copy of the VIDEO_BASE.
* ``proyectos/<slug>/04_versiones/Vn/**`` when that version already carries the ``.entregado``
  marker: delivered versions are immutable; changes go into a new version.

Commands that start with ``editoria`` are trusted: the CLI enforces its own rules (it is the
only thing allowed to create the original during ``init``).

The hook is defence in depth. It uses only the standard library and works on Windows, macOS
and Linux. It reads the Claude Code hook payload from stdin as JSON.
"""

from __future__ import annotations

import json
import re
import shlex
import sys
from pathlib import Path, PurePosixPath

DELIVERED_MARKER = ".entregado"
ORIGINAL_DIR = "00_original"
VERSIONS_DIR = "04_versiones"
_VERSION_RE = re.compile(r"^V\d+$")

FILE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
SHELL_TOOLS = {"Bash", "PowerShell"}

# Commands whose arguments are all treated as written/removed paths.
_MUTATING = {
    "rm",
    "rmdir",
    "del",
    "erase",
    "rd",
    "unlink",
    "shred",
    "truncate",
    "touch",
    "tee",
    "chmod",
    "chown",
    "attrib",
    "icacls",
    "mkdir",
    "md",
    "mv",
    "move",
    "ren",
    "rename",
    "remove-item",
    "move-item",
    "rename-item",
    "set-content",
    "add-content",
    "clear-content",
    "out-file",
    "new-item",
    "set-itemproperty",
    "set-acl",
    "ni",
    "sc",
    "ac",
    "ri",
    "mi",
    "rni",
}
# Commands where only the destination (last positional argument) is written.
_COPY_LIKE = {"cp", "copy", "copy-item", "xcopy", "robocopy", "install", "rsync", "cpi"}
_REDIRECT_RE = re.compile(r"(?:^|[^\w<])(?:\d?>>?|&>>?)\s*(\S+)")
_SPLIT_RE = re.compile(r"\|\||&&|;|\||\r?\n")
_EDITORIA_RE = re.compile(
    r"^(?:uv\s+run\s+(?:--\S+\s+)*)?(?:editoria(?:\.exe)?|python\d?\s+-m\s+editoria\S*)\b"
)


def _norm(text: str) -> str:
    return text.replace("\\", "/")


def _resolve(raw: str, cwd: Path) -> PurePosixPath:
    p = Path(raw.strip().strip("\"'"))
    if not p.is_absolute():
        p = cwd / p
    return PurePosixPath(_norm(str(p)))


def protected_reason(raw_path: str, cwd: Path) -> str | None:
    """Return a Spanish reason when ``raw_path`` is protected, else None."""
    if not raw_path or raw_path.startswith("-"):
        return None
    path = _resolve(raw_path, cwd)
    parts = path.parts
    for i, part in enumerate(parts):
        if part == ORIGINAL_DIR and i >= 1:
            project_dir = PurePosixPath(*parts[:i])
            is_project = (i >= 2 and parts[i - 2] == "proyectos") or (
                Path(str(project_dir), "proyecto.yaml").exists()
            )
            if is_project:
                return (
                    "Bloqueado: 00_original/ es la copia intacta del VIDEO_BASE y es de solo "
                    "lectura (regla P01). Trabajá sobre una versión en 04_versiones/ o sobre una "
                    "copia."
                )
        if (
            part == VERSIONS_DIR
            and i + 1 < len(parts)
            and _VERSION_RE.match(parts[i + 1])
            and Path(*parts[: i + 2], DELIVERED_MARKER).exists()
        ):
            return (
                f"Bloqueado: la versión {parts[i + 1]} ya fue entregada (tiene {DELIVERED_MARKER}) "
                "y es inmutable (regla P20). Creá la versión siguiente con 'editoria version new'."
            )
    return None


def _file_tool_reason(tool_input: dict, cwd: Path) -> str | None:
    for key in ("file_path", "notebook_path", "path"):
        value = tool_input.get(key)
        if isinstance(value, str):
            reason = protected_reason(value, cwd)
            if reason:
                return reason
    return None


def _tokens(segment: str) -> list[str]:
    try:
        return shlex.split(segment, posix=True)
    except ValueError:
        return segment.split()


def _segment_reason(segment: str, cwd: Path) -> str | None:
    segment = segment.strip()
    if not segment:
        return None
    # Redirections write regardless of the command.
    for match in _REDIRECT_RE.finditer(segment):
        reason = protected_reason(match.group(1), cwd)
        if reason:
            return reason
    if _EDITORIA_RE.match(segment):
        return None  # the CLI enforces its own rules
    tokens = _tokens(segment)
    if not tokens:
        return None
    name = Path(tokens[0].replace("\\", "/")).name.lower()
    name = re.sub(r"\.(exe|cmd|bat|ps1)$", "", name)
    args = [t for t in tokens[1:] if t]
    positional = [t for t in args if not t.startswith("-") or t == "-"]

    if name in _MUTATING or (name == "sed" and any(a.startswith("-i") for a in args)):
        candidates = positional
    elif name in _COPY_LIKE:
        candidates = positional[-1:]  # destination only
    elif name == "dd":
        candidates = [a.split("=", 1)[1] for a in args if a.startswith("of=")]
    elif name in {"ffmpeg", "ffmpeg.exe"}:
        candidates = positional[-1:]  # output file; inputs follow -i and are only read
        if len(tokens) >= 2 and tokens[-2] == "-i":
            candidates = []
    elif name in {"python", "python3", "py", "uv", "node", "perl", "ruby"}:
        # Inline scripts that mention a protected path and write/delete are blocked heuristically.
        joined = " ".join(args)
        writes = re.search(
            r"\b(write|unlink|remove|rmtree|rename|replace|truncate|open\([^)]*[\"']\s*[wax+])",
            joined,
        )
        if writes:
            for tok in re.findall(r"[^\s\"']+(?:00_original|04_versiones)[^\s\"']*", _norm(joined)):
                reason = protected_reason(tok, cwd)
                if reason:
                    return reason
        return None
    else:
        candidates = []
    for cand in candidates:
        reason = protected_reason(cand, cwd)
        if reason:
            return reason
    return None


def _shell_reason(command: str, cwd: Path) -> str | None:
    for segment in _SPLIT_RE.split(command):
        reason = _segment_reason(segment, cwd)
        if reason:
            return reason
    return None


def decide(payload: dict) -> str | None:
    """Return a blocking message for the hook payload, or None to allow."""
    tool = payload.get("tool_name", "")
    tool_input = payload.get("tool_input") or {}
    cwd = Path(payload.get("cwd") or ".")
    if tool in FILE_TOOLS:
        return _file_tool_reason(tool_input, cwd)
    if tool in SHELL_TOOLS:
        command = tool_input.get("command")
        if isinstance(command, str):
            return _shell_reason(command, cwd)
    return None


def main() -> int:
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    try:
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    except (json.JSONDecodeError, ValueError):
        return 0  # not a payload we understand: never break the session
    reason = decide(payload)
    if reason:
        print(reason, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
