# Render, reencuadre y QC (módulo A5)

Compone el MP4 final de una versión a partir de `plan.yaml` y de lo que dejaron los otros módulos, y verifica el resultado antes de entregar. **El reloj maestro es el audio del VIDEO_BASE:** el render nunca cambia la duración, el orden ni los cortes del original, y el audio es siempre el del base o la mezcla (`audio/mezcla.wav`), nunca el de una toma generada (P03, P04).

## Comandos

```bash
editoria render <slug> --version V1                      # escribe 04_versiones/V1/video.mp4
editoria render <slug> --sample-window 4-10              # muestra_4-10.mp4 (preset veryfast)
editoria render <slug> --preset slow --crf 17            # ajustes de x264
editoria contact-sheet <slug> --version V1 --every 2     # hoja_contactos.jpg
editoria qc <slug> --version V1                          # qc/qc.json + qc/qc.md (sale con 1 si hay FAIL)
```

Una versión entregada (`.entregado`) es inmutable: `render` (con cualquier salida: completo,
`--sample-window` o `--solo-componer`), `contact-sheet` y `qc` se niegan con un mensaje en
español, y lo mismo hacen `FFmpegRenderer.render` (si `out` cae dentro de una versión entregada o
de `00_original/`), `contact_sheet()` y `DefaultQualityControl.run()`.

## Qué lee `render` (dentro de `04_versiones/Vn/`)

| Archivo | Origen | Si falta |
|---|---|---|
| `plan.yaml` | director / A2 | error |
| `subtitulos.ass` | A2 | aviso; sale sin subtítulos |
| `graficos/overlays.json` (`{"overlays": [OverlayClip…]}`) | A3 | aviso; sale sin gráficos |
| emojis del plan (`assets/emoji/<id>.gif`) | A7 | se omite con aviso (si no vinieron en `overlays.json`) |
| `audio/mezcla.wav` | A4 | aviso; se usa el audio del VIDEO_BASE |
| tomas aceptadas (`ProjectShotLibrary.accepted`) | A6 | ninguna; un intervalo `generated` sin toma es error (P05) |
| `assets/fonts/<Familia>/` (`util.resources.font_family_dir(style.captions.font)`, si no la de `brand.fonts.body`) | A7 | libass usa fuentes del sistema (aviso) |

Escribe `video.mp4` y `filtergraph.txt` (el grafo exacto usado, para reproducir el render).

## Cómo compone

1. **Lienzo** 1080×1920 al FPS de origen (`Canvas.resolve_fps`). El base llena el lienzo con `util.geometry.base_transform`: fuente 9:16 menor → escala lanczos y aviso “sin detalle nativo nuevo”; fuente horizontal → recorte 9:16 centrado en el rostro y aviso.
2. **Reencuadres** (`method: reframe`): el video se parte en segmentos contiguos (`split` + `trim`) y se vuelve a unir con `concat`, así cada cuadro del original sale una sola vez y en orden. `motion: cut` = punch-in (`crop` sobre píxeles de la fuente + `scale` lanczos); `motion: push` = `zoompan` de 1× al zoom pedido. Ancla `face` (mediana de `rostro.json` en el intervalo), `center` o `point` (normalizado sobre el lienzo).
3. **Tomas generadas**: overlay del clip conformado, sin audio, durante `[in, out]`.
4. **Gráficos** (secuencias PNG RGBA, `setpts` + `eof_action=pass`) y luego **emojis** (GIF en bucle, recortado a `[start, end]` y escalado a `w×h`).
5. **Subtítulos ASS** al final (`ass` con `fontsdir`).
6. **Encode**: libx264 High, yuv420p, CRF 18, preset `medium` (muestras `veryfast`), AAC 192 kbps 48 kHz estéreo, `+faststart`. `--sample-window a-b` busca en la entrada (`-ss a -t b-a` antes del base y de la mezcla) para decodificar solo la ventana; justo después del base el grafo restaura la línea de tiempo original (`setpts=PTS+a/TB`, o tras el `concat` de los segmentos recortados a la ventana), así tomas, gráficos, emojis y subtítulos usan sus tiempos originales sin cambios, y al final `trim=start=a:end=b,setpts=PTS-STARTPTS` lleva la muestra a 0. Un `push` que empezó antes de `a` continúa su zoom desde el cuadro que le corresponde. Un test compara cuadros y audio de la muestra con los mismos instantes del render completo.

