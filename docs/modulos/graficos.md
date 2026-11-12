# Módulo de gráficos (motion graphics)

`editoria.graphics` convierte plantillas HTML/CSS en secuencias PNG con canal alfa
(`%05d.png`, desde `00001.png`) que el compositor (`editoria render`) superpone al video.
El render es determinístico, local y sin red.

## Comandos

```bash
editoria graphics list
editoria graphics preview <plantilla> [--params '{json}'] [--out carpeta] [--marca slug]
                          [--fps 30] [--duracion s] [--zona upper|middle|lower|...]
editoria graphics render <slug> --version V1
```

- `list`: tabla con id, tamaño, duración por defecto, zonas admitidas, SFX sugerido y
  etiquetas obligatorias.
- `preview`: renderiza la plantilla (sin `--params` usa los parámetros de ejemplo de su
  `params.schema.json`) y deja en `--out` (por defecto `./vista_previa/<plantilla>/`):
  `<plantilla>_medio.png` (cuadro medio sobre un lienzo gris 1080×1920, en su zona) y
  `<plantilla>_preview.mp4` (la animación completa sobre gris), además de `cuadros/`.
- `render`: renderiza los ítems de `graphics` del `plan.yaml` que usan `template` (los
  emojis los resuelve el pipeline) en `04_versiones/<V>/graficos/<id>/%05d.png` y escribe
  `graficos/overlays.json` (`{"overlays": [OverlayClip, ...]}`, rutas absolutas). Se niega
  a escribir en una versión entregada.

Códigos de salida: `0` bien, `1` error de uso (JSON o parámetros inválidos, plantilla o
proyecto inexistente), `2` Chromium/Playwright no disponible (el pipeline puede seguir sin
gráficos con un aviso).

## API (Python)

```python
from editoria.graphics import (
    PlaywrightGraphicsRenderer,  # implementa contracts.GraphicsRenderer
    render_plan_graphics,  # (ctx, version) -> list[OverlayClip]
    list_templates,  # -> list[TemplateMeta]
    preview_template,
    load_template,
    GraphicsError,
    GraphicsParamsError,
    GraphicsUnavailable,
    TemplateNotFound,
)
```

`PlaywrightGraphicsRenderer.render(item, brand, canvas, fps, out_dir)` devuelve un
`OverlayClip` con `frames_pattern`, `frame_count = round(duración × fps)`, `x, y, w, h`
(lienzo), `start/end` (línea de tiempo del VIDEO_BASE) y `labels` (por ejemplo
`["Ejemplo"]` o `["Ilustración"]`, leídas del DOM).

## Cómo renderiza

1. Valida los parámetros contra `params.schema.json` (JSON Schema 2020-12) y aplica los
   valores por defecto. Los errores salen en español con la ruta del parámetro.
2. Arma el HTML con Jinja2 (autoescape activado). La plantilla extiende `_base.html`,
   que define los tokens de marca como variables CSS (`--color-primary`, `--color-accent`,
   `--color-text`, `--color-bg`, `--color-on-accent`, `--font-heading`, `--font-body`),
   la duración del ítem (`--dur`) y la salida suave común (`.stage`). Los parámetros
   también quedan como JSON en `#editoria-params`.
3. Fuentes: busca la familia de la marca en `assets/fonts/` (recursivo) y la incrusta como
   `data:` URI. Si no está, usa la del sistema y avisa una vez.
4. Abre una página de Chromium headless con viewport **del tamaño de la plantilla** (no
   del lienzo), escala `canvas.width / 1080` y fondo transparente. **Toda solicitud
   http/https se aborta** (`context.route`) y se informa con un aviso.
5. Pausa todas las animaciones (`document.getAnimations()`) y, por cada cuadro, fija
   `currentTime = cuadro / fps × 1000`, llama al gancho opcional `window.editoriaSeek(ms)`
   (lo usa el contador de `dato_grafico`), espera dos cuadros de composición (lo hace el
   renderizador, no la plantilla) y captura `screenshot(omit_background=True)`. Chromium
   se lanza sin animaciones en hilo aparte (`--disable-threaded-animation`, etc.): sin
   esto, los bordes de capas semitransparentes en movimiento variaban entre corridas.
6. Comprueba que estén en el DOM las `etiquetas_obligatorias` de `meta.yaml`.
7. Guarda `.editoria_render.json` con el hash de entrada (plantilla + `_base.html` +
   parámetros + marca + fps + tamaño + duración + fuentes). Si el hash coincide y están
   todos los cuadros, no vuelve a renderizar.

Un solo Chromium por proceso (la API sync de Playwright admite una instancia por hilo),
compartido por todos los renderizadores; una página por ítem.

Rendimiento medido (Windows 11, Chromium 158 headless, 1080×1920 a 30 fps, biblioteca
completa con sus parámetros de ejemplo): 50–70 ms por cuadro según la plantilla
(meta: ≤ 150 ms). `graphics render` y `graphics preview` informan los ms por cuadro.

## Ubicación

- Plantillas por zona: `util.geometry.zone_box(zona, lienzo, w, h)` dentro del área segura.
  Si el plan pide una zona que la plantilla no admite, se usa la primera admitida (aviso).
- `anotacion` (`ubicacion: punto` en `meta.yaml`): la caja se centra en `x, y` (0–1 del
  lienzo) y se recorta a los bordes; la flecha o el texto apuntan hacia el centro.

