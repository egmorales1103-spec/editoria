#!/usr/bin/env python3
"""Download the external assets listed in ``assets/externos.yaml`` and verify their sha256.

What it fetches (fixed URLs only, nothing else is ever downloaded):

* ``E01``..``E06``: animated Google Noto Emoji GIFs (CC BY 4.0) from ``fonts.gstatic.com``,
  saved as ``assets/emoji/<id>.gif``.
* ``font/Inter``: the Inter typeface (SIL OFL 1.1) from its official GitHub release; the static
  TrueType files are extracted to ``assets/fonts/Inter/``.

Downloaded files are git-ignored (``assets/emoji/`` and ``assets/fonts/``); only the manifest
``assets/externos.yaml`` (licence, URL, author, sha256, attribution) is versioned.

Usage::

    uv run python scripts/fetch_assets.py              # download what is missing and verify
    uv run python scripts/fetch_assets.py --check      # verify only, never download
    uv run python scripts/fetch_assets.py --record     # maintainers: write sha256 into the manifest

``--record`` is meant to be run once when the manifest is created or an asset is updated, and
the resulting diff reviewed. Without it, a manifest entry with an empty sha256 is an error:
nothing unverified is accepted.

Exit code 0 when every asset is present and verified, 1 otherwise. Output is in Spanish.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import shutil
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = REPO_ROOT / "assets" / "externos.yaml"
USER_AGENT = "editoria-fetch-assets/0.1 (+https://github.com/)"
TIMEOUT_S = 120

# Hosts the script is allowed to talk to. Anything else in the manifest is refused.
ALLOWED_HOSTS = {"fonts.gstatic.com", "github.com", "objects.githubusercontent.com"}

# Members extracted from the Inter release archive (static TrueType files + licence).
INTER_ZIP_MEMBERS = {
    "extras/ttf/Inter-Regular.ttf": "Inter-Regular.ttf",
    "extras/ttf/Inter-Medium.ttf": "Inter-Medium.ttf",
    "extras/ttf/Inter-SemiBold.ttf": "Inter-SemiBold.ttf",
    "extras/ttf/Inter-Bold.ttf": "Inter-Bold.ttf",
    "extras/ttf/Inter-ExtraBold.ttf": "Inter-ExtraBold.ttf",
    "extras/ttf/Inter-Black.ttf": "Inter-Black.ttf",
    "LICENSE.txt": "OFL.txt",
}
VERIFIED_MARKER = ".verified"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str) -> bytes:
    host = url.split("/")[2] if "//" in url else ""
    if not url.startswith("https://") or host not in ALLOWED_HOSTS:
        raise ValueError(f"URL no permitida: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:  # noqa: S310
        return bytes(resp.read())


def load_manifest(path: Path = MANIFEST) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def save_sha256s(path: Path, shas: dict[str, str]) -> None:
    """Rewrite ``sha256:`` lines in place, keeping comments and layout."""
    lines = path.read_text(encoding="utf-8").splitlines()
    current: str | None = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("- id:"):
            current = stripped.split(":", 1)[1].strip().strip("\"'")
        elif stripped.startswith("sha256:") and current in shas:
            indent = line[: len(line) - len(line.lstrip())]
            lines[i] = f'{indent}sha256: "{shas[current]}"'
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def _is_zip(entry: dict) -> bool:
    return str(entry.get("source_url", "")).lower().endswith(".zip")


def _target(entry: dict) -> Path:
    return REPO_ROOT / entry["path"]


def is_present(entry: dict) -> bool:
    target = _target(entry)
    if _is_zip(entry):
        marker = target / VERIFIED_MARKER
        return (
            marker.exists()
            and marker.read_text(encoding="utf-8").strip() == entry.get("sha256", "")
            and all((target / name).exists() for name in INTER_ZIP_MEMBERS.values())
        )
    return target.exists() and sha256_file(target) == entry.get("sha256", "")


def install(entry: dict, data: bytes) -> None:
    target = _target(entry)
    if _is_zip(entry):
        shutil.rmtree(target, ignore_errors=True)
        target.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = set(zf.namelist())
            for member, out_name in INTER_ZIP_MEMBERS.items():
                if member not in names:
                    raise ValueError(f"El archivo descargado no contiene {member}.")
                (target / out_name).write_bytes(zf.read(member))
        (target / VERIFIED_MARKER).write_text(entry["sha256"] + "\n", encoding="utf-8")
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="solo verifica; no descarga")
    ap.add_argument(
        "--record", action="store_true", help="(mantenedores) registra los sha256 en el manifest"
    )
    ap.add_argument("--manifest", type=Path, default=MANIFEST)
    args = ap.parse_args(argv)

    entries = load_manifest(args.manifest).get("assets", [])
    problems = 0
    recorded: dict[str, str] = {}

    for entry in entries:
        asset_id = entry["id"]
        expected = entry.get("sha256", "")
        if not args.record and not expected:
            print(
                f"[ERROR] {asset_id}: el manifest no tiene sha256 (no se acepta nada sin verificar)."
            )
            problems += 1
            continue
        if not args.record and is_present(entry):
            print(f"[OK]    {asset_id}: ya está y coincide con el sha256.")
            continue
        if args.check:
            print(f"[FALTA] {asset_id}: ejecutá 'uv run python scripts/fetch_assets.py'.")
            problems += 1
            continue
        try:
            print(f"[....]  {asset_id}: descargando {entry['source_url']}")
            data = download(entry["source_url"])
        except (urllib.error.URLError, OSError, ValueError) as exc:
            print(f"[ERROR] {asset_id}: no se pudo descargar ({exc}).")
            problems += 1
            continue
        digest = sha256_bytes(data)
        if args.record:
            recorded[asset_id] = digest
            entry["sha256"] = digest
        elif digest != expected:
            print(
                f"[ERROR] {asset_id}: el sha256 no coincide (esperado {expected[:12]}…, "
                f"recibido {digest[:12]}…). No se guardó el archivo."
            )
            problems += 1
            continue
        try:
            install(entry, data)
        except (ValueError, zipfile.BadZipFile, OSError) as exc:
            print(f"[ERROR] {asset_id}: no se pudo instalar ({exc}).")
            problems += 1
            continue
        print(f"[OK]    {asset_id}: guardado en {entry['path']} (sha256 {digest[:12]}…).")

    if args.record and recorded:
        save_sha256s(args.manifest, recorded)
        print(f"Se registraron {len(recorded)} sha256 en {args.manifest.name}.")

    if problems:
        print(
            f"Hay {problems} problema(s). Los assets faltantes se reemplazan por los del sistema."
        )
        return 1
    print("Assets externos verificados. Recordá incluir la atribución (ver THIRD_PARTY.md).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
