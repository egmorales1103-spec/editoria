# Uso sin herramientas: el prompt maestro en un chat

Esta guía es para quien **no** usa la CLI `editoria` ni Claude Code y solo quiere apoyarse en una IA conversacional para planificar la edición de un video. Si instalaste EditorIA, el flujo completo está en el [README](../README.md).

## Qué se puede esperar

Una conversación de texto **sin acceso a herramientas** puede preparar instrucciones, propuestas, guion de edición, textos de subtítulos y prompts para otras aplicaciones. **No puede** abrir CapCut, operar Higgsfield ni exportar un video por sí sola. El prompt maestro le exige decirlo con claridad y no declarar como producido nada que no exista.

Para obtener un video terminado necesitás una IA con acceso real a un editor y a las herramientas de generación, o la CLI de EditorIA con Claude Code.

## Cómo usarlo

1. Abrí [`prompts/prompt-maestro.md`](../prompts/prompt-maestro.md) y completá los cuatro marcadores (`{{MARCA}}`, `{{PUBLICO}}`, `{{VOZ}}`, `{{RESTRICCIONES}}`). Si sos Master Solution, usá [`prompts/prompt-maestro.master-solution.md`](../prompts/prompt-maestro.master-solution.md), que ya viene completado.
2. Copiá el contenido desde la línea «COPIAR DESDE AQUÍ» hasta «FIN DEL PROMPT.» en las instrucciones del proyecto o en el primer mensaje del chat de la IA editora.
3. Adjuntá tu exportación recortada como `VIDEO_BASE`. Los cortes de pausas los hacés vos en tu editor (por ejemplo CapCut): la IA no rehace tu montaje. Si tu aplicación no acepta el formato, subí el archivo por separado.
4. Si tenés logo, colores o tipografías, adjuntalos. Si no, la IA usará blanco, negro y un único acento que declarará como propuesta.
5. Verificá qué herramientas tiene realmente la IA (editor de video, Higgsfield, navegador). Si no tiene ninguna, esperá instrucciones y archivos de preparación, no un video final.
6. Si vas a usar generaciones de pago, indicá el límite de créditos que ya tenés y autorizás para este video. No hace falta comprar nada para recibir propuestas.
7. Recibí tres propuestas (A, B y C) con su recomendación, y luego la V1. Después enviá tu feedback con tiempos concretos; podés usar la plantilla [`templates/docs/Feedback_V1.md`](../templates/docs/Feedback_V1.md).

## Decisiones del flujo

- La IA presenta tres tratamientos creativos y, por defecto, desarrolla el que recomiende para entregar V1 sin una aprobación intermedia. Si querés elegir antes, escribí: «Mostrame A/B/C y esperá que elija antes de montar V1».
- No se produce una versión completa por cada propuesta. Las tres muestras son breves y comparables; la entrega principal es una V1 completa.
- Las tomas nuevas solo se incorporan si conservan fondo, identidad y sincronización labial. Si no pasan la revisión, se conserva el original o un reencuadre basado en él, y se deja clara la diferencia.
- Una perspectiva generada por IA no puede garantizar que el fondo sea idéntico. Conservar el escenario tiene prioridad sobre un ángulo nuevo.
- Después de entregar V1, la IA espera tu feedback. No publica ni envía mensajes por vos.

## Plantillas de trabajo

En [`templates/docs/`](../templates/docs/) hay plantillas para ordenar el trabajo:

| Plantilla | Para qué sirve |
|---|---|
| `Brief_Por_Video.md` | Completar solo lo que no se deduce del video |
| `Propuestas_A_B_C.md` | Comparar las tres propuestas |
| `Mapa_Edicion.csv` | Mapa de edición con tiempos, método y recursos |
| `Registro_Generaciones.csv` | Registro real de cada generación de tomas |
| `Feedback_V1.md` | Dejar comentarios con tiempos |

## Mensaje breve para iniciar cada trabajo

> Usá el prompt maestro. Este archivo es mi VIDEO_BASE, ya recortado. Prepará las tomas complementarias preservando mi fondo e identidad, tres propuestas creativas y una V1 completa con subtítulos, motion graphics y efectos de sonido. Desarrollá tu propuesta recomendada y esperá mi feedback después de V1. Mi límite de créditos autorizado para este video es: [completar si corresponde].

## Referencias y derechos

Los patrones de [`references/patrones.yaml`](../references/patrones.yaml) y los enlaces de [`references/web.yaml`](../references/web.yaml) son material de inspiración, no autorización para republicar obras de otras personas. Consultá la licencia de cualquier recurso que incorpores a una publicación. La lista de sonidos describe usos habituales de edición, no un ranking confirmado de viralidad.
