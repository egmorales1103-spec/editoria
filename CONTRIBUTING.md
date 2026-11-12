# Cómo contribuir a EditorIA

Gracias por querer aportar. Este documento explica cómo preparar el entorno, las reglas del repositorio y cómo agregar una **plantilla de gráficos** o un **estilo**. Al participar aceptás el [Código de conducta](CODE_OF_CONDUCT.md).

## Idioma

- Documentación, mensajes de la CLI y textos para personas: **español**.
- Código, nombres, docstrings, claves de esquema y enums internos: **inglés**.
- Identificadores que escribe quien usa la herramienta (plantillas, estilos, veredictos `aceptado/reintentar/descartado`): español.

## Entorno de desarrollo

```bash
uv sync --all-extras
uv run playwright install chromium
uv run python scripts/fetch_assets.py
uv run pre-commit install
```

Comandos habituales:

```bash
uv run pytest -m "not slow and not network"      # suite rápida (genera tests/.fixtures la primera vez)
uv run ruff check . && uv run ruff format --check .
uv run mypy
```

Reglas técnicas: Python ≥ 3.11 con tipado completo, ruff con línea de 100, tests sin red (marcadores `slow`, `e2e`, `network`), toda llamada a FFmpeg a través de `editoria.util.ffmpeg`, rutas de proyecto a través de `ProjectContext`. Más detalle en [CLAUDE.md](CLAUDE.md) y [docs/arquitectura.md](docs/arquitectura.md).

## Reglas del repositorio

1. **Sin medios de terceros ni datos personales.** No se versionan videos, imágenes, GIF ni audio, salvo `assets/sfx/` (SFX propios), `docs/img/` (capturas propias o sintéticas) y `templates/graphics/*/preview.png`. No incluyas nombres de personas, cuentas, correos ni teléfonos reales. `pre-commit` y `tests/repo/` lo verifican.
2. **Licencias claras.** Todo asset incluido necesita licencia compatible declarada en `assets/sfx/manifest.yaml` o `assets/externos.yaml`. Si es de terceros, lo normal es **descargarlo** con `scripts/fetch_assets.py` y no vendorizarlo.
3. **Sin secretos.** Las claves van en `.env` (no se versiona).
4. **Las reglas del producto no se debilitan.** No agregues comandos de publicación, formas de gastar créditos sin límite, ni maneras de escribir en `00_original/`. Ver [docs/politicas.md](docs/politicas.md). Toda regla nueva se implementa como chequeo, con un test positivo y uno negativo.
5. **Commits** con [Conventional Commits](https://www.conventionalcommits.org/es/): `feat(captions): ...`, `fix(render): ...`, `docs: ...`.

## Pull requests

- Una idea por PR, con descripción de qué cambia y por qué.
- Los tests y linters pasan localmente; la CI corre en Ubuntu y Windows con Python 3.11 y 3.12.
- Si tocás esquemas o contratos (`schemas/`, `contracts.py`), explicá el impacto y regenerá `schemas/json/` con `uv run python -m editoria.schemas.export`.
- Completá la plantilla de PR.

## Crear una plantilla de gráficos

Las plantillas son HTML/CSS que se renderiza con Playwright ([ADR-0001](docs/adr/0001-motor-de-graficos.md)). Cada una vive en `templates/graphics/<id>/`, con `<id>` en minúsculas y con guion bajo (por ejemplo `linea_tiempo`).

```
templates/graphics/<id>/
├─ template.html          marcado y estilos; las animaciones solo con CSS o Web Animations API
├─ params.schema.json     JSON Schema de los parámetros (con textos de error claros)
├─ meta.yaml              metadatos
└─ preview.png            (opcional) vista previa; es el único PNG permitido en el repo
```

`meta.yaml` incluye: `id`, `nombre`, `descripcion`, `size: [ancho, alto]` (el contenido visible, no el cuadro completo), `bleed` (margen transparente para que las sombras no se corten; 56 si la plantilla tiene tarjetas con sombra, ver [docs/modulos/graficos.md](docs/modulos/graficos.md), donde también se explica el ajuste automático del texto largo con `--k`), `duracion_s`, `zonas` permitidas, `sfx_sugerido` y `etiquetas_obligatorias` (por ejemplo "Ejemplo" o "Ilustración").

Criterios que se revisan:

- **Determinismo:** prohibidos `setTimeout`, `setInterval` y `requestAnimationFrame`. El motor pausa las animaciones y fija el tiempo cuadro a cuadro.
- **Sin red:** ninguna fuente, imagen ni script externo. Las fuentes salen de `assets/fonts/` y los colores de las variables CSS de la marca (`--brand-primary`, `--brand-accent`, `--brand-text`, `--brand-bg`; confirmá los nombres en las plantillas existentes).
- **Fondo transparente** y legible sobre video claro u oscuro.
- **Honestidad:** si muestra datos, exigí `data_source` (`real | ejemplo`) y mostrá "Ejemplo"; si recrea una interfaz, rotulala "Ilustración"; no uses marcas de terceros.
- **Densidad:** una idea por plantilla.
- Probala con `uv run editoria graphics preview <id> --params '{...}'`.
- Agregá el id a `allowed_templates` de los estilos donde corresponda (`styles/`) y un test de render (mismo hash en dos renders, canal alfa, parámetros inválidos con error claro).

Usá la plantilla de issue "Plantilla nueva" para proponerla antes de implementarla.

## Crear o modificar un estilo

Un estilo es un archivo `styles/<ID>_<nombre>.yaml` validado por el esquema `StylePreset` (`src/editoria/schemas/style.py`). Campos principales: `id`, `name`, `description`, `references`, `captions`, `editorial_titles`, `graphics` (`allowed_templates`, `max_simultaneous`), `sfx` (`max_per_10s`, `min_spacing_s`, `allowed_cues`) y `reframe` (`cadence_s`, `max_zoom`).

**Limitación de v0.1:** el esquema solo admite los identificadores `A`, `B` y `C`. Un estilo "nuevo" hoy es una variante de uno de esos tres; sumar identificadores requiere un cambio de contrato (abrí un issue "Estilo nuevo" para discutirlo).

Para un estilo:

1. Copiá uno existente y ajustá los valores.
2. Describí en `references` y `description` los patrones R/W que lo inspiran. Los patrones están en [references/patrones.yaml](references/patrones.yaml): **solo texto**. No adjuntes videos, capturas ni enlaces a publicaciones de terceros, ni nombres de sus autores.
3. Validá: `uv run pytest tests/test_schemas.py`.
4. Mantené la densidad razonable: el linter exige que los límites de gráficos y SFX estén definidos. Un estilo que satura la pantalla no se acepta.

## Crear una marca

Copiá `brands/_plantilla/` a `brands/<tu-marca>/` y completá `brand.yaml`. No inventes una identidad oficial: dejá `provisional: true` si faltan logo, colores o tipografías. Incluí `glossary` (términos para la transcripción) y `forbidden_claims` (frases que no pueden aparecer en gráficos ni títulos).

## Referencias

Para agregar un enlace a `references/web.yaml`, indicá id, categoría, URL y una nota propia. No copies el contenido del recurso ni garantices su licencia.

## Dudas

Abrí un issue con la plantilla que corresponda. Para temas de seguridad, ver [SECURITY.md](SECURITY.md).
