# ADR-0004: Licencias del proyecto y de sus recursos

- Estado: aceptada (los titulares deben confirmar la elección antes de recibir contribuciones)
- Fecha: 8 de noviembre de 2026

## Contexto

El repositorio mezcla código, prompts y documentación, efectos de sonido generados y recursos de terceros (fuentes, emojis). Cambiar la licencia después de recibir contribuciones es difícil.

## Decisión

| Material | Licencia | Motivo |
|---|---|---|
| Código (`src/`, `scripts/`, `tests/`, `.claude/hooks/`) | **Apache-2.0** (`LICENSE`) | Concesión de patentes explícita y amplia compatibilidad |
| Prompts, documentación, plantillas de trabajo y estilos | **CC BY 4.0** (`LICENSE-docs`) | Reutilizable con atribución |
| SFX generados por `scripts/gen_sfx.py` | **CC0 1.0** | Sin restricciones; son sintetizados por el proyecto |
| Emojis animados Noto | CC BY 4.0 (de Google) | No se redistribuyen: los descarga `scripts/fetch_assets.py` y se exige atribución |
| Tipografía Inter | SIL OFL 1.1 | No se redistribuye en el repositorio: la descarga el script |

Además:

- **FFmpeg** se invoca como **binario externo** y no se distribuye ni se enlaza. Según la compilación, es GPL o LGPL; al no distribuirlo, esas obligaciones no se trasladan al proyecto. Está documentado en `THIRD_PARTY.md`.
- Los **modelos de whisper** se descargan por separado, con sus propias licencias.
- Las **referencias de terceros** (videos, capturas, plantillas) no se incluyen: solo descripciones en texto y enlaces.
- Todo asset usado en un video debe tener licencia declarada en `assets/sfx/manifest.yaml` o `assets/externos.yaml`; la ausencia es un ERROR del linter y del QC, y `deliver` genera `atribuciones.md`.
- Los videos de quien usa la herramienta no se versionan (`proyectos/` está en `.gitignore`).

## Consecuencias

- Atribución obligatoria de emojis Noto en los videos que los usen.
- Un test del repositorio falla si un asset de los manifests no tiene licencia, o si se versionan medios fuera de las rutas permitidas.
- Si se cambia a una licencia más simple para el código (por ejemplo MIT), hay que hacerlo antes de aceptar contribuciones externas.

## Alternativas descartadas

- **MIT para el código:** más simple, sin concesión de patentes explícita.
- **GPL:** obligaría a quien use el proyecto a publicar sus modificaciones y complicaría la convivencia con FFmpeg.
