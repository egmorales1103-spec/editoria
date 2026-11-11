"""`editoria doctor`: environment checks (owner: A1).

``run_checks()`` returns a list of :class:`Check`; ``has_blocking_failures()`` tells whether
anything the pipeline cannot work without is missing. Warnings (e.g. no cached whisper model)
never block.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import typer
from rich.table import Table

from editoria.util import ffmpeg
from editoria.util.log import console
from editoria.util.project import projects_dir

Status = Literal["OK", "FALTA", "AVISO"]

MIN_FFMPEG_MAJOR = 6
REQUIRED_FILTERS = (
    "subtitles",
    "ass",
    "loudnorm",
    "ebur128",
    "sidechaincompress",
    "blackdetect",
    "freezedetect",
    "silencedetect",
    "ssim",
    "overlay",
    "scdet",
    "zoompan",
)
MIN_FREE_GB_BLOCKING = 1.0
MIN_FREE_GB_WARN = 5.0
WHISPER_MODELS = ("large-v3-turbo", "small")

FFMPEG_FIX = (
    "Windows: winget install Gyan.FFmpeg | macOS: brew install ffmpeg | "
    "Linux: sudo apt install ffmpeg"
)
LIBASS_FIX = (
    "Windows: winget install Gyan.FFmpeg (build full) | macOS: brew install ffmpeg | "
    "Linux: sudo apt install ffmpeg libass9"
)
CHROMIUM_FIX = "Todos los sistemas: uv run playwright install chromium"
EXTRAS_FIX = "Todos los sistemas: uv sync --all-extras"


@dataclass(frozen=True)
class Check:
    name: str
    status: Status
    detail: str = ""
    fix: str = ""
    blocking: bool = True  # only meaningful when status == "FALTA"

    @property
    def ok(self) -> bool:
        return self.status == "OK"


def has_blocking_failures(checks: list[Check]) -> bool:
    return any(c.status == "FALTA" and c.blocking for c in checks)


# ---------------------------------------------------------------------------------------
def _check_ffmpeg() -> list[Check]:
    out: list[Check] = []
    for tool in ("ffmpeg", "ffprobe"):
        try:
            path = ffmpeg.executable(tool)
        except ffmpeg.FFmpegNotFound:
            out.append(Check(tool, "FALTA", "No está en el PATH.", FFMPEG_FIX))
        else:
            out.append(Check(tool, "OK", path))
    if out[0].status != "OK":
        return out
    try:
        major, minor = ffmpeg.version()
    except Exception as exc:
        out.append(Check("ffmpeg ≥ 6", "FALTA", f"No se pudo ejecutar: {exc}", FFMPEG_FIX))
        return out
    if (major, minor) == (0, 0):
        out.append(
            Check("ffmpeg ≥ 6", "AVISO", "No se pudo leer la versión.", FFMPEG_FIX, blocking=False)
        )
    elif major < MIN_FFMPEG_MAJOR:
        out.append(
            Check("ffmpeg ≥ 6", "FALTA", f"Versión {major}.{minor}: demasiado antigua.", FFMPEG_FIX)
        )
    else:
        detail = "versión de desarrollo" if major == 999 else f"{major}.{minor}"
        out.append(Check("ffmpeg ≥ 6", "OK", detail))
    return out


def _check_filters() -> list[Check]:
    out: list[Check] = []
    for name in REQUIRED_FILTERS:
        try:
            present = ffmpeg.has_filter(name)
        except Exception:
            present = False
        if present:
            out.append(Check(f"filtro {name}", "OK"))
        else:
            out.append(Check(f"filtro {name}", "FALTA", "No disponible.", FFMPEG_FIX))
    return out


def _check_libass() -> Check:
    try:
        config = ffmpeg.run(["-version"], check=False).stdout
        has_flag = "--enable-libass" in config
        has_filter = ffmpeg.has_filter("subtitles") and ffmpeg.has_filter("ass")
    except Exception:
        return Check("libass", "FALTA", "No se pudo consultar ffmpeg.", LIBASS_FIX)
    if has_flag or has_filter:
        return Check("libass", "OK", "ffmpeg compilado con libass")
    return Check(
        "libass", "FALTA", "ffmpeg sin libass: no se pueden quemar subtítulos.", LIBASS_FIX
    )


def playwright_cache_dirs() -> list[Path]:
    env = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if env and env != "0":
        return [Path(env)]
    home = Path.home()
    local = os.environ.get("LOCALAPPDATA")
    return [
        Path(local) / "ms-playwright" if local else home / "AppData" / "Local" / "ms-playwright",
        home / "Library" / "Caches" / "ms-playwright",
        home / ".cache" / "ms-playwright",
    ]


def _check_playwright() -> list[Check]:
    if importlib.util.find_spec("playwright") is None:
        return [
            Check("Playwright (paquete)", "FALTA", "No está instalado.", EXTRAS_FIX),
            Check("Chromium de Playwright", "FALTA", "Requiere el paquete.", CHROMIUM_FIX),
        ]
    found = [
        d
        for root in playwright_cache_dirs()
        if root.is_dir()
        for d in root.glob("chromium*-*")
        if d.is_dir()
    ]
    if found:
        chromium = Check("Chromium de Playwright", "OK", found[0].name)
    else:
        chromium = Check("Chromium de Playwright", "FALTA", "No está descargado.", CHROMIUM_FIX)
    return [Check("Playwright (paquete)", "OK"), chromium]


def hf_cache_dirs() -> list[Path]:
    if os.environ.get("HF_HUB_CACHE"):
        return [Path(os.environ["HF_HUB_CACHE"])]
    if os.environ.get("HF_HOME"):
        return [Path(os.environ["HF_HOME"]) / "hub"]
    return [Path.home() / ".cache" / "huggingface" / "hub"]


def _check_whisper() -> list[Check]:
    out: list[Check] = []
    if importlib.util.find_spec("faster_whisper") is None:
        out.append(
            Check(
                "faster-whisper (paquete)",
                "AVISO",
                "No está instalado: 'transcribe' solo funciona con --backend fixture.",
                "Todos los sistemas: uv sync --extra transcribe",
                blocking=False,
            )
        )
    else:
        out.append(Check("faster-whisper (paquete)", "OK"))
    cached = [
        m
        for m in WHISPER_MODELS
        if any(
            root.is_dir() and any(root.glob(f"models--*faster-whisper-{m}*"))
            for root in hf_cache_dirs()
        )
    ]
    if cached:
        out.append(Check("Modelo whisper en caché", "OK", ", ".join(cached)))
    else:
        out.append(
            Check(
                "Modelo whisper en caché",
                "AVISO",
                "No hay modelo descargado: la primera transcripción lo bajará "
                "(large-v3-turbo ≈ 1,6 GB; 'small' ≈ 0,5 GB con --model small).",
                "Se descarga solo al transcribir (requiere red una vez).",
                blocking=False,
            )
        )
    return out


def _check_opencv() -> Check:
    name = "OpenCV (detección de rostro)"
    try:
        import cv2
    except ImportError:
        return Check(
            name,
            "AVISO",
            "No está instalado: se usará una zona estimada para el rostro.",
            "Todos los sistemas: uv sync --extra analyze",
            blocking=False,
        )
    if not hasattr(cv2, "CascadeClassifier"):
        return Check(
            name,
            "AVISO",
            f"OpenCV {cv2.__version__} no trae Haar cascades: se usará una zona estimada.",
            "Todos los sistemas: instalar opencv-python-headless < 5",
            blocking=False,
        )
    return Check(name, "OK", cv2.__version__)


def _nearest_existing(path: Path) -> Path:
    p = path.resolve()
    while not p.exists() and p != p.parent:
        p = p.parent
    return p


def _check_disk(where: Path) -> Check:
    target = _nearest_existing(where)
    try:
        free_gb = shutil.disk_usage(target).free / 1e9
    except OSError as exc:
        return Check("Espacio libre", "FALTA", f"No se pudo medir en {target}: {exc}")
    detail = f"{free_gb:.1f} GB libres en {target}"
    if free_gb < MIN_FREE_GB_BLOCKING:
        return Check(
            "Espacio libre",
            "FALTA",
            detail + " (se necesita al menos 1 GB).",
            "Liberá espacio o usá --proyectos en otra unidad.",
        )
    if free_gb < MIN_FREE_GB_WARN:
        return Check(
            "Espacio libre", "AVISO", detail + " (poco para varios videos).", blocking=False
        )
    return Check("Espacio libre", "OK", detail)


def _check_write(where: Path) -> Check:
    target = _nearest_existing(where)
    try:
        with tempfile.NamedTemporaryFile(dir=target, prefix=".editoria-", delete=True):
            pass
    except OSError as exc:
        return Check(
            "Permisos de escritura",
            "FALTA",
            f"No se puede escribir en {target}: {exc}",
            "Elegí otra carpeta con --proyectos o ajustá los permisos.",
        )
    return Check("Permisos de escritura", "OK", str(target))


def run_checks(projects: Path | None = None) -> list[Check]:
    """Run every environment check (read-only: nothing is created or downloaded)."""
    where = projects or projects_dir()
    checks = _check_ffmpeg()
    if checks[0].status == "OK":
        checks += _check_filters()
        checks.append(_check_libass())
    else:
        checks.append(Check("Filtros de ffmpeg y libass", "FALTA", "Requiere ffmpeg.", FFMPEG_FIX))
    checks += _check_playwright()
    checks += _check_whisper()
    checks.append(_check_opencv())
    checks.append(_check_disk(where))
    checks.append(_check_write(where))
    return checks


# ---------------------------------------------------------------------------------------
_STYLE = {"OK": "[green]OK[/green]", "FALTA": "[red]FALTA[/red]", "AVISO": "[yellow]AVISO[/yellow]"}


def render_table(checks: list[Check]) -> Table:
    table = Table(title="Diagnóstico de EditorIA")
    for col in ("Estado", "Comprobación", "Detalle", "Solución"):
        table.add_column(col, overflow="fold")
    for c in checks:
        table.add_row(_STYLE[c.status], c.name, c.detail, c.fix if c.status != "OK" else "")
    return table


def register(app: typer.Typer) -> None:
    @app.command("doctor")
    def doctor_cmd() -> None:
        """Verifica ffmpeg, filtros, libass, Chromium, modelo whisper y disco."""
        checks = run_checks()
        console.print(render_table(checks))
        missing = [c for c in checks if c.status == "FALTA" and c.blocking]
        warns = [c for c in checks if c.status == "AVISO"]
        if missing:
            console.print(f"[red]Falta {len(missing)} requisito(s) bloqueante(s).[/red]")
            raise typer.Exit(code=1)
        suffix = f" ({len(warns)} aviso(s) no bloqueante(s))" if warns else ""
        console.print(f"[green]Todo lo necesario está disponible.[/green]{suffix}")
