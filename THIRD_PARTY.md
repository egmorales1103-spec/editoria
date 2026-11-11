# Componentes de terceros

EditorIA no redistribuye videos, fotogramas ni plantillas de terceros. Este documento lista las dependencias y los recursos externos que usa, con su licencia, y cómo se obtienen. Los datos de licencia son los declarados por cada proyecto a la fecha de esta versión; antes de cada release se deben contrastar con `uv.lock` y con los metadatos de cada paquete.

Licencias propias: código Apache-2.0 (`LICENSE`); prompts, documentación, plantillas y estilos CC BY 4.0 (`LICENSE-docs`); efectos de sonido generados por el proyecto CC0 1.0. Ver [ADR-0004](docs/adr/0004-licencias.md).

## Binarios externos (no se distribuyen)

| Componente | Cómo se usa | Licencia |
|---|---|---|
| **FFmpeg** y **ffprobe** | Se invocan como **programas externos** que instala el usuario (winget, brew, apt); EditorIA no los incluye, no los enlaza ni los distribuye | LGPL 2.1+ o GPL 2+ según la compilación (las compilaciones completas suelen ser GPL). Al no distribuirse con el proyecto, sus obligaciones no se trasladan a EditorIA |
| **Chromium** (vía Playwright) | `playwright install chromium` lo descarga en la caché del usuario; se usa headless para renderizar plantillas | BSD-3-Clause y licencias de sus componentes (ver chromium.org/chromium-os/licensing) |

## Dependencias de Python

### Núcleo

| Paquete | Licencia |
|---|---|
| typer | MIT |
| rich | MIT |
| pydantic | MIT |
| pyyaml | MIT |
| numpy | BSD-3-Clause |
| pillow | MIT-CMU (HPND) |
| jinja2 | BSD-3-Clause |
| httpx | BSD-3-Clause |
| jsonschema | MIT |

### Opcionales (extras)

| Extra | Paquete | Licencia | Notas |
|---|---|---|---|
| `transcribe` | faster-whisper | MIT | Usa CTranslate2 (MIT), ONNX Runtime (MIT), tokenizers y huggingface-hub (Apache-2.0) y PyAV (BSD-3-Clause; sus ruedas incluyen bibliotecas de FFmpeg bajo LGPL) |
| `graphics` | playwright | Apache-2.0 | Descarga Chromium aparte |
| `analyze` | opencv-python-headless | Apache-2.0 | Sus ruedas incluyen bibliotecas de FFmpeg bajo LGPL 2.1 |

### Desarrollo

| Paquete | Licencia |
|---|---|
| pytest | MIT |
| ruff | MIT |
| mypy | MIT |
| respx | BSD-3-Clause |
| pre-commit | MIT |
| types-PyYAML, types-jsonschema | Apache-2.0 |

Las dependencias transitivas (por ejemplo click, anyio, h11, httpcore, certifi, markupsafe, referencing, tqdm) mantienen sus propias licencias permisivas; el listado completo está en `uv.lock`.

## Modelos de transcripción

| Modelo | Licencia | Obtención |
|---|---|---|
| Whisper (`large-v3-turbo`, `small`, etc., en formato CTranslate2) | MIT (modelos de OpenAI Whisper) | Se descargan desde Hugging Face la primera vez que se transcribe y quedan en la caché del usuario. No se incluyen en el repositorio |

## Recursos descargados por `scripts/fetch_assets.py`

Se descargan a `assets/emoji/` y `assets/fonts/` (ignorados por git) y se verifican con el sha256 de `assets/externos.yaml`.

| Recurso | Licencia | Autor | Fuente |
|---|---|---|---|
| Noto Emoji animados (E01 a E06: 1f4a1, 1f440, 1f525, 1f44f, 1f389, 1f914) | CC BY 4.0 | Google | https://googlefonts.github.io/noto-emoji-animation/ |
| Tipografía Inter v4.1 | SIL Open Font License 1.1 | The Inter Project Authors | https://github.com/rsms/inter |

**Atribución obligatoria (Noto Emoji):** cuando un video use estos emojis, se debe mantener la atribución y señalar las modificaciones (por ejemplo, recorte o escala). Texto sugerido:

> Emojis animados: Google Noto Emoji — CC BY 4.0. https://googlefonts.github.io/noto-emoji-animation/

`editoria deliver` incluye esta atribución en `atribuciones.md` cuando corresponde. Licencia: https://creativecommons.org/licenses/by/4.0/ · Documentación: https://googlefonts.github.io/noto-emoji-files/?view=docs

**Inter (OFL):** no se redistribuye en este repositorio; el script descarga la versión oficial, que incluye el texto de la licencia (`assets/fonts/Inter/OFL.txt`).

## Efectos de sonido

Los SFX de `assets/sfx/` los genera `scripts/gen_sfx.py` de forma determinística (síntesis propia, sin muestras de terceros) y se publican bajo **CC0 1.0**. Su manifest está en `assets/sfx/manifest.yaml`.

## Referencias de estilo

Los enlaces de `references/web.yaml` y los patrones de `references/patrones.yaml` son material de inspiración y **no se incluyen ni se redistribuyen**. Cada recurso web conserva sus derechos y condiciones de uso.

## Marcas

Higgsfield, CapCut, Claude, Instagram, TikTok y otras marcas mencionadas pertenecen a sus titulares. Se nombran solo para describir compatibilidad o flujo de trabajo; EditorIA no está afiliado a ellas ni respaldado por ellas.
