# Módulo: subtítulos (`captions/`)

Genera, para una versión, `subtitulos.ass` (con estilo, para quemar en el video),
`subtitulos.srt` y `subtitulos.vtt` (texto limpio en UTF-8, para subir a la plataforma) y
`subtitulos.json` (lista de `CaptionEvent` con la caja estimada de cada evento, que usa QC).

```bash
editoria captions build <slug> --version V1
```

Lee `04_versiones/V1/plan.yaml` (estilo, énfasis, títulos editoriales, reencuadres),
`transcript.json`, `cortes.json`, `rostro.json` y `probe.json`. Python:
`build_for_version(ctx, "V1")` o `AssCaptionBuilder().build(...)` (contrato `CaptionBuilder`;
acepta además `cuts=`, `editorial_titles=` y `duration=` como argumentos opcionales).

## Agrupación de palabras

1. Se corta siempre en: pausas > 0,25 s, puntuación de cláusula (`. , ; : ? ! …`) y cortes de
   cámara (una palabra que cruza el corte va del lado donde cae su punto medio).
2. Cada tramo se reparte en partes parejas de hasta `words_per_event` palabras, y se divide de
   nuevo si el texto no entra en `max_lines` líneas de `max_chars_line` caracteres (corte de
   línea balanceado).
3. Cada evento empieza con su primera palabra y termina con la última; puede quedarse hasta
   0,8 s más para respetar `max_cps` (y un mínimo de 0,5 s), sin pisar el evento siguiente,
   el próximo corte de cámara ni el final del video. Ningún evento contiene un corte.
4. Los caracteres por segundo se cuentan sin espacios. Si el habla es más rápida que la lectura
   cómoda, el texto se mantiene fiel y se emite un AVISO con los tiempos.

## Estilo visual (ASS)

- `PlayResX/Y` = lienzo (1080×1920). Estilo `<A|B|C>` para lo dicho y `<A|B|C>_titulo` para
  títulos editoriales (caja opaca con el color `highlight` del preset de títulos y texto en
  blanco o negro según contraste). Si el preset no define `editorial_titles`, se deriva uno
  distinto (P13).
- Colores de la marca: texto `text`, contorno `bg`, resaltado `highlight` del estilo.
- Resaltado: en estilos con animación `pop` (C) la palabra activa se colorea mientras se dice
  (karaoke por palabra con `\t(...\1c...)`); en `fade` (A, B) se colorean las palabras de
  `emphasis` (color propio o el de resaltado). Las palabras de énfasis conservan su color en
  ambos modos.
- Animación: `pop` = `\t` sobre `\fscx\fscy` (70 % → 110 % → 100 %); `fade` = `\fad`.
- Mayúsculas según `case` (`upper`, `lower`, `sentence`, `as_is`).
- Fuente: la del estilo, luego la de la marca; se buscan en `assets/fonts/` (pasar `fontsdir` a
  libass) y luego en el sistema. Si no está, se usa Arial (Windows/macOS) o DejaVu Sans
  (Linux) con un AVISO.

## Posición y rostro

- Posición estable para todos los eventos: centro en `position_y` × alto, ajustado para que el
  bloque de `max_lines` líneas quede dentro de la zona segura (`Canvas.safe`: arriba 220 px,
  abajo 420 px, izquierda 60 px, derecha 140 px a 1080×1920; configurable en el plan).
- Las cajas a evitar se calculan desde `rostro.json` con `util.geometry.base_transform` (y
  agrandadas por el zoom de cada reencuadre). Si el bloque choca con el rostro (margen 24 px),
  se mueve a la altura libre más cercana dentro de la zona segura; si no hay ninguna, queda
  abajo con un AVISO.

## Limitaciones conocidas

- Ancho y alto del bloque son estimaciones por promedio de glifos (no se mide la fuente).
- La caja del rostro es la unión de todas las muestras (no varía en el tiempo).
- Los títulos editoriales no se reubican si coinciden con un gráfico: lo decide el director.
