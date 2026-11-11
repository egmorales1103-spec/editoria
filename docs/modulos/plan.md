# Módulo: plan y políticas (`planning/`, `policy/`)

El plan (`plan.yaml`, esquema `editoria/plan@1`) describe toda la edición de forma declarativa.
Este módulo genera un **borrador automático** por estilo y verifica cualquier plan con un
**linter de políticas** que traduce las reglas del prompt a chequeos ejecutables.

## Comandos

```bash
editoria plan draft <slug> --style A [--out ruta] [--window 2-9.5]
editoria plan lint  <slug> [--plan ruta | --version V1]
```

- `plan draft` escribe por defecto `03_propuestas/plan_<estilo>.yaml`, imprime los hallazgos del
  linter y termina con código 1 si el borrador tiene algún ERROR. `--out` rechaza destinos dentro
  de una versión entregada (`.entregado`) o de cualquier carpeta `00_original/`. El borrador es
  determinista: el mismo proyecto y estilo producen el mismo archivo.
- `--window a-b` limita video, gráficos y SFX a la ventana de muestra (propuestas A/B/C sobre el
  mismo pasaje). Los subtítulos siempre cubren todo el audio.
- `plan lint` valida el esquema (errores de Pydantic como hallazgos `SCHEMA`) y luego las
  reglas. Imprime una tabla (nivel, regla, tiempo, elemento, mensaje) y devuelve código ≠ 0 si
  hay ERROR.

## Qué hace el borrador

| Elemento | Criterio |
|---|---|
| Subtítulos | Todo el audio, estilo del preset. |
| Énfasis | Términos del glosario de la marca (frases de varias palabras incluidas) y cifras; como máximo uno por segundo. |
| Gráficos (distintos por estilo, §8) | **A**: `palabra_clave` con el término del glosario del gancho (si no hay, `titulo_gancho`). **B**: `titulo_gancho` con las primeras palabras del gancho + `checklist` con 2–3 frases cortas tomadas literalmente de segmentos de desarrollo (`body`/`example`) seguidos, en la mitad del lienzo sin rostro. **C**: `titulo_gancho` en mayúsculas con la frase del gancho + un emoji animado (E03 fuego, o E01 idea) en el segmento de cierre, solo si figura con licencia en `assets/externos.yaml`. Todo texto sale de la transcripción o de los segmentos; los segmentos con cifras no se convierten en ítems; solo plantillas permitidas por el estilo y nunca con claims prohibidos de la marca. |
| Reencuadres | Alternan original/reencuadre en los inicios de segmento (cambios de idea) cuando pasó ~`cadence_s` (75 %) desde el último cambio. Un reencuadre **se cierra siempre en el siguiente corte de cámara** de `cortes.json`; se descartan los menores a 1,5 s. Zoom = mín(`max_zoom` del estilo, 1,25 / escala base) para no prometer detalle nativo; ancla `face` si hay rostro detectado, `center` si es estimado. |
| SFX | Solo en la entrada de cada gráfico (`pop` o el `sfx_sugerido` de la plantilla) y al inicio de cada reencuadre (`whoosh`), respetando `allowed_cues`, `min_spacing_s` y `max_per_10s`. Si el SFX no figura con licencia en `assets/sfx/manifest.yaml`, se omite y queda anotado en `notes`. |

Python: `DefaultPlanTools().draft(ctx, style, window=None)` y `.lint(plan, ctx)`;
`editoria.planning.draft_plan()`; `editoria.policy.lint_plan(plan, ctx)` y `has_errors()`.

## Reglas del linter

| Id | Nivel | Qué verifica |
|---|---|---|
| `SCHEMA` | ERROR/WARN | Validación Pydantic; ids repetidos; plantilla inexistente o parámetros inválidos (`params.schema.json` de la plantilla o tabla interna); emoji fuera de E01–E06; énfasis fuera de la transcripción; reencuadre sin `zoom` > 1; estilo o marca inexistentes (ERROR). `captions.style` distinto del estilo del plan y `ref` de SFX inexistente (WARN). |
| `P04` | ERROR/WARN | Intervalos dentro de `[0, duración]` (tolerancia 1 cuadro), sin solapes en la pista de video; gráficos, títulos y SFX dentro de la duración; ventana válida (ERROR). Reencuadre o toma generada que cruza un corte de cámara (WARN). Sin `probe.json` (ERROR: sin duración no se puede garantizar que nada pase del final; ejecutar `editoria probe`). |
| `P05` | ERROR | `method: generated` cuya toma no figura con veredicto `aceptado` en `02_tomas/registro_generaciones.csv`. |
| `P07` | ERROR/WARN | Zoom × escala base > 1,25 sobre píxeles nativos (ERROR); zoom > `max_zoom` del estilo (WARN). |
| `P13` | ERROR/WARN | Títulos editoriales con la misma tipografía que los subtítulos (fuente, peso, tamaño, mayúsculas o contorno) (ERROR); título que repite lo que se dice (WARN). |
| `P14` | ERROR/WARN | `dato_grafico` sin `data_source: real|ejemplo` (ERROR); cifras o porcentajes en otras plantillas sin `data_source` (WARN). |
| `P16` | ERROR | Gráficos/emojis simultáneos > `max_simultaneous`; plantilla fuera de `allowed_templates`; cue fuera de `allowed_cues`; SFX con separación < `min_spacing_s` o más de `max_per_10s` en 10 s. |
| `P17` | ERROR | SFX (`<cue>_<variante>`), emoji o música sin licencia en `assets/sfx/manifest.yaml` / `assets/externos.yaml`. |
| `BRAND` | ERROR/WARN | Claims prohibidos de la marca en textos de gráficos o títulos (ERROR); marca del plan distinta de la del proyecto (WARN). |

P07 completo (guarda en el render) y P12 (subtítulos sobre el rostro en el video final) los
verifican render y QC.
