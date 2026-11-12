# Registro de cambios

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/). El proyecto sigue [versionado semántico](https://semver.org/lang/es/).

## [Sin publicar]

### Corregido

- Plantillas de gráficos: las sombras de las tarjetas ya no se cortan con un borde recto en el límite de la imagen. Cada plantilla declara un `bleed` (margen transparente) y el contenido visible queda en la misma posición que antes.
- `comparacion`: el círculo de la flecha ya no toca el texto de las tarjetas (queda a 18 px o más).
- `anotacion`: la etiqueta y su sombra quedan siempre dentro de la imagen, también con el punto en una esquina.

### Limitaciones conocidas

- `chat_burbujas` y `checklist` no reducen el tamaño de letra con textos muy largos: con el máximo que admite el esquema (por ejemplo 4 mensajes de 120 caracteres) el contenido puede desbordar la plantilla y cortarse.

## [0.1.0] — 2026-11-11

### Agregado

- CLI `editoria`: `doctor`, `init`, `probe`, `transcribe`, `analyze`, `plan draft|lint`, `captions build`, `graphics list|preview|render`, `audio sfx|mix|check-voice`, `render`, `contact-sheet`, `qc`, `shots pack|import|compare|verdict|budget`, `propose`, `deliver`, `run`, `version new` y `feedback parse`.
- Plan declarativo `plan.yaml` con esquemas Pydantic estrictos y linter de políticas.
- Tres estilos (A claridad profesional, B explicación visual, C ritmo y personalidad) y marca provisional `master-solution`.
- Capa de agentes para Claude Code: skills `editar-video` y `aplicar-feedback`, subagentes `director-creativo`, `operador-tomas`, `motion-designer`, `disenador-sonido` y `revisor-qc`, y hooks de protección del original, de las versiones entregadas y del presupuesto.
- Prompt maestro genérico con marcadores (`prompts/prompt-maestro.md`) y la instancia de Master Solution.
- Patrones de edición R01–R09 (solo texto) y 25 referencias web.
- `scripts/fetch_assets.py` y `assets/externos.yaml` para emojis Noto e Inter con verificación sha256.
- Documentación: README (español e inglés), arquitectura, políticas, guía para Windows, ADR 0001–0004, uso con chat.
- Comunidad: guía de contribución, código de conducta, política de seguridad, formularios de issues, plantilla de PR y CODEOWNERS.
- CI en Ubuntu y Windows (Python 3.11 y 3.12) y pre-commit (ruff, detect-secrets, archivos grandes y `no-media`).
- Pruebas de higiene del repositorio (`tests/repo/`): sin medios ni datos personales versionados, licencias completas, archivos de comunidad presentes.

### Limitaciones conocidas

- La verificación de identidad, fondo y sincronía labial es humana.
- Las tomas generadas con Higgsfield son opcionales y manuales; no hay cliente de API en v0.1 (no se verificó un modelo de video a video con estimación de costo).
- Sin exportación a proyectos de CapCut ni publicación en redes.
