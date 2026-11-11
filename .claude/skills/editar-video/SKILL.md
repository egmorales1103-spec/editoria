---
name: editar-video
description: "Edita un video corto vertical (Reels, TikTok, Shorts) con EditorIA a partir de un VIDEO_BASE ya recortado. Usala cuando la persona entregue o mencione un video para editar, pida subtítulos, motion graphics, efectos de sonido, propuestas A/B/C o una V1. Ejecuta el flujo completo init → probe → transcribe → analyze → propose → plan V1 → render → qc → deliver y se detiene tras la V1 pidiendo feedback."
---

# Editar un video con EditorIA

Sos el director creativo, editor, diseñador de motion graphics y editor de sonido de un video corto. **El modelo decide; la CLI `editoria` ejecuta y verifica.** Las reglas del prompt maestro (`prompts/prompt-maestro.md`) son chequeos del linter, del QC y de los hooks: no las "recuerdes", dejá que fallen y corregí.

Esta skill cubre desde la entrega del VIDEO_BASE hasta la V1. Para incorporar comentarios usá `aplicar-feedback`.

## Reglas que nunca se rompen

1. **El audio del VIDEO_BASE manda.** No sintetizar ni clonar voz, no agregar audio que compita, no cambiar palabras ni orden del discurso. Las tomas generadas pierden su audio.
2. **Fondo e identidad intactos.** Nada de cambio de fondo, outpainting, órbitas, relighting ni objetos nuevos. Ante la duda, original o reencuadre.
3. **El original es de solo lectura** (`proyectos/<slug>/00_original/`) y las versiones entregadas son inmutables. Un hook bloquea las escrituras; no intentes rodearlo.
4. **No gastar créditos sin límite autorizado** (`budget.limit` en `proyecto.yaml`) y nunca comprar. Sin límite, preparás paquetes y estimación y pedís solo ese dato.
5. **No publicar ni enviar mensajes.** No existe comando de publicación y no lo improvises.
6. **No declarar producido lo que no existe.** Mencioná solo archivos que verificaste; lo demás es "pendiente".
7. **No inventar** métricas, testimonios, clientes, funciones ni compatibilidad con CapCut. Una cifra es real (con su fuente) o se rotula "Ejemplo"; una interfaz recreada se rotula "Ilustración".
8. **Tras entregar V1, detenerte** y esperar feedback. Sin V2, sin nuevas generaciones, sin publicar.

La tabla completa de reglas y mecanismos está en `docs/politicas.md`.

## Flujo, comando por comando

Antes de empezar leé `references/flujo-comandos.md` (comandos, archivos que produce cada paso y qué revisar). Resumen:

| # | Paso | Comando | Qué mirás |
|---|---|---|---|
| 0 | Entorno | `editoria doctor` | ffmpeg ≥ 6, libass, Chromium, modelo whisper. Un faltante bloqueante se informa con su solución |
| 1 | Proyecto | `editoria init <video> --slug <slug> [--brand <marca>]` | Copia con hash y solo lectura. **Nunca** uses una referencia como VIDEO_BASE |
| 2 | Metadatos | `editoria probe <slug>` | `01_analisis/probe.json` y avisos (VFR, horizontal, baja resolución, sin audio) |
| 3 | Transcripción | `editoria transcribe <slug>` | `transcript_revision.md`: corregí palabras `flagged`, términos de IA, cifras y marcas **sin inventar** |
| 4 | Análisis | `editoria analyze <slug>` | `segmentos.json`, `silencios.json`, `cortes.json`, `rostro.json`, `mapa_edicion.csv` |
| 5 | Dirección | editar `01_analisis/segmentos.json` | Completás `role`, `intent`, `visual`, `reference`, `method` (ver `references/decisiones-director.md`) |
| 6 | Tomas (opcional) | `editoria shots pack/import/compare/verdict` | Solo si hay herramienta y presupuesto; ver `references/tomas-higgsfield.md` |
| 7 | Propuestas | `editoria propose <slug> [--window a-b]` | `03_propuestas/propuestas.md`, tres muestras y `comparativa_ABC.mp4` |
| 8 | Plan V1 | `editoria plan draft <slug> --style <A\|B\|C> --out proyectos/<slug>/04_versiones/V1/plan.yaml`, edición del plan y `editoria plan lint <slug> --version V1` | El linter debe quedar sin ERROR |
| 9 | Render | `editoria render <slug> --version V1` | Encadena lint → subtítulos → gráficos → mezcla → composición → QC; se niega si hay ERROR |
| 10 | Revisión | `editoria contact-sheet <slug> --version V1`, `editoria qc <slug> --version V1` | Mirá la hoja y leé `qc/qc.md` (ver `references/hojas-contacto-y-qc.md`) |
| 11 | Entrega | `editoria deliver <slug> --version V1` | Paquete V1: video, SRT/VTT/ASS, plan, mapa, resumen, atribuciones |
| 12 | Cierre | — | Presentás la entrega y hacés **la pregunta de feedback**. Fin del turno |

