---
name: aplicar-feedback
description: "Incorpora el feedback de la persona sobre una versión entregada (V1, V2…) de un video editado con EditorIA. Usala cuando la persona responda con cambios por minuto/segundo, complete Feedback_V1.md o pida ajustes de tomas, ritmo, subtítulos, gráficos o sonido. Convierte los comentarios en cambios con ubicación temporal, crea la versión siguiente sin sobrescribir nada, renderiza, hace QC y entrega."
---

# Aplicar feedback y crear la versión siguiente

Se usa **después** de entregar una versión (`editar-video` terminó con la pregunta de feedback). Objetivo: aplicar exactamente lo pedido, **conservar lo aprobado** y no tocar nada más.

## Reglas

1. **Versiones inmutables:** nunca edites una versión con `.entregado`. Los cambios van siempre en la siguiente (V2, V3…). Un hook bloquea las escrituras en versiones entregadas.
2. **El original no se toca** y el audio base sigue mandando.
3. **Conservá lo aprobado.** Si la persona dijo qué le gustó, eso no cambia. Un ajuste puntual no justifica rehacer la estética ni reescribir el contenido.
4. **No generar tomas nuevas ni gastar créditos** sin una instrucción expresa y un límite autorizado (`budget.limit`).
5. **No publicar** ni enviar mensajes. Al entregar la nueva versión, volvés a detenerte.
6. **Una preferencia aislada no es una regla permanente.** Solo guardás como preferencia de marca lo que la persona confirma como tal.

## Flujo

### 1. Recibir el feedback
El feedback llega en el chat o como `templates/docs/Feedback_V1.md` completado. Si llega en el chat, volcalo vos a un archivo con esa misma estructura (impresión general y tabla `Tiempo en V1 | Elemento | Qué cambiar | Resultado deseado`). Guardalo **fuera** de `04_versiones/` (por ejemplo `proyectos/<slug>/feedback_V1.md`): las versiones entregadas son inmutables y el hook bloquearía la escritura.

Formatos de tiempo aceptados: `mm:ss`, `ss.s`, rangos `00:12–00:15`. Las filas vacías se ignoran.

### 2. Parsear
```
editoria feedback parse <slug> proyectos/<slug>/feedback_V1.md --version V1
```
Escribe `feedback.json` (lo hace la CLI, que es la única que puede) con ítems `{t_in, t_out, element, change, desired}` más lo que la persona quiere conservar y cambiar. Leé el resultado y verificá que los tiempos y elementos quedaron como los dijo.

### 3. Convertir comentarios en cambios concretos
Armá una lista de cambios, cada uno con:
- **Ubicación temporal** (`t_in`–`t_out` en la V anterior; los tiempos no se desplazan porque la duración no cambia).
- **Elemento afectado:** toma, ritmo, subtítulo, gráfico o sonido, y el id del plan (`v02`, `g01`, `sfx[3]`).
- **Cambio** exacto en el plan (qué clave, qué valor).
- **Lo que se conserva** alrededor.

Mapa de elementos a lugar del plan:

| Comentario sobre… | Se cambia en… |
|---|---|
| Toma / encuadre | `video[]` (zoom, anchor, motion, método) |
| Ritmo / cortes de reencuadre | `video[]` (más o menos reencuadres; nunca el orden ni la duración del base) |
| Subtítulos (texto, énfasis, tamaño) | `captions.emphasis`, estilo, o la transcripción corregida |
| Gráficos | `graphics[]` (plantilla, params, tiempos, zona) |
| Sonido | `sfx[]` y `mix`; música solo con licencia |
| Estilo en general | `style` y todo lo derivado: solo si lo pidió expresamente |

**Ambigüedad:** si un comentario admite dos interpretaciones muy distintas, hacé una pregunta breve **y avanzá con los cambios independientes** mientras tanto. No inventes la intención.

**Lo que no se puede hacer:** si un pedido choca con una regla (por ejemplo "cambiá el fondo", "agregá una cifra de ahorro" sin dato real, "usá esta canción comercial"), no lo ejecutes: explicá cuál es la regla y ofrecé una alternativa válida.

### 4. Crear la versión
```
editoria version new <slug> --from V1
```
Copia el plan a la versión siguiente. Exige feedback parseado y nunca sobrescribe. Si falla por falta de `feedback.json`, volvé al paso 2.

### 5. Editar el plan nuevo
Aplicá la lista de cambios en `proyectos/<slug>/04_versiones/V2/plan.yaml` (referencia en `.claude/skills/editar-video/references/plan-yaml.md`) y corré:
```
editoria plan lint <slug> --version V2
```
Sin ERROR. Documentá en `notes` del plan qué cambió respecto de V1 y por qué.

### 6. Render y QC
```
editoria render <slug> --version V2
editoria contact-sheet <slug> --version V2 --every 2
editoria qc <slug> --version V2
```
Mirá la hoja en los tiempos tocados **y en los vecinos** (para detectar efectos colaterales) y leé `qc/qc.md`. Compará con V1: lo aprobado debe seguir igual. Corregí FAIL antes de entregar.

### 7. Entregar
```
editoria deliver <slug> --version V2
```
Presentá:
1. Lista de cambios aplicados, cada uno con su tiempo.
2. Lo que se conservó.
3. Lo que **no** se aplicó y por qué, o lo que quedó pendiente de aclaración.
4. Resultado del QC y puntos de `REVISIÓN HUMANA`.
5. Rutas del video y del paquete.

Cerrá con la pregunta de feedback del prompt y **detenete**:

> ¿Qué querés ajustar en las tomas, el ritmo, los subtítulos, los gráficos o el sonido? Podés indicarme el minuto/segundo y el cambio.

## Errores frecuentes

- Editar la V1 entregada "para ir más rápido".
- Rehacer toda la edición por un comentario puntual.
- Cambiar tiempos del video base para acomodar un efecto.
- Aceptar una toma generada sin veredicto, o gastar créditos sin límite.
- Declarar aplicado un cambio que no verificaste en el render.
