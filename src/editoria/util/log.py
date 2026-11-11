"""Console output (Spanish, user-facing) and JSONL logs."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rich.console import Console

console = Console(highlight=False)
err_console = Console(stderr=True, highlight=False)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"editoria.{name}")


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rec = {"ts": now_iso(), **record}
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    path = Path(path)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def info(msg: str) -> None:
    console.print(msg)


def ok(msg: str) -> None:
    console.print(f"[green]✔[/green] {msg}")


def warn(msg: str) -> None:
    err_console.print(f"[yellow]AVISO[/yellow] {msg}")


def error(msg: str) -> None:
    err_console.print(f"[red]ERROR[/red] {msg}")