## Contrato de una plantilla

```
templates/graphics/<id>/
├─ template.html         # {% extends "_base.html" %} + bloques style / body / script
├─ params.schema.json    # JSON Schema; additionalProperties: false; examples[0] = ejemplo
└─ meta.yaml             # id, nombre, descripcion, size [w, h], bleed, duracion_s, zonas,
                         # sfx_sugerido, etiquetas_obligatorias, ubicacion (zona|punto)
```

**`size` y `bleed`.** `size` es el contenido visible. `bleed` (px CSS, por defecto 0) es un
margen transparente que se agrega por los cuatro lados para que las sombras no se corten en
el borde de la imagen: el PNG mide `size + 2·bleed`. El renderer corre la imagen hacia
afuera, así el contenido visible queda exactamente donde lo pone la zona. `_base.html` ya
inscribe `.stage` dentro del margen (`inset: var(--bleed)`), de modo que `position: absolute;
inset: 0` dentro de la plantilla sigue refiriéndose al contenido visible. Las plantillas con
tarjetas usan `bleed: 56`; la sombra estándar (`--shadow`) llega a 36 px a los lados, 50 abajo y
22 arriba. Si definís una sombra más grande, subí el `bleed` en consecuencia.

**Texto largo: ajuste automático.** La caja de una plantilla tiene tamaño fijo, pero el
texto que recibe no. Las plantillas con texto libre (`chat_burbujas`, `checklist`,
`titulo_gancho`, `dato_grafico`) escalan su tipografía y sus espacios con la variable
`--k` (1 = tamaño de diseño) y el renderer la baja de a 2,5 % hasta que el contenido entra:

```html
<style> .panel { padding: calc(44px * var(--k)); font-size: calc(42px * var(--k)); } </style>
{% block script %}
<script>window.editoriaFit = () => window.editoriaFitTo({target: '.panel'});</script>
{% endblock %}
```

`editoriaFitTo({target, padY, check, min})` mide en el navegador real (no estima por
cantidad de caracteres, así que funciona con cualquier tipografía de marca). `target` debe ser
un elemento de alto automático dentro de la caja; `check` agrega una condición propia (por
ejemplo, que un número no se salga de su columna); `min` es la escala mínima (0,55 por
defecto). El renderer llama a `editoriaFit()` una sola vez, con las fuentes ya cargadas y
antes del primer cuadro, así que el resultado no cambia entre cuadros ni entre corridas. Con
el contenido de ejemplo `--k` queda en 1: el diseño normal no se toca. Si ni con la escala
mínima entra, el renderer avisa («el contenido no entra en su caja») y el texto se corta.

Reglas (las verifican los tests):

- Solo animaciones/transiciones CSS o WAAPI. Prohibidos `setTimeout`, `setInterval`,
  `requestAnimationFrame` y `requestIdleCallback`. Para valores que cambian con el tiempo
  (contadores) se define `window.editoriaSeek = (ms) => {...}`, función pura del tiempo.
- Nada remoto: ni `http(s)://` ni `//` en `src`, `href` o `url()`.
- Todas las animaciones arrancan en t = 0 (usar `animation-delay`); la salida se programa
  con `calc(var(--dur) - var(--t-out))` (ya la aplica `.stage`).
- No usar `display: none` para ocultar elementos animados (no aparecen en
  `getAnimations()`); usar opacidad.
- Etiquetas de procedencia: un elemento con `data-editoria-label="Ejemplo"` (o
  `"Ilustración"`) visible durante todo el gráfico.

## Biblioteca v0.1

| id | parámetros | notas |
|---|---|---|
| `titulo_gancho` | `texto`, `subtitulo?` | palabra por palabra, barra de acento |
| `palabra_clave` | `texto` | pastilla de acento con rebote suave |
| `checklist` | `items` (1–5), `titulo?` | ítems que se marcan en secuencia |
| `chat_burbujas` | `mensajes: [{lado: izq\|der, texto}]` (1–4) | conversación genérica |
| `notificacion` | `app`, `titulo`, `texto` | genérica: inicial de la app, sin logos de terceros |
| `dato_grafico` | `tipo: barras\|contador`, `valores`, `etiquetas?`, `unidad?`, `titulo?`, `data_source: real\|ejemplo` | con `ejemplo`, etiqueta "Ejemplo" visible siempre (P14) |
| `anotacion` | `tipo: flecha\|circulo`, `x`, `y` (0–1), `texto?` | se ubica por coordenadas |
| `comparacion` | `antes`, `despues`, `titulo?` | tarjetas lado a lado |
| `ui_demo` | `titulo`, `pasos` (1–5) | etiqueta "Ilustración" obligatoria (P15) |
| `cta_cierre` | `texto`, `accion?` | cierre con botón |

`dato_grafico` acepta además `titulo?` (opcional), que no figuraba en la tabla de
convenciones; es compatible con los planes existentes.

## Limitaciones conocidas

- El determinismo está verificado en la misma máquina y versión de Chromium (3 corridas de
  las 10 plantillas, 0 cuadros distintos). Otra versión de Chromium u otro sistema operativo
  puede cambiar el antialiasing y, por lo tanto, los hashes.
- Sin la fuente de la marca en `assets/fonts/`, el resultado depende de las fuentes del
  sistema (cambia entre máquinas, no entre corridas).
