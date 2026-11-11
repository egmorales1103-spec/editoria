# Política de seguridad

## Versiones con soporte

Mientras el proyecto esté en la serie 0.x, solo se corrige la última versión publicada.

## Cómo reportar una vulnerabilidad

**No abras un issue público** para reportar un problema de seguridad. Usá el reporte privado de GitHub (pestaña *Security* → *Report a vulnerability*) o escribí a [completar: correo de contacto de seguridad].

Incluí, si podés:

- Qué componente afecta (CLI, hooks de `.claude/`, scripts, plantillas de gráficos) y la versión.
- Pasos para reproducirlo y su impacto.
- Si hay medios o datos personales involucrados, **no los adjuntes**: describilos.

Respondemos para confirmar la recepción en un plazo razonable y coordinamos la divulgación una vez corregido el problema. No hay un programa de recompensas.

## Qué consideramos un problema de seguridad

- Ejecución de código o lectura/escritura de archivos fuera de la carpeta de proyectos a partir de un video, un plan o una plantilla maliciosos (por ejemplo, rutas con `..` o plantillas HTML que cargan recursos de red).
- Evasión de las guardas que protegen el original, las versiones entregadas o el presupuesto (`00_original/`, `.entregado`, `budget.limit`).
- Fuga de claves o datos del usuario (por ejemplo, claves en logs o en el historial).
- Dependencias con vulnerabilidades conocidas que afecten al uso normal.

## Buenas prácticas para quien usa EditorIA

- Las claves (por ejemplo `HIGGSFIELD_API_KEY`) van en `.env`, que **nunca se versiona**. No las pegues en issues ni en capturas.
- `proyectos/` contiene tus videos: está en `.gitignore`; no lo subas.
- El render de gráficos bloquea la red; no deshabilites esa restricción para plantillas que no controlás.
- Revisá las plantillas de terceros antes de usarlas: son HTML que se ejecuta en un navegador headless.
- El repositorio usa `detect-secrets` en pre-commit y activa el escaneo de secretos de GitHub: no lo desactives.
