# Módulo de ingesta, análisis y versionado

Dueño: A1. Código en `src/editoria/{ingest,analysis,versioning}/` y `src/editoria/doctor.py`.

Flujo: `doctor` → `init` → `probe` → `transcribe` → `analyze` → (entrega de V1) → `feedback parse` → `version new`.

## `editoria doctor`

Tabla con estado `OK` / `FALTA` / `AVISO`, el detalle y la solución para Windows (winget), macOS (brew) y Linux (apt).

| Comprobación | Bloqueante |
|---|---|
| `ffmpeg` y `ffprobe` en el PATH, ffmpeg ≥ 6 | sí |
| Filtros: `subtitles`, `ass`, `loudnorm`, `ebur128`, `sidechaincompress`, `blackdetect`, `freezedetect`, `silencedetect`, `ssim`, `overlay`, `scdet`, `zoompan` | sí |
| libass | sí |
| Paquete Playwright y Chromium en la caché de Playwright | sí |
| Espacio libre en la carpeta de proyectos (< 1 GB falta, < 5 GB aviso) y permiso de escritura | sí |
| Modelo whisper en la caché de Hugging Face, paquete `faster-whisper`, OpenCV con Haar | no (aviso) |

El código de salida es distinto de 0 solo si falta algo bloqueante. `doctor` no crea ni descarga nada.

## `editoria init <video> --slug <id> [--brand <marca>]`

- Exige la ruta explícita de un archivo de video existente. Si falta o no existe, el error pide únicamente ese archivo (P02). Un archivo dentro de `02_Referencias_Usuario` se rechaza: una referencia no es el VIDEO_BASE.
- Si no se da `--slug`, se deriva del nombre del archivo. Si el slug ya existe, es un error: nunca se sobrescribe.
- **Copia** (nunca mueve) el video a `00_original/video_base.<ext>`, escribe `video_base.sha256`, verifica que la copia tenga el mismo hash y marca ambos archivos como solo lectura (P01).
- Crea `proyecto.yaml` (`original`, `original_sha256`, `source_name`). Si algo falla a mitad de camino, borra lo que creó.

## `editoria probe <slug>`

Escribe `01_analisis/probe.json` (`ProbeResult`). Decodifica todo el archivo (`-v error -f null -`) para detectar corrupción. Avisos en español: corrupción (el comando termina con código 1, pero el JSON se escribe), VFR (por diferencia entre `r_frame_rate` y `avg_frame_rate` o por tiempos de cuadro irregulares), rotación en metadatos, video horizontal, ancho < 1080 y falta de audio.

## `editoria transcribe <slug> [--model] [--backend whisper|fixture] [--force]`

- `whisper`: faster-whisper, idioma `es`, `word_timestamps`, glosario de la marca como `initial_prompt`, `large-v3-turbo` en CPU con int8 (alternativa: `--model small`). Requiere `uv sync --extra transcribe`.
- Caché en `01_analisis/.cache/` con clave = hash del audio + modelo + prompt. `--force` la ignora.
- Cada palabra con `prob` < 0,6 queda `flagged` (P23). El texto nunca se corrige: se marca para que una persona lo escuche. `transcript_revision.md` lista el texto por tiempo con las palabras dudosas entre `[[ ]]`.
- `fixture`: copia `tests/.fixtures/transcript_fixture.json` (o el archivo de `EDITORIA_TRANSCRIPT_FIXTURE`). Para pruebas y trabajo sin red.

## `editoria analyze <slug> [--force]`

Necesita `transcript.json` (hace `probe` solo si falta `probe.json`). Escribe en `01_analisis/`:

- `silencios.json`: `silencedetect` a -35 dB, mínimo 0,25 s.
- `cortes.json`: cortes duros con `select='gt(scene,0.3)'`.
- `rostro.json`: Haar de OpenCV cada 0,5 s si está disponible; si no, o si no detecta nada, una zona superior central con `estimated: true` (calculada sobre el recorte 9:16, coordenadas en píxeles de la fuente).
- `segmentos.json`: oraciones separadas por puntuación final o pausas ≥ 0,35 s (los tramos de más de 8 s se parten en su pausa mayor). `role`, `intent`, `visual` quedan vacíos para el director.
- `mapa_edicion.csv`: columnas exactas de `MAPA_COLUMNS`, una fila por segmento con `estado = pendiente`.

Si `segmentos.json` ya tiene decisiones del director (rol, intención, etc.) no se sobrescribe sin `--force`.

## `editoria feedback parse <slug> <Feedback.md> [--version V1] [--force]`

Convierte `Feedback_V1.md` completado en `feedback.json` dentro de la versión indicada (es el único archivo que se agrega a una versión ya entregada).

- Impresión general: `Propuesta que prefiero`, `Quiero conservar`, `Quiero cambiar` (los textos de ejemplo de la plantilla cuentan como vacíos).
- Tabla `Cambios por momento`: tiempos `mm:ss`, `mm:ss.s`, `ss.s`, `h:mm:ss`, instante único o rango con `–`, `—` o `-`. Las filas vacías o la fila de ejemplo `00:00–00:00` se ignoran. Una fila con contenido y tiempo ilegible es un error que lista las filas a corregir: el feedback nunca se adivina.
- Revisión rápida: se guardan solo las preguntas que se respondieron.
- Si ya hay `feedback.json`, hace falta `--force`.

## `editoria version new <slug> --from V1`

Copia el plan de la versión de origen a la siguiente (`V1` → `V2`) con `version` actualizada. Exige `feedback.json` en la versión de origen (P20), exige que ese feedback sea de esa versión, y nunca sobrescribe: si la versión siguiente existe, es un error. La versión de origen no se modifica.

## Puntos de entrada en Python

```python
from editoria.ingest import init_project, probe_project, transcribe_project
from editoria.analysis import analyze_project
from editoria.versioning import new_version, parse_feedback, save_feedback
from editoria.doctor import run_checks, has_blocking_failures
```

Los errores que el usuario puede corregir se lanzan como `editoria.ingest.IngestError` (mensaje en español, listo para mostrar).