ffmpeg se ejecuta con `cwd` = carpeta de la versión y todas las rutas son relativas (`-/filter_complex filtergraph.txt`; en ffmpeg < 7, `-filter_complex_script`). libass no abre rutas con acentos en Windows: si el ASS no tiene una ruta relativa ASCII, se copia junto al video.

### Guarda de zoom (P07)

Un reencuadre no puede mostrar los píxeles nativos a más de `EncodeSettings.max_zoom` (1,25×). Se mide `escala del base × zoom`: en una fuente 1080×1920 el límite es zoom 1,25; en una fuente 720×1280 (ya escalada 1,5×) o en una horizontal recortada (≈1,78×) **cualquier** zoom > 1 se rechaza. El render lanza `ZoomGuardError` y QC lo marca FAIL. El zoom del estilo (`reframe.max_zoom`) solo produce WARN.

## QC (`DefaultQualityControl`)

Responde las 9 preguntas de la sección 10 del prompt; cada chequeo indica la pregunta y la regla en `prompt_question`.

| id | Regla | Qué mide | Estado |
|---|---|---|---|
| `decode` | §10 Q1 | decodificación completa sin errores, imagen y audio | FAIL si hay errores |
| `format` | P19 | h264 High yuv420p, 1080×1920, FPS de origen, AAC 48 kHz | FAIL |
| `faststart` | P19 | átomo `moov` antes de `mdat` | FAIL |
| `duration` | P04 | duración igual al original ±1 cuadro | FAIL |
| `black` / `freeze` | §10 Q4 | `blackdetect` / `freezedetect`, solo lo que no está en el original | FAIL / WARN |
| `loudness` | P18 | LUFS integrado vs objetivo, true peak, muestras saturadas | FAIL si TP > 0 o clipping; WARN si se aleja del objetivo |
| `voice_sync` | P03 | desfase y similitud de la voz (correlación; inyectable) | FAIL > 100 ms; WARN > 45 ms |
| `original_hash` | P01 | sha256 del original vs `proyecto.yaml` y `.sha256` | FAIL |
| `zoom_guard` | P07 | guarda de zoom; fuente escalada u horizontal | FAIL / WARN |
| `captions` | P12 | cada evento dentro de la zona segura y fuera del rostro (con el zoom de los reencuadres) | FAIL; WARN si es solo horizontal y estimado desde el ASS |
| `shots_accepted` | P05 | tomas usadas con veredicto `aceptado` | FAIL |
| `licenses` | P17 | SFX, emojis y música con licencia en los manifests | FAIL |
| `plan_lint` | — | linter de políticas (si está disponible o se inyecta) | FAIL con ERROR |
| `deliverables` | P11 | archivos reales y pendientes | WARN si faltan SRT/VTT |
| `identity`, `background`, `lips`, `aesthetic` (+ `generated_shots`) | P24, P08, P03 | no verificable automáticamente | siempre REVISIÓN HUMANA |

`qc.json` guarda en `video_sha256` el sha256 del `video.mp4` verificado (la entrega lo compara).
El análisis del ORIGINAL (`blackdetect`, `freezedetect`, `ebur128`) se cachea en
`01_analisis/.cache/qc_original.json` con clave sha256 del original y parámetros de los filtros:
los QC siguientes solo decodifican el video final.

Las cajas de subtítulos salen de `subtitulos.json` cuando trae `box`; si no, se estiman desde `subtitulos.ass` (estilo, alineación, márgenes, `\pos`, `\an`).

## API (Python)

```python
from editoria.render import FFmpegRenderer, inputs_from_version, contact_sheet
from editoria.qc import DefaultQualityControl

inputs = inputs_from_version(ctx, "V1")
FFmpegRenderer().render(plan, ctx, inputs, vdir / "video.mp4", EncodeSettings())
contact_sheet(ctx, "V1", every=2.0)
report = DefaultQualityControl(voice_checker=mixer.check_voice, linter=lint_plan).run(ctx, "V1")
```

## Limitaciones

- `zoompan` redondea la posición a píxeles enteros: en pushes muy lentos puede verse un leve temblor.
- Las cajas estimadas desde el ASS son aproximadas (ancho por clase de carácter); por eso un desborde solo horizontal es WARN.
- El chequeo de voz de respaldo correlaciona la forma de onda de los primeros 60 s; con música fuerte la similitud baja (WARN).
- QC no evalúa si los gráficos tapan el rostro ni la ortografía: eso queda en REVISIÓN HUMANA.
