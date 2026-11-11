# Decisiones del director

El código ejecuta y verifica; estas decisiones son tuyas. Cada una se registra en un archivo (`segmentos.json`, `plan.yaml`, `propuestas.md`), no solo en la conversación.

## 1. Estructura

Dividí el video en **gancho, desarrollo, ejemplos y cierre solo cuando esas partes existen**. Un video de 15 s puede tener solo gancho y cierre. No fuerces una estructura que el contenido no tiene.

Buscá momentos donde algo ayuda a entender el mensaje: una cifra, una lista, un cambio de idea, una pregunta, una definición. Conservá los cortes de la persona y el sentido de las frases. Nunca alargues el video para mostrar un efecto: la duración y el orden del VIDEO_BASE son inamovibles.

## 2. Completar `segmentos.json`

`editoria analyze` deja los segmentos con `role` e `intent` vacíos. Editá `proyectos/<slug>/01_analisis/segmentos.json`:

```json
{
  "id": "s03",
  "start": 9.8,
  "end": 14.2,
  "text": "Con una automatización el reporte se arma solo cada lunes",
  "role": "example",
  "intent": "Mostrar el ahorro de tiempo con un ejemplo concreto",
  "visual": "Gráfico de barras Antes/Después, etiquetado como ejemplo",
  "reference": "R06",
  "method": "original"
}
```

- `role`: `hook` (gancho), `body` (desarrollo), `example` (ejemplo), `closing` (cierre) o `null` si el segmento no cumple ninguno.
- `intent`: **para qué** está el segmento en el mensaje (una frase). No repite el texto.
- `visual`: qué se ve y por qué ayuda. Si no hay un porqué, "sin apoyo: la persona a cámara alcanza".
- `reference`: patrón R o enlace W que inspira el tratamiento. Vacío si no aplica.
- `method`: `original`, `reframe` o `generated`. **Distinguilos siempre**:
  - `reframe`: recorte o acercamiento con píxeles existentes. Menor riesgo.
  - `generated`: contenido reconstruido por IA. Solo con veredicto `aceptado` en el registro.
  - Un gráfico no es un método: es un recurso superpuesto y va en `graphics`, no cambia el `method` del intervalo.

Los tiempos y el `text` los puso el análisis: no los cambies para "acomodar" una idea.

## 3. Elegir el estilo

| Estilo | Cuándo recomendarlo | Qué se nota |
|---|---|---|
| A · Claridad profesional | Contenido de negocio sereno, pocas ideas, tono profesional | Subtítulos limpios, un gráfico a la vez, acercamientos discretos |
| B · Explicación visual | Hay un proceso, pasos, herramientas, datos o comparaciones | Listas, conversaciones, notificaciones, comparaciones, hasta dos elementos |
| C · Ritmo y personalidad | Ideas cortas y contundentes, preguntas, contrastes, energía | Tipografía grande, reencuadres frecuentes, acentos sonoros |

Las tres propuestas son **tratamientos distintos del mismo pasaje** (composición, ritmo y uso de gráficos). No cambian contenido, voz, identidad ni escenario. Recomendá una con un motivo concreto del video ("el ejemplo del minuto 0:10 se entiende mejor con una comparación"), no uno genérico ("es la más profesional"). No fuerces el formato de preguntas de C si el video no tiene preguntas.

## 4. Gráficos

- **Una idea, una plantilla.** Listalas con `editoria graphics list` y mirá una con `graphics preview` antes de ponerla en el plan.
- **Máximo simultáneo** y plantillas permitidas salen del estilo (`styles/*.yaml`); el linter lo exige. No satures: subtítulos, títulos, emojis y diagramas no conviven todos a la vez.
- **Zonas:** `upper`, `middle`, `lower`, `center`, `upper_left`, `upper_right`, `lower_left`, `lower_right`, `full`. No tapes rostro ni manos relevantes (mirá `rostro.json`), ni los controles de la plataforma.
- **Datos:** `dato_grafico` exige `data_source: real | ejemplo`. Con `real`, tené la fuente en el texto de la persona; con `ejemplo`, se muestra la etiqueta "Ejemplo" y las cifras deben ser coherentes. Nunca inventes métricas, ahorros, clientes ni testimonios.
- **Interfaces:** si no hay captura real, `ui_demo` va rotulada "Ilustración". No simules funciones que no existen. `notificacion` es genérica, sin marcas de terceros.
- **Texto:** cuidá los claims prohibidos de la marca (`forbidden_claims`): el linter los marca ERROR.
- **Emojis:** puntuales, uno a la vez (`E01` bombilla, `E02` ojos, `E03` fuego, `E04` aplauso, `E05` celebración, `E06` pensando). Para procesos de negocio, preferí iconos consistentes. Requieren `scripts/fetch_assets.py` ejecutado y llevan atribución.
- **Títulos editoriales** (`captions.editorial_titles`): texto que **no** es lo que se dice. Deben verse distintos de los subtítulos (usa `editorial_titles` del estilo).

## 5. Subtítulos

- Fieles a lo dicho; corregí ortografía sin cambiar el mensaje.
- `emphasis`: índices de palabra de `transcript.json`. Una palabra importante por idea, no más; términos del glosario de la marca y cifras son buenos candidatos.
- Posición estable, dentro de la zona segura; el generador reubica si choca con el rostro, pero verificalo en la hoja de contactos.

## 6. Reencuadres

- Intervalos `method: reframe` con `zoom` moderado (≤ `max_zoom` del estilo) y `anchor: face` o `center`.
- Cadencia según `reframe.cadence_s`, apoyada en cambios de idea; evitá cambios por rutina y saltos de gestos.
- Si la fuente es de baja resolución, evitá acercamientos: un zoom no crea detalle nuevo y el QC lo avisa.
- El zoom digital **no** se presenta como "otro ángulo de cámara".

## 7. Sonido (al final)

- Primero montaje y gráficos; después el sonido: `pop` (aparece un elemento), `click` (selección), `whoosh` (desplazamiento o reencuadre), `ding` (confirmación), `teclado` (escritura), `impacto_suave` (idea central).
- Cada cue va **pegado a la acción** (`ref` al gráfico o intervalo). Nada de un sonido por palabra; el silencio también aporta.
- La voz manda: el linter limita SFX por 10 s y separación mínima según el estilo; el QC mide loudness, true peak y la relación voz/SFX.
- Música: opcional y secundaria; solo con licencia registrada. No descargues canciones comerciales.
- Nunca digas que un sonido está "en tendencia" sin verificación actual.

## 8. Cómo editar `plan.yaml`

Partí del borrador (`plan draft`), cambiá solo lo necesario y corré `plan lint` después de cada cambio. Reglas prácticas:

- No toques `in`/`out` de los intervalos de video salvo para insertar reencuadres: los intervalos deben cubrir el video sin solapes y dentro de `[0, duración]`.
- Cada gráfico tiene `id` único; los SFX referencian ese `id` en `ref`.
- Usá el `notes` del plan para dejar el porqué de las decisiones (esto alimenta `resumen.md`).
- Si el linter marca ERROR, corregí el plan; si marca WARN, evaluá si se justifica y mencionalo en la entrega.

Referencia del formato: `plan-yaml.md`.
