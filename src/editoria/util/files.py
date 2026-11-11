"""File helpers: hashing, read-only flags, CSV with exact columns."""

from __future__ import annotations

import csv
import hashlib
import os
import stat
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path


def sha256_file(path: Path | str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        while block := fh.read(chunk):
            h.update(block)
    return h.hexdigest()


def make_read_only(path: Path | str) -> None:
    p = Path(path)
    mode = p.stat().st_mode
    os.chmod(p, mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))


def make_writable(path: Path | str) -> None:
    p = Path(path)
    os.chmod(p, p.stat().st_mode | stat.S_IWUSR)


def is_read_only(path: Path | str) -> bool:
    return not os.access(Path(path), os.W_OK)


def read_csv_rows(path: Path | str) -> list[dict[str, str]]:
    p = Path(path)
    if not p.exists():
        return []
    with p.open(encoding="utf-8-sig", newline="") as fh:
        return [dict(r) for r in csv.DictReader(fh)]


def write_csv_rows(
    path: Path | str, columns: Sequence[str], rows: Iterable[Mapping[str, object]]
) -> Path:
    """Write CSV (UTF-8, LF) with exactly ``columns`` in that order; extra keys are an error."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(columns), extrasaction="raise", lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if v is None else v) for k, v in r.items()})
    return p


def fmt_ts(seconds: float) -> str:
    """mm:ss.cc for human-facing tables (e.g. 01:02.50)."""
    seconds = max(seconds, 0.0)
    m, s = divmod(seconds, 60)
    return f"{int(m):02d}:{s:05.2f}"
