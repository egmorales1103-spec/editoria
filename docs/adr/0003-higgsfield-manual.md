# ADR-0003: Higgsfield en modo manual asistido por defecto

- Estado: aceptada
- Fecha: 8 de noviembre de 2026

## Contexto

El flujo original prevé tomas complementarias generadas con Higgsfield (variaciones sutiles de encuadre derivadas de la grabación). Existe una API oficial, pero no está verificado que algún modelo haga video-a-video preservando identidad, fondo y sincronía labial. Una generación puede inventar zonas que la cámara nunca registró, consume créditos y puede deformar rostro, manos o fondo.

## Decisión

1. **Modo manual asistido por defecto.** `shots pack` prepara el segmento, fotogramas ancla, el prompt con restricciones negativas y los pasos; la persona (o un agente con acceso autorizado) lo ejecuta en la herramienta; `shots import` valida y conforma el resultado; `shots compare` mide la deriva del fondo; `shots verdict` es la **única** vía para aceptar una toma.
2. **Cliente API experimental, apagado por defecto** (`shots api estimate|submit|status|download`), solo con endpoint y modelo verificados en la documentación oficial durante la sesión de desarrollo, y con presupuesto obligatorio.
3. **Presupuesto obligatorio.** Sin `budget.limit` en `proyecto.yaml` no se envía nada. Los gastos se registran en `logs/creditos.jsonl`. Nunca se compran planes ni créditos. Un hook de Claude Code bloquea `shots api submit` sin límite (defensa en profundidad).
4. **Nada de reintentos automáticos que gasten.** `max_attempts` limita los reintentos manuales.
5. **El producto funciona completo sin tomas generadas:** una V1 con original y reencuadres se identifica como "sin tomas generadas".
6. **Registro solo de datos reales:** semilla y costo quedan vacíos si la herramienta no los mostró.
7. **El QC marca REVISIÓN HUMANA** siempre que haya tomas generadas: identidad, fondo y labios no se pueden verificar con certeza por código.

## Consecuencias

- Máxima seguridad frente a gasto accidental y a tomas que alteran la identidad o el escenario.
- El flujo tiene un paso manual cuando se quiere usar tomas generadas.
- No se promete conservación exacta del fondo mediante generación; ante conflicto, prevalece la preservación del original.

## Alternativas descartadas

- **API por defecto:** gasto y riesgo sin verificación de capacidades.
- **No soportar tomas generadas:** se pierde una parte del flujo original que algunos usuarios quieren explorar.
