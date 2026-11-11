# Políticas: reglas del prompt convertidas en garantías ejecutables

El prompt maestro (`prompts/prompt-maestro.md`) tiene reglas como "no cambiar el fondo", "no inventar métricas" o "esperar feedback tras V1". En un chat son pedidos de texto: el modelo puede olvidarlos. En EditorIA cada regla tiene un **mecanismo que la verifica**: el linter del plan, el QC, la propia CLI o un hook.

La idea central: **el modelo decide; el código ejecuta y verifica.**

## Tabla de reglas

| ID | Regla (sección del prompt) | Mecanismo |
|---|---|---|
| P01 | Conservar copia intacta del original (§3) | `init` copia, calcula sha256 y deja el archivo de solo lectura; un hook bloquea escrituras en `00_original/`; el QC verifica el hash |
| P02 | No usar una referencia como VIDEO_BASE (§3) | `init` exige una ruta explícita; la skill pide solo el archivo faltante |
| P03 | El audio base manda; sin voz sintética; se descarta el audio de las tomas generadas (§5) | `shots import` quita el audio; el compositor solo usa la mezcla basada en el audio base; el QC mide desfase y similitud de voz |
| P04 | Conservar duración, orden y cortes (§6, §10) | Linter: intervalos dentro de `[0, duración]` y sin solapes en la pista de video; QC: duración ±1 cuadro |
| P05 | Toma generada solo si pasó revisión (§7) | Linter: ERROR si `method: generated` sin veredicto `aceptado` en el registro |
| P06 | Distinguir reencuadre, toma generada y recurso gráfico (§5) | `method` obligatorio en cada intervalo; `resumen.md` lista cada intervalo con su método |
| P07 | Reencuadre sin prometer detalle nuevo (§5, §10) | Guarda de zoom: ERROR si se escala más de 1,25× sobre píxeles nativos; WARN sobre el máximo del estilo |
| P08 | Sin fondo nuevo, órbitas, outpainting ni relighting (§5) | El prompt del paquete de tomas lleva restricciones negativas; `shots compare` mide la deriva del fondo; la skill lo prohíbe |
| P09 | Créditos solo dentro del límite autorizado; nunca comprar (§4) | Guarda de presupuesto + `logs/creditos.jsonl`; sin límite no hay envío; un hook de defensa en profundidad bloquea `shots api submit` sin `budget.limit` |
| P10 | Exactamente tres propuestas sobre el mismo pasaje (§8) | `propose` siempre genera A, B y C sobre la misma ventana |
| P11 | No declarar producido lo que no existe (§4, §8, §11) | `deliver` lista solo archivos verificados con ffprobe; lo demás figura como "pendiente" |
| P12 | Subtítulos fieles, sincronizados y legibles; sin tapar el rostro ni los controles de la plataforma (§9.2) | El generador respeta palabras, caracteres por segundo, caracteres por línea, zona segura y rostro; el QC lo verifica |
| P13 | Títulos editoriales distinguibles de lo dicho (§9.2) | Linter: ERROR si `editorial_titles` no usa un estilo distinto |
| P14 | No inventar métricas; ejemplos etiquetados (§9.3) | `data_source` obligatorio en plantillas de datos; etiqueta "Ejemplo" automática; linter |
| P15 | Una interfaz recreada es una ilustración (§9.3) | La plantilla `ui_demo` agrega la etiqueta "Ilustración"; sin esa plantilla no se recrean interfaces |
| P16 | No saturar la pantalla ni poner un sonido por palabra (§2, §9.3, §9.4) | Linter: máximo de elementos simultáneos y de SFX por 10 s según el estilo; separación mínima entre cues |
| P17 | Recursos con permiso y atribución (§9.3, §9.4) | Linter y QC: un asset usado sin licencia en `assets/sfx/manifest.yaml` o `assets/externos.yaml` es ERROR; `deliver` genera `atribuciones.md` |
| P18 | Voz inteligible; sin clipping (§9.4) | QC: LUFS, true peak, clipping y relación voz/SFX |
| P19 | MP4 H.264/AAC, 1080×1920, FPS de origen, sin bandas por rutina (§10) | Preset de encode fijo + QC |
| P20 | Entregar V1 y esperar; no sobrescribir versiones (§11, §12) | `version new` exige feedback parseado para V2 en adelante; las versiones entregadas son inmutables (`.entregado`) y un hook las protege; la skill se detiene tras V1 |
| P21 | No publicar ni enviar mensajes (§4) | No existe comando de publicación; las skills y subagentes lo prohíben |
| P22 | No inventar compatibilidad con CapCut (§10) | `deliver` entrega plan, mapa CSV y capas; la documentación lo aclara |
| P23 | Palabras inciertas marcadas, no inventadas (§6) | `flagged` por baja probabilidad y `transcript_revision.md` |
| P24 | No embellecer ni alterar la identidad (§5) | Hojas comparativas; el QC marca REVISIÓN HUMANA siempre que haya tomas generadas |

Además, el linter aplica los `forbidden_claims` de la marca (ID `BRAND`) y valida el esquema del plan (ID `SCHEMA`).

## Qué es un chequeo y qué es una limitación

Hay reglas que el código **no puede** verificar con certeza: que la cara no cambió, que el fondo conserva sus objetos, que los labios coinciden con la voz, que la edición tiene buen gusto. El QC las deja como **REVISIÓN HUMANA** y las reporta como pendientes; nunca las marca como aprobadas. La métrica de deriva del fondo orienta, no decide.

## Los hooks de Claude Code

`.claude/settings.json` registra dos hooks de tipo `PreToolUse` (Python estándar, funcionan en Windows, macOS y Linux):

| Hook | Bloquea | Regla |
|---|---|---|
| `proteger_original.py` | Escrituras (Write, Edit, MultiEdit, comandos de Bash y PowerShell) en `proyectos/*/00_original/**` y en versiones con archivo `.entregado` | P01, P20 |
| `guardar_presupuesto.py` | `editoria shots api submit` si `proyecto.yaml` no tiene `budget.limit` positivo o ya está agotado | P09 |

Son **defensa en profundidad**: la CLI aplica las mismas guardas por su cuenta. Los hooks protegen frente a un agente que intente escribir directamente. Los comandos `editoria ...` se consideran de confianza porque la CLI valida sus propias reglas. La detección en comandos de shell es heurística (no analiza todos los programas posibles); la protección de fondo es el archivo de solo lectura y las guardas de la CLI.

## Cómo agregar o cambiar una política

1. Escribí la regla con su ID y su sección del prompt.
2. Implementala como chequeo (linter, QC o guarda de la CLI), no solo como texto.
3. Agregá al menos un test positivo y uno negativo.
4. Actualizá esta tabla.
