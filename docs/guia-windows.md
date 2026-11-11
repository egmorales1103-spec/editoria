# Guía para Windows

EditorIA corre en Windows 10/11, macOS y Linux. Esta guía cubre la instalación en Windows y los problemas típicos. Los comandos van en **PowerShell**.

## 1. Requisitos

```powershell
winget install --id Git.Git -e
winget install --id astral-sh.uv -e
winget install --id Gyan.FFmpeg -e
```

- **Reiniciá la terminal** después de instalar, para que se actualice el `PATH`.
- Dejá al menos **10 GB libres**: el modelo de transcripción (de 1 a 3 GB según el tamaño), Chromium de Playwright (cientos de MB) y los renders.
- Verificá FFmpeg: `ffmpeg -version` debe mostrar la versión 6 o superior. Los filtros necesarios (`subtitles`, `ass`, `loudnorm`, `sidechaincompress`, etc.) los incluye la compilación de Gyan.

```powershell
ffmpeg -hide_banner -filters | findstr /C:"subtitles" /C:"loudnorm" /C:"sidechaincompress"
```

## 2. Instalación

Cloná el repositorio en una **carpeta sin espacios**, por ejemplo `C:\dev\editoria`:

```powershell
git clone <url-del-repositorio> C:\dev\editoria
cd C:\dev\editoria
uv sync --all-extras
uv run playwright install chromium
uv run python scripts/fetch_assets.py
uv run editoria doctor
```

`editoria doctor` muestra una tabla OK/FALTA con la solución de cada faltante.

## 3. Primer uso

```powershell
uv run editoria init "C:\Users\yo\Videos\mi video.mp4" --slug mi-video
uv run editoria probe mi-video
uv run editoria transcribe mi-video
uv run editoria analyze mi-video
```

Las rutas **con espacios y acentos** del video de entrada funcionan: la herramienta las maneja internamente (copia el original a `proyectos\mi-video\00_original\` y ejecuta FFmpeg con rutas relativas). Aun así, elegí un `--slug` corto, en minúsculas y sin espacios.

## 4. Claude Code en Windows

Claude Code necesita **Git for Windows** (incluye Git Bash). Los hooks de `.claude/settings.json` se ejecutan con `uv run --no-project python ...` y usan la variable `$CLAUDE_PROJECT_DIR`, así que requieren que `uv` esté en el `PATH`. Abrí Claude Code en la carpeta del repositorio y usá la skill `/editar-video`.

## 5. Problemas frecuentes

| Síntoma | Causa y solución |
|---|---|
| `editoria` no se reconoce | Usá `uv run editoria ...` desde la carpeta del repo, o reiniciá la terminal |
| `ffmpeg` no se encuentra | Reiniciá la terminal tras `winget install`; revisá `where.exe ffmpeg` |
| Fallan los subtítulos o el render con la ruta del proyecto | Mové el repo a una carpeta sin espacios (por ejemplo `C:\dev\editoria`) |
| Caracteres raros (`Ã±`, `�`) en la consola | Usá Windows Terminal; la CLI fuerza UTF-8 en su salida |
| Falta Chromium | `uv run playwright install chromium`; sin él, el flujo continúa sin gráficos y con una advertencia |
| La primera transcripción tarda | Descarga el modelo una vez; podés usar `--model small` para pruebas |
| Los emojis o la fuente Inter no aparecen | `uv run python scripts/fetch_assets.py`; si falla la red, se usa una fuente del sistema con una advertencia |
| El antivirus bloquea la ejecución de scripts | Excluí la carpeta del proyecto o ejecutá desde una terminal con permisos habituales; no desactives el antivirus |
| `PermissionError` al editar el original | Es intencional: `00_original\` es de solo lectura. Trabajá sobre una versión |

## 6. Desinstalar

Borrá la carpeta del repositorio y, si querés liberar espacio, la caché de modelos de Hugging Face (`%USERPROFILE%\.cache\huggingface`) y la de Playwright (`%LOCALAPPDATA%\ms-playwright`).
