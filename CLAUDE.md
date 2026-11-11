# CLAUDE.md — EditorIA

Instrucciones para Claude Code, tanto para **desarrollar** EditorIA como para **usarlo** a fin de editar videos.

## Qué es

`editoria` es una CLI en Python que ejecuta el flujo del prompt maestro (`prompts/`): análisis → tomas → 3 propuestas → V1 con subtítulos, motion graphics y sonido → QC → entrega → feedback. **El modelo decide; el código ejecuta y verifica.** Las reglas del prompt son chequeos (linter, QC, hooks), no pedidos de texto: ver `docs/politicas.md`.

## Comandos de desarrollo

```bash
uv sync --all-extras                 # dependencias (incluye dev)
uv run playwright install chromium   # motor de gráficos
uv run pytest -m "not slow"          # suite rápida (genera tests/.fixtures la primera vez)
uv run ruff check . && uv run ruff format --check .
uv run mypy                          # usa [tool.mypy] files = src/editoria
uv run python scripts/make_fixtures.py --force   # regenerar fixtures sintéticos
uv run python -m editoria.schemas.export         # exportar JSON Schema a schemas/json/
```

## Convenciones

- Python ≥ 3.11, tipado completo (mypy), ruff (línea 100).
- **Idioma:** mensajes al usuario, docs y CLI en español; código, nombres, docstrings, claves de esquema y enums internos en inglés; IDs que escribe el usuario (plantillas, estilos, veredictos `aceptado/reintentar/descartado`) en español.
- **ffmpeg:** toda llamada pasa por `editoria.util.ffmpeg.run()/probe()`. Con filtergraphs que referencian archivos, usar `cwd=` y rutas relativas (Windows + espacios + acentos). Probar siempre con `tests/.fixtures/carpeta con espacios/edición ñ.mp4`.
- **Proyectos:** `editoria.util.project.ProjectContext` tiene todas las rutas de `proyectos/<slug>/`. No construir rutas a mano.
- **Geometría:** `editoria.util.geometry.base_transform()` define cómo el video base llena el lienzo 9:16. Cualquier conversión de cajas de rostro a coordenadas del lienzo usa esa función.
- **Esquemas:** `editoria.schemas` (Pydantic v2, `extra="forbid"`). Leer/escribir con `read_model`/`write_model` (YAML o JSON según extensión). `plan.yaml` usa alias `in`/`schema`.
- **CLI:** cada módulo expone `cli.register(app)`; el `cli.py` raíz los monta.
- Tests sin red; marcadores `slow`, `e2e`, `network`.
- Commits: conventional commits (`feat(captions): …`).

## Mapa de propiedad (Ola 1)

| Dueño | Rutas |
|---|---|
| Lead | `pyproject.toml`, `uv.lock`, `src/editoria/{__init__,cli,contracts,pipeline,deliver}.py`, `src/editoria/{schemas,util}/**`, `tests/conftest.py`, `tests/fixtures/**`, `tests/e2e/**`, `tests/test_*.py` (raíz), `scripts/make_fixtures.py`, `CLAUDE.md`, `.gitignore`, `.gitattributes`, `LICENSE*`, `.env.example` |
| A1 | `src/editoria/{ingest,analysis,versioning}/**`, `src/editoria/doctor.py`, `tests/{ingest,analysis,versioning}/**`, `docs/modulos/ingesta.md` |
| A2 | `src/editoria/{planning,policy,captions}/**`, `tests/{planning,policy,captions}/**`, `docs/modulos/{plan,subtitulos}.md` |
| A3 | `src/editoria/graphics/**`, `templates/graphics/**`, `tests/graphics/**`, `docs/modulos/graficos.md` |
| A4 | `src/editoria/audio/**`, `assets/sfx/**`, `scripts/gen_sfx.py`, `tests/audio/**`, `docs/modulos/sonido.md` |
| A5 | `src/editoria/{render,qc}/**`, `tests/{render,qc}/**`, `docs/modulos/render-qc.md` |
| A6 | `src/editoria/shots/**`, `tests/shots/**`, `docs/higgsfield.md`, `docs/modulos/tomas.md` |
| A7 | `.claude/**`, `prompts/**`, `brands/**`, `styles/**`, `references/**`, `templates/docs/**`, `docs/**` (excepto `docs/modulos/**` y `docs/higgsfield.md`), `README*.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `THIRD_PARTY.md`, `CHANGELOG.md`, `.github/**`, `.pre-commit-config.yaml`, `scripts/fetch_assets.py`, `assets/externos.yaml`, `tests/repo/**` |

Nadie edita fuera de sus rutas. Si un contrato no alcanza: adaptador local + "solicitud de cambio de contrato" en el reporte.

## Kit de origen (solo lectura)

`C:\dev\editor master solution\Master_Solution_Kit_Edicion_IA\Master_Solution_Kit_Edicion_IA`

Solo se importa lo permitido en la sección 2 del plan. **Nunca** se copian al repo: los videos de referencia (`02_Referencias_Usuario/`), sus fotogramas, `06_Laminas_Visuales/`, `ABRIR_CATALOGO.html`, ni `Inventario_Referencias.json` completo (son material de terceros o datos personales). El historial de git debe quedar limpio.

## Prohibiciones (producto)

- No escribir en `proyectos/*/00_original/**` ni en versiones ya entregadas.
- No publicar en redes ni enviar mensajes. No existe comando de publicación.
- No gastar créditos sin un límite autorizado en `proyecto.yaml`; nunca comprar.
- No sintetizar ni clonar voz; el audio del VIDEO_BASE manda.
- No inventar métricas, testimonios ni compatibilidad con CapCut.
- Tras entregar V1, detenerse y esperar feedback.
