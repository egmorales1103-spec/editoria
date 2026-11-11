# Tomas complementarias (Higgsfield) — flujo manual asistido

Las tomas generadas son **opcionales y de riesgo**. El producto funciona completo sin ellas: la V1 con original y reencuadres es una alternativa legítima, siempre que se identifique como "sin tomas generadas" y no se presente como cumplimiento de esta etapa. Detalle de lo verificado y lo no verificado: `docs/higgsfield.md`.

## Antes de empezar

- ¿Hay acceso real a la herramienta (navegador autorizado o conector)? Si no, solo preparás paquetes: la persona los ejecuta a mano.
- ¿`proyecto.yaml` tiene `budget.limit`? Sin límite **no se gasta nada**: preparás segmentos, prompts y estimación visible y pedís solo ese dato. Nunca compres planes ni créditos.
- Los límites de la herramienta (`tool_limits`) salen de `proyecto.yaml`; si están vacíos el paquete dice "verificar en la herramienta". No los inventes.
- Subí a la herramienta solo el segmento del VIDEO_BASE de este trabajo, nunca carpetas completas.

## Qué pedir (y qué no)

Elegí de **dos a cuatro momentos** que lo justifiquen (no es una cuota). Empezá por acercamientos moderados y variaciones sutiles que no revelen zonas nuevas. Una perspectiva lateral solo es candidata si no rompe fondo ni sincronía labial. Nunca: cambio de fondo, outpainting, órbitas amplias, movimiento de 180°/360°, nuevas luces, ropa u objetos, desenfoque, relighting o colorización del fondo.

## Pasos

1. **Paquete:** `editoria shots pack <slug> --in 9.8 --out 12.3 --cambio "acercamiento sutil al rostro"`. Crea el segmento (re-encode preciso), fotogramas ancla (inicio, medio, fin), el prompt con restricciones negativas y `pack.md` con los pasos manuales; agrega una fila `pendiente` al registro.
2. **Ejecución manual:** la persona (o vos, con acceso autorizado) corre el paquete en la herramienta. Registrá solo lo que la herramienta muestra: función/modelo real, ajustes, costo mostrado. Semilla y costo vacíos si nadie los informó; **no los fabriques**.
3. **Importar:** `editoria shots import <slug> G01 <archivo>`. Conforma FPS, resolución y pixel format, **quita el audio** y verifica la duración contra el segmento (más largo se recorta; más corto o con otro aspecto se rechaza).
4. **Comparar:** `editoria shots compare <slug> G01`. Hoja lado a lado (inicio, medio, fin y el cuadro de mayor movimiento) y métricas de deriva del fondo. **Recomienda, no decide.**
5. **Mirar:** abrí la hoja y compará rostro, manos, bordes, objetos, sombras y boca. Ante una duda visible, conservá el original.
6. **Veredicto:** `editoria shots verdict <slug> G01 aceptado|reintentar|descartado --motivo "..."`. Es la **única** vía para aceptar una toma. El veredicto sobre identidad, fondo y labios lo da la persona: si vos no podés verlo con certeza, proponé el veredicto con tu evidencia y pedí confirmación, o dejala `pendiente`. `reintentar` respeta `max_attempts`.
7. **Usar:** solo las tomas `aceptado` pueden entrar al plan (`method: generated`, `shot: G01`). El linter (P05) y el QC lo verifican, y el QC siempre deja `REVISIÓN HUMANA` cuando hay tomas generadas.

## Presupuesto

`editoria shots budget <slug>` muestra límite, gastado y restante (`logs/creditos.jsonl`). Un hook impide `shots api submit` sin límite (el cliente de API es experimental y está apagado por defecto). No hay reintentos automáticos que gasten.

## No sobreprometer

Los prompts expresan el objetivo; no garantizan que el modelo lo cumpla. No digas que generaste, descargaste o importaste algo si no existe el archivo y no lo verificaste.
