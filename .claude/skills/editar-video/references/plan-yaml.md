# Referencia de `plan.yaml` (schema `editoria/plan@1`)

El plan es declarativo: el render es función del plan y los medios. Los esquemas son estrictos (claves desconocidas = error). Ubicación: `proyectos/<slug>/04_versiones/Vn/plan.yaml`.

```yaml
schema: editoria/plan@1
version: V1
style: A                       # A | B | C
brand: master-solution
canvas: {width: 1080, height: 1920, fps: source}
video:                         # cubre el VIDEO_BASE: sin solapes, dentro de [0, duración]
  - {id: v01, in: 0.00, out: 2.40, method: original}
  - {id: v02, in: 2.40, out: 4.10, method: reframe, zoom: 1.10, anchor: face, motion: cut}
  - {id: v03, in: 9.80, out: 12.30, method: generated, shot: G01}   # solo con veredicto aceptado
captions:
  style: A
  emphasis: [{word: 14}, {word: 37, color: accent}]   # índices en transcript.json
  editorial_titles: []                                 # textos que NO se dicen; estilo distinto
graphics:
  - {id: g01, template: palabra_clave, in: 0.30, out: 2.10, zone: upper, params: {texto: "Automatizá"}}
  - {id: g02, template: dato_grafico, in: 14.0, out: 17.5, zone: middle,
     params: {tipo: barras, valores: [40, 75], etiquetas: ["Antes", "Después"], data_source: ejemplo}}
  - {id: e01, emoji: E01, in: 6.2, out: 7.4, zone: upper_right}
sfx:
  - {cue: pop, at: 0.30, gain_db: -14, ref: g01}
  - {cue: whoosh, at: 2.38, gain_db: -16, ref: v02}
music: null
mix: {target_lufs: -14, true_peak_db: -1.0, duck_db: -10}
notes: "Propuesta A recomendada porque…"
```

## Campos

- `video[]`: `id`, `in`, `out` (segundos del VIDEO_BASE, `out > in`), `method` (`original | reframe | generated`). Reencuadre: `zoom` ≥ 1.0 (moderado, ≤ `max_zoom` del estilo; más de 1.25× sobre píxeles nativos es ERROR), `anchor` (`face | center | point`; con `point` agregá `point: [x, y]` normalizado 0..1), `motion` (`cut` punch-in o `push` lento). `generated` exige `shot`.
- `captions`: `style`, `emphasis[] {word, color?}` (token `primary|accent|text|bg` o `#RRGGBB`), `editorial_titles[] {text, in, out, zone}`, `enabled`.
- `graphics[]`: exactamente uno de `template` o `emoji`; `in`, `out`, `zone`, `params`.
- `sfx[]`: `cue` (`pop | click | whoosh | ding | teclado | impacto_suave`), `at`, `gain_db`, `ref?`, `variant?` (1–3).
- `music`: `{path, asset_id, gain_db}` con `asset_id` en un manifest con licencia; o `null`.
- `mix`: loudness objetivo, true peak y ducking.
- `notes`: razones de las decisiones.
- `window: [a, b]`: solo en planes de propuesta (muestras).

## Parámetros de las plantillas de gráficos

| Plantilla | `params` |
|---|---|
| `titulo_gancho` | `texto`, `subtitulo?` |
| `palabra_clave` | `texto` |
| `checklist` | `items` (1–5), `titulo?` |
| `chat_burbujas` | `mensajes: [{lado: izq\|der, texto}]` (1–4) |
| `notificacion` | `app` (genérico), `titulo`, `texto` |
| `dato_grafico` | `tipo: barras\|contador`, `valores`, `etiquetas?`, `unidad?`, `data_source: real\|ejemplo` (obligatorio) |
| `anotacion` | `tipo: flecha\|circulo`, `x`, `y` (0–1), `texto?` |
| `comparacion` | `antes`, `despues`, `titulo?` |
| `ui_demo` (opcional) | `titulo`, `pasos` — se rotula "Ilustración" |
| `cta_cierre` (opcional) | `texto`, `accion?` |

Confirmá la lista real con `editoria graphics list`: es la fuente de verdad.

## Reglas del linter que más se ven

`SCHEMA` (formato), `P04` (intervalos y tiempos), `P05` (toma generada sin veredicto), `P07` (zoom), `P13` (títulos editoriales indistinguibles), `P14` (datos sin `data_source`), `P16` (densidad: elementos simultáneos, SFX por 10 s, separación mínima, cues y plantillas no permitidos por el estilo), `P17` (assets sin licencia), `BRAND` (claims prohibidos). Detalle en `docs/politicas.md`.
