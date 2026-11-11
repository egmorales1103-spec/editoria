# Leer la hoja de contactos y el reporte de QC

## Hoja de contactos (`hoja_contactos.jpg`)

`editoria contact-sheet <slug> --version V1 --every 2` genera una imagen con cuadros cada N segundos **más los bordes de cada inserción y gráfico** (entrada y salida). Cada celda lleva su tiempo. Abrí la imagen con la herramienta de lectura de imágenes y recorrela de izquierda a derecha y de arriba hacia abajo.

Qué mirar, en orden:

1. **Rostro y manos:** ¿algún subtítulo, gráfico o emoji los tapa? ¿La persona se ve igual en todos los cuadros (sin deformaciones)?
2. **Subtítulos:** ¿legibles sobre el fondo de ese cuadro? ¿dentro de la zona segura (no pegados a los bordes ni donde irían los botones de la plataforma)? ¿misma posición entre eventos? ¿la palabra destacada es la que importa?
3. **Gráficos:** ¿en los cuadros de entrada y salida se ven completos y sin cortes? ¿la etiqueta "Ejemplo" o "Ilustración" aparece cuando corresponde? ¿hay más de lo permitido a la vez?
4. **Reencuadres:** ¿el encuadre sigue al rostro? ¿se ve pixelado por el zoom? ¿el cambio cae en un cambio de idea?
5. **Tomas generadas** (si hay): ¿mismo fondo, objetos, luz y ropa que el original? ¿manos y bordes sin deformar? ¿qué dice la hoja `shots compare`?
6. **Cuadros negros o repetidos:** una secuencia de cuadros iguales o negros es un problema, no estilo.
7. **Fondo:** ¿se mantiene estable entre cuadros? Cualquier objeto nuevo o desplazado es un defecto.

Una hoja de contactos **no** sustituye ver el video: no muestra movimiento, sincronía labial ni mezcla de audio. Esos puntos quedan como `REVISIÓN HUMANA`.

## Reporte de QC (`qc/qc.md` y `qc/qc.json`)

`editoria qc <slug> --version V1` responde las preguntas de control del prompt (§10) y las reglas verificables. Cada chequeo tiene `status`:

| Estado | Significa | Qué hacés |
|---|---|---|
| `PASS` | Verificado y correcto | Nada |
| `WARN` | Aceptable pero conviene revisar | Intentá corregirlo; si lo dejás, mencionalo en la entrega con el motivo |
| `FAIL` | Incumple una regla o el archivo está mal | **Corregí antes de entregar**; la versión no se entrega con FAIL |
| `HUMAN` (se muestra como «REVISIÓN HUMANA») | No se puede verificar con código | Lo listás en la entrega para que la persona lo revise: identidad, fondo, labios, criterio estético |

Cada chequeo trae `detail` y `evidence` (tiempos, valores, rutas). Usá la evidencia: por ejemplo, un subtítulo sobre el rostro indica el tiempo del evento; un desfase de voz da los milisegundos.

### Chequeos típicos y cómo corregirlos

| Chequeo | Causa frecuente | Corrección |
|---|---|---|
| Decodificación completa / códecs / resolución / FPS | Error de render o de encode | Volver a renderizar; si persiste, `render` sin `--sample-window` y revisar `filtergraph.txt` |
| Duración ±1 cuadro | Un intervalo recortó o alargó | Revisar `video:` del plan: cobertura completa sin solapes |
| Cuadros negros / congelados vs. original | Gráfico `full`, capa mal ubicada, cuadros faltantes | Revisar el gráfico en esa franja |
| Loudness / true peak / clipping | SFX altos, mezcla | Bajar `gain_db` de los cues y volver a mezclar |
| Desfase o similitud de voz | Audio alterado | Revisar el `mix`: la voz base no se procesa más que la normalización |
| Subtítulos en zona segura / fuera del rostro | `position_y` y rostro | Revisar `rostro.json`; cambiar zona de gráficos o estilo |
| Hash del original | El original fue modificado | **Detenerte e informar**: no se entrega; no se "repara" |
| Tomas usadas aceptadas | `generated` sin veredicto | Usar `shots verdict` (decisión humana) o volver a `original`/`reframe` |
| Assets con licencia | Emoji/SFX/música sin licencia registrada | Ejecutar `scripts/fetch_assets.py` o quitar el recurso |

### Después del QC

1. Corregí todo FAIL y los WARN que tengan arreglo. Volvé a renderizar y a correr `qc`.
2. En la entrega, resumí el resultado con números (`N PASS, N WARN, N FAIL, N REVISIÓN HUMANA`) y listá los WARN y los puntos humanos.
3. No presentes un `HUMAN` como aprobado, ni redactes que "el fondo se conserva" si solo lo miraste en una hoja: decí qué miraste.
