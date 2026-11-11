# Sonido y mezcla (`editoria.audio`)

Módulo A4. El audio del VIDEO_BASE manda (P03): la mezcla parte de ese audio, le suma efectos de
sonido (SFX) y, opcionalmente, música, y normaliza el resultado. La voz no recibe ningún otro
procesamiento (sin ecualización, compresión ni limitador).

## Comandos

```bash
editoria audio sfx                              # tabla de SFX, licencias y estado de los hashes
editoria audio mix <slug> --version V1          # escribe 04_versiones/V1/audio/mezcla.wav + mezcla.json
editoria audio check-voice <slug> <media>       # desfase (ms) y similitud de la voz vs el original
```

`check-voice` termina con código 1 si el desfase supera un cuadro (33 ms) o si la similitud es
menor a 0,5. `<media>` puede ser un MP4 o un WAV.

`audio mix` (y `mix_for_version()`) se niegan a escribir en una versión entregada
(`.entregado`): crear una versión nueva con `editoria version new`.

## Puntos de entrada en Python

| Nombre | Qué hace |
|---|---|
| `FFmpegAudioMixer.mix(base_video, cues, music, spec, out_wav) -> MixResult` | Mezcla y normaliza (implementa `AudioMixer`). |
| `FFmpegAudioMixer.check_voice(base_video, final_media) -> VoiceCheck` | Correlación cruzada. También disponible como `check_voice(...)`. |
| `mix_for_version(ctx, version) -> MixResult` | Lee `plan.yaml`, mezcla sobre el original y escribe `audio/mezcla.wav` y `audio/mezcla.json`. |
| `measure_loudness(path) -> Loudness` | LUFS integrados, true peak (4x), LRA, pico de muestra y muestras con clipping. WAV o cualquier medio con audio. |
| `check_sfx_density(cues, style) -> list[str]` | Violaciones (en español) de separación mínima, máximo por 10 s y cues permitidos. Lista vacía = correcto. |

`FFmpegAudioMixer(sfx_dir=None, music_root=None)`: `sfx_dir` reemplaza `assets/sfx`; `music_root`
es la carpeta contra la que se resuelven rutas relativas de `MusicSpec.path` (`mix_for_version`
usa la carpeta del proyecto; también se prueba la raíz del repo y el directorio actual).

## Cadena de mezcla

```
audio base -> aresample 48 kHz ---------------------------------+
SFX n      -> volume(gain_db) -> adelay(at, en muestras) --------+--> amix(normalize=0) -> loudnorm 2 pasadas
música     -> volume -> sidechaincompress (clave = voz) --------+     (linear=true, I=-14, TP=-1)
```

- Canales: se conserva el del base (mono queda mono; estéreo queda estéreo; más de 2 se mezclan a
  estéreo). Los SFX son mono y se duplican a ambos canales sin cambiar el nivel.
- `amix` usa `normalize=0` (suma pura). Con builds de ffmpeg sin esa opción (anteriores a 7.1) se
  usa un respaldo equivalente (`apad` + `volume=N`).
- La duración de la mezcla es la del audio base; un SFX que empieza después del final se omite con
  aviso. Los SFX de variante `None` usan la variante 1.
- Música: se repite en bucle si es más corta que el video, entra con fundido de 0,4 s y sale con
  fundido de 1,5 s. El umbral del `sidechaincompress` se calcula del nivel de la voz para que la
  música baje aproximadamente `duck_db` mientras hay voz (calibrado en pruebas: ±2 dB).
- `loudnorm` va en dos pasadas con `linear=true`, `LRA=50` (para no salir del modo lineal) y un
  margen interno de 0,1 dB bajo el `true_peak_db` pedido. Tras escribir el WAV se mide de nuevo y
  se repite el render con un objetivo menor si el true peak queda por encima.
- **Voz sin compresión:** si el material no puede llegar a `target_lufs` de forma lineal sin superar
  el true peak, el objetivo se baja (el resultado queda por debajo de -14 LUFS) y se avisa; nunca se
  deja que `loudnorm` pase al modo dinámico. Es una decisión de diseño a favor de la fidelidad de
  la voz; el QC verá ese loudness menor en `mezcla.json`.
- Salida: WAV PCM 16 bits, 48 kHz. Si el base no tiene audio (`NoAudioError`) o es silencio, el
  error es explícito y en español.

`MixResult`: `wav`, `lufs`, `true_peak`, `lra`, `clipped_samples` y `voice_to_sfx_db` (relación de
potencia voz/SFX en los cuadros de 20 ms donde ambos suenan; `None` si nunca coinciden).

## Verificación de voz

`check_voice` decodifica ambos medios a mono 16 kHz y busca el pico de la correlación cruzada
normalizada (solo sobre la zona solapada) dentro de ±1 s, con interpolación parabólica. Devuelve
`offset_ms` (positivo = el final llega tarde) y `similarity` (0 a 1). Se compensa el
`start_time` del flujo de audio de cada archivo, porque ffmpeg descarta el hueco inicial al
decodificar (así un `-itsoffset` también se detecta). Un MP4 con AAC queda dentro de ±1 cuadro.

## SFX incluidos (`assets/sfx/`)

Seis cues (`pop`, `click`, `whoosh`, `ding`, `teclado`, `impacto_suave`) con 3 variantes cada uno
(`<cue>_<n>.wav`, n = 1..3). Se generan con `scripts/gen_sfx.py`: síntesis propia con numpy
(osciladores, ruido filtrado, envolventes), semilla fija, WAV 48 kHz mono 16 bits, pico -1 dBFS y
colas con fundido. Total aproximado: 1 MB. Licencia CC0-1.0, autoría "EditorIA contributors".

```bash
uv run python scripts/gen_sfx.py           # regenera WAV + manifest.yaml
uv run python scripts/gen_sfx.py --check   # verifica hashes sin escribir
```

Los sha256 de `manifest.yaml` son reproducibles: el escritor WAV es determinístico y las pruebas
comprueban que el generador reproduce exactamente esos hashes. Si se cambia la síntesis hay que
regenerar los archivos y el manifest juntos. Los usos sugeridos del manifest son orientativos; no
afirman que un sonido esté de moda ni que mejore métricas.

El volumen relativo entre cues no está igualado por loudness (todos tienen el mismo pico); el
`gain_db` del plan (por defecto -14 dB) es el que ajusta cada uno.

## Limitaciones conocidas

- `mix_for_version` mezcla el audio completo del original; si el plan tiene `window` (propuestas),
  el recorte de la muestra lo hace el render.
- El true peak se calcula por sobremuestreo 4x en el dominio de la frecuencia; coincide con
  `ebur128` dentro de unas décimas de dB.
- La densidad de SFX en `mix_for_version` solo emite avisos; el linter del plan (P16) es quien bloquea.
- No se valida la licencia de la música en la mezcla (lo hace el linter, P17).
