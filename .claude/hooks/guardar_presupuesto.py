#!/usr/bin/env python3
"""PreToolUse hook: no paid generation without an authorised budget (rule P09).

Blocks (exit code 2, message on stderr) a Bash or PowerShell command that runs
``editoria shots api submit <slug> ...`` unless ``proyectos/<slug>/proyecto.yaml`` declares a
positive ``budget.limit`` that has not been used up. The CLI applies the same guard; this hook is
defence in depth so an agent cannot spend credits by mistake.

Fail-closed: if the slug or the project file cannot be found, the command is blocked.

Standard library only; PyYAML is used when available, otherwise a small line parser is used.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
from pathlib import Path

SHELL_TOOLS = {"Bash", "PowerShell"}
_SUBMIT_RE = re.compile(r"\bshots\s+api\s+submit\b")


def _read_budget(config_path: Path) -> tuple[float | None, float]:
    """Return ``(limit, spent)`` from proyecto.yaml. ``limit`` is None when absent or null."""
    text = config_path.read_text(encoding="utf-8")
    try:
        import yaml

        data = yaml.safe_load(text) or {}
        budget = data.get("budget") or {}
        limit = budget.get("limit")
        return (None if limit is None else float(limit)), float(budget.get("spent") or 0.0)
    except ImportError:
        pass
    limit_val: float | None = None
    spent_val = 0.0
    in_budget = False
    for line in text.splitlines():
        if re.match(r"^budget\s*:", line):
            in_budget = True
            continue
        if in_budget and re.match(r"^\S", line):
            in_budget = False
        if in_budget:
            m = re.match(r"^\s+(limit|spent)\s*:\s*([^\s#]*)", line)
            if not m:
                continue
            raw = m.group(2).strip("\"'")
            if raw in {"", "~", "null", "Null", "NULL"}:
                value: float | None = None
            else:
                try:
                    value = float(raw)
                except ValueError:
                    value = None
            if m.group(1) == "limit":
                limit_val = value
            else:
                spent_val = value or 0.0
    return limit_val, spent_val


def _projects_dir(tokens: list[str], cwd: Path) -> Path:
    for i, tok in enumerate(tokens):
        if tok == "--proyectos" and i + 1 < len(tokens):
            return _abs(tokens[i + 1], cwd)
        if tok.startswith("--proyectos="):
            return _abs(tok.split("=", 1)[1], cwd)
    env = os.environ.get("EDITORIA_PROJECTS")
    return _abs(env, cwd) if env else cwd / "proyectos"


def _abs(raw: str, cwd: Path) -> Path:
    p = Path(raw.strip("\"'"))
    return p if p.is_absolute() else cwd / p


def _submit_slug(tokens: list[str]) -> str | None:
    """First positional token after ``submit`` (the project slug)."""
    for i in range(len(tokens) - 2):
        if tokens[i : i + 3] == ["shots", "api", "submit"]:
            for tok in tokens[i + 3 :]:
                if not tok.startswith("-"):
                    return tok
            return None
    return None


def _segment_reason(segment: str, cwd: Path) -> str | None:
    if not _SUBMIT_RE.search(segment):
        return None
    segment = segment.replace("\\", "/")  # Windows paths: keep backslashes out of shlex
    try:
        tokens = shlex.split(segment, posix=True)
    except ValueError:
        tokens = segment.split()
    slug = _submit_slug(tokens)
    if slug is None:
        return (
            "Bloqueado: no pude identificar el proyecto de 'shots api submit'. Indicá el slug "
            "para que se pueda verificar el presupuesto autorizado (regla P09)."
        )
    config = _projects_dir(tokens, cwd) / slug / "proyecto.yaml"
    if not config.exists():
        return (
            f"Bloqueado: no encuentro {config}. Sin proyecto.yaml no hay presupuesto autorizado "
            "y no se envía nada a la API (regla P09)."
        )
    try:
        limit, spent = _read_budget(config)
    except Exception:  # unreadable or malformed file: fail closed
        return f"Bloqueado: no pude leer el presupuesto de {config} (regla P09)."
    if limit is None or limit <= 0:
        return (
            "Bloqueado: proyecto.yaml no tiene budget.limit. Nunca se gastan créditos sin un "
            "límite autorizado por la persona dueña del proyecto (regla P09). Pedile solo ese dato."
        )
    if spent >= limit:
        return (
            f"Bloqueado: el presupuesto autorizado ({limit:g}) ya está agotado "
            f"(gastado {spent:g}). "
            "No se compran créditos ni se amplía el límite sin autorización expresa (regla P09)."
        )
    return None


def _split_commands(command: str) -> list[str]:
    """Split a command line on ``;``, ``|``, ``&&``, ``||`` and newlines, outside quotes."""
    parts: list[str] = []
    buf: list[str] = []
    quote: str | None = None
    i = 0
    while i < len(command):
        ch = command[i]
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
            buf.append(ch)
        elif ch in (";", "|", "\r", "\n") or command.startswith("&&", i):
            parts.append("".join(buf))
            buf = []
            if command.startswith(("&&", "||"), i):
                i += 1
        else:
            buf.append(ch)
        i += 1
    parts.append("".join(buf))
    return parts


def decide(payload: dict) -> str | None:
    """Return a blocking message for the hook payload, or None to allow."""
    if payload.get("tool_name") not in SHELL_TOOLS:
        return None
    command = (payload.get("tool_input") or {}).get("command")
    if not isinstance(command, str):
        return None
    cwd = Path(payload.get("cwd") or ".")
    for segment in _split_commands(command):
        reason = _segment_reason(segment, cwd)
        if reason:
            return reason
    return None


def main() -> int:
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    try:
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    except (json.JSONDecodeError, ValueError):
        return 0
    reason = decide(payload)
    if reason:
        print(reason, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