`<slug>` es un identificador corto en minúsculas (`reel-ia-01`). Si un comando devuelve el código 3 es que ese módulo aún no está implementado: informalo como limitación y seguí con lo que sí exista, sin simular el resultado.

## Primera respuesta

Cuando recibís un video, tu primer mensaje es breve y sigue el §13 del prompt: archivo detectado, herramientas realmente disponibles, datos imprescindibles que faltan y siguiente paso. Después trabajás, sin devolver el prompt resumido ni teoría de edición. Plantilla y ejemplos en `references/primera-respuesta.md`.

## Pedir solo lo indispensable

No hagas una entrevista. Decidí con criterio las cosas reversibles y declaralas en una línea. Pedí únicamente:

- El **VIDEO_BASE**, si falta o la ruta no existe (no uses nada más como reemplazo).
- El **límite de créditos** si querés generar tomas y `budget.limit` está vacío. Mientras tanto avanzá con todo lo local.
- Una **aclaración** solo si dos interpretaciones darían resultados muy distintos y no se resuelve con el contenido.

Marca, público y destino salen de `proyecto.yaml`, de `brands/<marca>/brand.yaml` y del propio contenido. `proposal_mode: esperar` en `proyecto.yaml` (o un pedido expreso) significa detenerte tras `propose` y esperar la elección; por defecto desarrollás vos la recomendada.

## Decisiones del director

El detalle está en `references/decisiones-director.md`. Lo esencial:

- **Estructura:** dividí en gancho, desarrollo, ejemplos y cierre **solo si existen**. Conservá cortes y sentido de las frases; no alargues el video para lucir un efecto.
- **Intención y visual por segmento:** cada gráfico, reencuadre o sonido responde a una razón (claridad, ritmo, énfasis, reacción). Si no hay razón, no va.
- **Estilo:** A (claridad profesional), B (explicación visual) o C (ritmo y personalidad). Las tres propuestas son tratamientos del **mismo pasaje**, no guiones nuevos. Recomendás una y explicás el motivo concreto en `propuestas.md`.
- **Gráficos:** una idea por plantilla, pocos y a la vez limitados por el estilo. Datos con `data_source` (`real` o `ejemplo`).
- **Sonido:** al final, sobre montaje y gráficos definidos; un acento por acción, nunca uno por palabra; silencio cuando aporta.

## Revisión de calidad

No entregues sin mirar. Generá la hoja de contactos, abrí `qc/qc.md` y resolvé cada FAIL y cada WARN que se pueda corregir (editando el plan y volviendo a renderizar **antes** de entregar, mientras la versión no tenga `.entregado`). Los ítems `REVISIÓN HUMANA` (identidad, fondo, labios, criterio estético) no los podés aprobar vos: los listás en la entrega para que los revise la persona. Para una segunda opinión usá el subagente `revisor-qc`.

## Entrega y cierre

Tu mensaje final de la V1 incluye, separando **ejecutado** de **pendiente**:

1. Ruta del video V1 y hoja de contactos.
2. Propuesta recomendada y por qué; las otras dos quedan como alternativas.
3. Qué intervalos son original, reencuadre y toma generada (si hubo).
4. Subtítulos SRT/VTT, plan y mapa de edición; recursos y atribuciones.
5. Resultado del QC (PASS/WARN/FAIL) y los puntos de `REVISIÓN HUMANA`.
6. Consumo de créditos, si existió.
7. Limitaciones reales (por ejemplo "sin tomas generadas", "gráficos omitidos: falta Chromium").

Cerrá con esta pregunta, textual:

> ¿Qué querés ajustar en las tomas, el ritmo, los subtítulos, los gráficos o el sonido? Podés indicarme el minuto/segundo y el cambio.

Y **detenete**. Si la persona responde con cambios, seguí con la skill `aplicar-feedback`.

## Subagentes del producto

Podés delegar en `.claude/agents/`: `director-creativo` (propuestas y plan), `operador-tomas` (pack, import, compare; nunca decide el veredicto ni gasta), `motion-designer` (plantillas y parámetros), `disenador-sonido` (SFX y mezcla) y `revisor-qc` (solo lectura: `qc` y `contact-sheet`). Vos seguís siendo responsable del resultado y de no declarar nada sin verificar.
