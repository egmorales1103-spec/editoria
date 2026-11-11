# Módulo `shots`: tomas complementarias

Prepara, importa, compara y registra tomas generadas en Higgsfield (modo manual asistido; ver
[`docs/higgsfield.md`](../higgsfield.md)). Código: `src/editoria/shots/`.

## Flujo

```
shots pack → (ejecutás en Higgsfield) → shots import → shots compare → shots verdict
```

| Comando | Qué hace |
|---|---|
| `shots pack <slug> --in a --out b --cambio "..." [--reintento-de G01]` | Asigna el id (G01, G02…), recorta el segmento con re-codificación precisa (CRF 16), extrae anclas de inicio, medio y fin, arma el prompt de la sección 7 del prompt maestro con el cambio y las restricciones negativas, escribe `pack.md` con los pasos manuales y una fila `pendiente` en el registro. |
| `shots import <slug> <id> <archivo> [--funcion] [--ajustes] [--costo] [--reemplazar]` | Valida y conforma el resultado: lienzo 1080×1920 con `util.geometry.base_transform`, FPS del original, `yuv420p`, **sin audio** (P03). Más largo que el segmento: recorta. Más corto u otro aspecto: rechaza. |
| `shots compare <slug> <id>` | Hoja original/candidato (inicio, medio, fin, mayor movimiento), video lado a lado y métricas del fondo. Recomienda; no decide. |
| `shots verdict <slug> <id> aceptado\|reintentar\|descartado --motivo "..."` | Única vía para aceptar. Opcionales: `--fondo --identidad --manos --sincronia` (revisión humana). |
| `shots budget <slug> [--registrar N --detalle "..."]` | Límite, gastado y restante. |
| `shots list <slug>` | Tomas y veredictos. |

## Archivos (dentro de `proyectos/<slug>/02_tomas/`)

- `higgsfield/paquetes/<id>/`: `segmento.mp4` (con audio, es lo que se sube), `ancla_*.png`,
  `prompt.txt`, `pack.md`, `meta.json`.
- `higgsfield/resultados/<id>/`: `recibido.<ext>` (copia tal cual del archivo importado, puede
  traer audio; no se usa) y `conformado.mp4` (silencioso, lienzo, FPS: es el que usa el render).
- `comparativas/<id>/`: `hoja_<id>.jpg`, `lado_a_lado_<id>.mp4`, `referencia.mp4`,
  `metricas.json`, `informe.md`.
- `registro_generaciones.csv`: columnas exactas `REGISTRO_COLUMNS`. Solo datos reales: `costo_mostrado`,
  `funcion_modelo_real` y `ajustes_mostrados` quedan vacíos si nadie los informó. No hay columna de
  semilla; si la herramienta la muestra, va en `--ajustes`.

## Reglas que hace cumplir

- P03: `import` descarta el audio y verifica con ffprobe que el conformado no lo tiene.
- P05/P24: solo `shots verdict` marca `aceptado`, y exige un resultado importado en disco.
  `ProjectShotLibrary.accepted(ctx)` devuelve únicamente esas tomas (como `ConformedClip`; `start`
  y `end` son `entrada`/`salida` en la línea de tiempo del VIDEO_BASE).
- P08: el prompt lleva las restricciones negativas; `pack` avisa si el cambio pedido menciona
  fondo nuevo, órbitas, relighting, outpainting o ropa; `compare` mide la deriva del fondo.
- P09: `ensure_budget(ctx, cost)` lanza `BudgetError` si no hay límite o se excedería. Gastado =
  el mayor entre `logs/creditos.jsonl` y `budget.spent` de `proyecto.yaml`.
- Intentos: cada reintento es un id nuevo (`--reintento-de`) con `attempt` +1. `reintentar` y
  `pack --reintento-de` respetan `tool_limits.max_attempts`.
- Los límites de la herramienta salen de `proyecto.yaml`; nada está fijo en el código.

## Métricas de `compare`

El fondo es el lienzo menos la caja de rostro (unión de las muestras alrededor del segmento,
pasada a lienzo con `base_transform`) dilatada 80 px. Original y candidato se conforman con la
misma transformación.

| Métrica | Cómo se mide | Estable | Deriva |
|---|---|---|---|
| SSIM del fondo | filtro `ssim` de ffmpeg sobre 4 recortes alrededor del rostro, ponderado por área | ≥ 0,90 | < 0,75 |
| Parpadeo | RMS del cambio extra de luma media del fondo entre cuadros (0–255) | ≤ 3 | > 8 |
| Diferencia de color | CIELAB dE76 entre colores medios del fondo | ≤ 5 | > 10 |

Entre ambos extremos la recomendación es `revisar`. Los umbrales son constantes de
`shots/compare.py`, calibradas con los fixtures sintéticos: **no están validadas con video real**
y deben ajustarse con material de un proyecto. Las métricas no miden identidad, piel, manos,
bordes ni sincronía labial.

## Limitaciones conocidas

- No hay cliente de API (ver `docs/higgsfield.md`).
- La sincronía labial no se verifica automáticamente.
- Un resultado de aspecto distinto al del segmento enviado se rechaza; uno de otra resolución se
  escala (con recorte alrededor del rostro si el original es horizontal).
- Si falta `rostro.json`, el "fondo" es todo el lienzo y el rostro también cuenta.
