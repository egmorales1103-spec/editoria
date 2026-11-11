# EditorIA

Edición de reels con IA: una **CLI determinística que edita, verifica y entrega**, más una capa de agentes para Claude Code que la opera como director creativo y editor.

[English summary](README.en.md) · [Arquitectura](docs/arquitectura.md) · [Políticas](docs/politicas.md) · [Guía para Windows](docs/guia-windows.md)

> **Estado: v0.1 en desarrollo.** Funciona sobre un video que ya recortaste en tu editor; no reemplaza a un editor humano ni promete resultados de estudio. Ver [limitaciones](#limitaciones-honestas).

## Qué es

Partís de un video vertical grabado por vos y ya recortado (por ejemplo en CapCut). EditorIA:

1. Lo analiza: metadatos, transcripción local con tiempos por palabra, silencios, cortes y zona del rostro.
2. Te presenta **tres propuestas creativas (A, B y C)** del mismo pasaje, con una muestra breve de cada una y una recomendación.
3. Arma una **V1 completa**: subtítulos, motion graphics a partir de plantillas, efectos de sonido y mezcla.
4. Hace un **control de calidad** automático y entrega el paquete (video, SRT/VTT, plan, mapa de edición, atribuciones).
5. **Se detiene** y espera tu feedback con tiempos concretos para crear V2 sin tocar lo anterior.

La idea central: **el modelo decide; el código ejecuta y verifica.** Las reglas del prompt (no tocar fondo, identidad ni voz; no inventar métricas; no gastar créditos sin límite; esperar feedback tras V1) dejan de ser pedidos de texto y pasan a ser chequeos del linter, del QC y de hooks. Ver [docs/politicas.md](docs/politicas.md).

### Qué garantiza

- El audio de tu video manda: no se sintetiza ni se clona voz.
- El original se guarda con hash y en solo lectura; las versiones entregadas son inmutables.
- No hay comando de publicación: **EditorIA no publica ni envía mensajes**.
- No se gastan créditos de ningún servicio sin un límite que vos autorices, y nunca se compran.
- No se inventan métricas: un dato es real o se rotula "Ejemplo"; una interfaz recreada se rotula "Ilustración".
- Todo recurso usado (SFX, emojis, fuentes) tiene licencia registrada y se atribuye.

## Demo

El repositorio **no incluye videos**. Para ver el flujo sin usar material propio, generá medios sintéticos de prueba (video con patrón de prueba y audio tipo habla):

```bash
uv run python scripts/make_fixtures.py        # crea tests/.fixtures/ (ignorado por git)
uv run editoria init tests/.fixtures/base_1080x1920_30.mp4 --slug demo
uv run editoria transcribe demo --backend fixture
uv run editoria analyze demo
```

El backend `fixture` usa una transcripción de ejemplo, así que no descarga modelos. La demo muestra el flujo, no la estética final.

## Instalación

Requisitos: Python 3.11 o superior (lo instala `uv`), **FFmpeg 6 o superior** con libass y Git. Se necesitan unos 10 GB libres (modelos, Chromium y renders).

### Windows (PowerShell)

```powershell
winget install --id Git.Git -e
winget install --id astral-sh.uv -e
winget install --id Gyan.FFmpeg -e
```

Reiniciá la terminal. Más detalles y solución de problemas en la [guía para Windows](docs/guia-windows.md). Cloná el repo en una carpeta sin espacios (por ejemplo `C:\dev\editoria`).

### macOS

```bash
brew install git ffmpeg uv
```

### Linux (Debian/Ubuntu)

```bash
sudo apt install git ffmpeg
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Verificá que `ffmpeg -version` muestre 6 o más; si tu distribución trae una versión anterior, instalá una compilación reciente.

### Dependencias del proyecto

```bash
git clone <url-del-repositorio> editoria && cd editoria
uv sync --all-extras                 # CLI, transcripción, análisis, gráficos y herramientas de desarrollo
uv run playwright install chromium   # motor de gráficos
uv run python scripts/fetch_assets.py   # emojis Noto e Inter (verificados con sha256, no versionados)
uv run editoria doctor               # comprueba el entorno y explica cómo resolver cada faltante
```

## Inicio rápido en 5 comandos

```bash
uv run editoria init "mi video.mp4" --slug mi-video   # 1. crea el proyecto y copia el original (solo lectura)
uv run editoria transcribe mi-video                   # 2. transcripción local con palabras dudosas marcadas
uv run editoria analyze mi-video                      # 3. silencios, cortes, rostro y segmentos
uv run editoria propose mi-video                      # 4. tres muestras A/B/C y recomendación
uv run editoria run mi-video                          # 5. V1: plan, subtítulos, gráficos, mezcla, QC y entrega
```

Los resultados quedan en `proyectos/mi-video/` (ignorado por git). Mirá `04_versiones/V1/video.mp4`, `qc/qc.md` y `resumen.md`. Después, dejá tu feedback con la plantilla [`Feedback_V1.md`](templates/docs/Feedback_V1.md).

## Uso con Claude Code

Es el uso previsto: un agente decide la dirección creativa y la CLI ejecuta. Abrí Claude Code en la carpeta del repositorio y pedí, por ejemplo:

> Usá `/editar-video` con este VIDEO_BASE: `C:\videos\mi-video.mp4`. Desarrollá la propuesta que recomiendes y esperá mi feedback después de V1.

- La skill `editar-video` ejecuta el flujo completo hasta V1, decide estructura, estilo y gráficos, mira las hojas de contactos y el QC, y **se detiene** con la pregunta de feedback.
- La skill `aplicar-feedback` convierte tus comentarios con tiempos en la versión siguiente sin sobrescribir nada.
- Subagentes: `director-creativo`, `operador-tomas`, `motion-designer`, `disenador-sonido` y `revisor-qc` (solo lectura).
- Hooks de seguridad: bloquean escrituras en `00_original/` y en versiones entregadas, y el envío de generaciones de pago sin presupuesto.

Estructura en [`.claude/`](.claude/) y [arquitectura](docs/arquitectura.md).

## Uso sin Claude Code

- **Solo la CLI:** todos los comandos funcionan solos (`uv run editoria --help`). Podés escribir o editar el `plan.yaml` a mano ([formato](.claude/skills/editar-video/references/plan-yaml.md)) y usar `plan lint`, `render`, `qc` y `deliver`.
- **Solo un chat de IA, sin herramientas:** el [prompt maestro](prompts/prompt-maestro.md) sirve para planificar la edición y preparar instrucciones. No opera editores ni genera video por sí solo. Guía en [docs/uso-con-chat.md](docs/uso-con-chat.md).

## Políticas

Resumen: original intacto, audio base manda, sin publicación automática, sin gasto sin límite, sin métricas inventadas, un paso de feedback tras V1. La tabla completa de 24 reglas con su mecanismo (linter, QC, CLI o hook) está en [docs/politicas.md](docs/politicas.md).

## Tomas generadas con Higgsfield

Son **opcionales** y se manejan en modo manual asistido: `shots pack` prepara el segmento y el prompt, vos lo ejecutás en la herramienta, `shots import` valida el resultado, `shots compare` mide la deriva del fondo y `shots verdict` es la única vía para aceptar una toma. No hay cliente de API en v0.1: no se pudo verificar un modelo de video a video con estimación de costo en la documentación oficial (ver docs/higgsfield.md). Qué está verificado y qué no: [docs/higgsfield.md](docs/higgsfield.md) y [ADR-0003](docs/adr/0003-higgsfield-manual.md). Sin tomas generadas, la V1 se hace con original y reencuadres y se declara así.

## Limitaciones honestas

- **La estética no compite con un editor humano.** La biblioteca de v0.1 tiene ocho plantillas de gráficos y tres estilos. El valor está en el sistema: edición reproducible desde un plan, garantías automáticas y un flujo que entrega V1 y se detiene.
- **No hay verificación automática de identidad, fondo ni sincronía labial.** El QC marca estos puntos como REVISIÓN HUMANA y la deriva del fondo es solo una métrica orientativa.
- **Higgsfield no está verificado de punta a punta.** No se asegura que un modelo preserve identidad, fondo y labios.
- **No exporta proyectos de CapCut** ni de otros editores: entrega video, subtítulos, plan, mapa de edición y capas.
- El reencuadre usa los píxeles existentes: una fuente de baja resolución no gana detalle.
- La transcripción puede equivocarse; las palabras dudosas se marcan y deben revisarse.
- Sin GUI ni versión web; sin publicación en redes; la música no viene incluida.
- La integración continua corre en Ubuntu y Windows, pero la v0.1 se probó sobre todo en Windows.

## Licencias

- Código: [Apache-2.0](LICENSE).
- Prompts, documentación, plantillas y estilos: [CC BY 4.0](LICENSE-docs).
- Efectos de sonido generados por el proyecto: CC0.
- Recursos de terceros (emojis Noto CC BY 4.0, fuente Inter OFL) y dependencias: ver [THIRD_PARTY.md](THIRD_PARTY.md). Se descargan, no se redistribuyen.
- FFmpeg se usa como binario externo y no se distribuye con el proyecto.

El repositorio no incluye videos, fotogramas ni material de terceros: las referencias de estilo están descritas solo en texto ([patrones](docs/referencias.md), [enlaces](docs/referencias-web.md)).

## Cómo contribuir

Leé [CONTRIBUTING.md](CONTRIBUTING.md): desarrollo local, cómo crear una **plantilla** de gráficos o un **estilo** nuevo, y las reglas del repositorio (sin medios de terceros, sin datos personales). Participación sujeta al [Código de conducta](CODE_OF_CONDUCT.md). Para reportar una vulnerabilidad, ver [SECURITY.md](SECURITY.md). Cambios en [CHANGELOG.md](CHANGELOG.md).
