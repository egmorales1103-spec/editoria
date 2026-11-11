# Higgsfield en EditorIA

EditorIA trabaja con Higgsfield en **modo manual asistido**: la CLI prepara el paquete (segmento,
fotogramas ancla, prompt, pasos), vos ejecutás en la herramienta, y la CLI importa, compara y
registra el resultado. No hay integración automática con la API.

## Qué está verificado

Última lectura de la documentación pública: 11 de noviembre de 2026
(`https://docs.higgsfield.ai/docs` y `https://docs.higgsfield.ai/docs/models.md`). Es lectura de
documentación; **no se llamó a la API** ni se gastó ningún crédito.

- La API tiene como base `https://api.higgsfield.ai`.
- La autenticación documentada usa un encabezado `Authorization: Key <id>:<secreto>` (par de
  clave e identificador creado en la consola de Higgsfield). Ojo: `.env.example` menciona
  `HIGGSFIELD_API_KEY`, un nombre propio del proyecto que no coincide con ese esquema.
- Los envíos son `POST` a una ruta específica de cada modelo (ejemplos de la documentación:
  `/higgsfield/genjutsu/motion-transfer/v1.0` y `/higgsfield-ai/soul/v2/standard`). La respuesta
  inmediata trae `status: queued`, `request_id`, `status_url` y `cancel_url`
  (`https://api.higgsfield.ai/requests/{request_id}/status`).
- El cuerpo de cada petición depende del modelo ("los campos varían por modelo y flujo").

## Qué NO está verificado

- **Ningún modelo de video a video** que conserve identidad, fondo y labios. La documentación
  lista familias (Genjutsu, Seedance, Kling, Wan, entre otras) pero no indica cuáles editan un
  video existente; las únicas rutas de ejemplo que reciben un video no están descritas como tales.
- **Ningún endpoint de estimación de costo.** La documentación leída no lo menciona; tampoco
  precios ni costos en créditos.
- El método HTTP de consulta de estado y de cancelación (la página no lo indica).
- Límites reales de duración, resolución y número de intentos de cada modelo.
- Qué funciones admite tu cuenta hoy: cambian con el tiempo. Se comprueban al ejecutar.

## Por qué no existe `shots api`

El brief pedía un cliente experimental (`shots api estimate|submit|status|download`) **solo si**
se podían verificar el endpoint y el modelo concretos. No se pudo: falta un modelo de video a
video confirmado y un endpoint de estimación. Construirlo sería inventar rutas, parámetros y
costos, y un envío equivocado gastaría créditos reales. Por eso **no está implementado**.

Lo que sí queda listo para cuando se verifique:

- `editoria.shots.ensure_budget(ctx, cost)` y `record_credit(ctx, amount, detail)`: la guarda de
  presupuesto reutilizable. Sin límite autorizado en `proyecto.yaml` (`budget.limit`) bloquea todo.
- `shots import` ya acepta cualquier archivo descargado y lo valida y conforma.

Para retomarlo: verificar el modelo y la ruta en `docs.higgsfield.ai`, definir el flujo
estimar → `ensure_budget` → enviar → consultar → descargar → `shots import`, sin reintentos
automáticos que gasten, con pruebas `respx`, apagado por defecto (`EDITORIA_HIGGSFIELD_API=1`).

## Funciones, modelos y costos: se comprueban al ejecutar

- EditorIA **no fija** nombres de modelos, botones ni capacidades.
- La función/modelo real, los ajustes y el costo los muestra la herramienta: se anotan tal cual
  con `shots import --funcion "..." --ajustes "..." --costo N`.
- Si nadie informó un dato (por ejemplo la semilla o el costo), queda **vacío** en
  `registro_generaciones.csv`. Nunca se rellena con un valor inventado.
- Los límites de la herramienta (`tool_limits.higgsfield_max_clip_s`, `tool_limits.max_attempts`)
  salen de `proyecto.yaml`. Si están vacíos, el `pack.md` indica "verificar en la herramienta".

## Créditos (P09)

- Sin límite autorizado en `proyecto.yaml` no se debe ejecutar nada que consuma créditos. Se pide
  ese único dato y mientras tanto se avanza con lo local.
- Nunca se compran planes ni créditos.
- `editoria shots budget <slug>` muestra límite, gastado y restante según
  `logs/creditos.jsonl` (formato: una línea JSON con `amount`, `unit`, `detail`). Con
  `--registrar N` se anota un consumo ya ocurrido.
- Se sube a Higgsfield únicamente `segmento.mp4` del paquete: ni el video completo ni carpetas.

## Reglas de revisión

Un resultado generado nunca entra al video sin veredicto `aceptado` (P05), y el audio del
resultado siempre se descarta (P03). `shots compare` mide solo la deriva del fondo; identidad,
manos y labios requieren revisión humana (P24). Ante duda visible, se conserva el original.
