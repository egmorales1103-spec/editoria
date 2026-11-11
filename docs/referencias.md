# Patrones de edición de referencia (R01–R09)

EditorIA describe nueve patrones de edición que sirven de vocabulario común entre el director creativo (humano o agente), los estilos A/B/C y el campo `referencia` del mapa de edición.

## De dónde salen y qué no incluyen

Son **observaciones de técnica escritas en texto**: qué se hace en pantalla y para qué. Nacieron del análisis de piezas de referencia de terceros, pero este repositorio **no incluye ningún video, fotograma, captura ni enlace a esas piezas, ni nombra a sus autores o cuentas**. Los patrones no autorizan a copiar una obra: orientan decisiones de ritmo, jerarquía tipográfica y uso de gráficos. Lo que se publique siempre es material propio.

La fuente de datos es [`references/patrones.yaml`](../references/patrones.yaml); esta página es su lectura para personas. Para recursos en la web, ver [referencias-web.md](referencias-web.md).

## Reglas que prevalecen sobre cualquier patrón

- El fondo, la identidad y la voz del VIDEO_BASE no se modifican.
- No se inventan métricas, testimonios ni funciones: una cifra es real o se rotula "Ejemplo"; una interfaz recreada se rotula "Ilustración".
- No se llena la pantalla: el linter limita elementos simultáneos y efectos de sonido por cada 10 s según el estilo.
- No hay bandas cinematográficas por rutina en video vertical.

## Resumen

| ID | Patrón | Estilos | Plantillas relacionadas |
|---|---|---|---|
| R01 | Conversación entre dos personajes | C | `chat_burbujas`, `notificacion` |
| R02 | Explicación de herramientas a cámara | B | `checklist`, `anotacion`, `ui_demo` |
| R03 | Entrevista con subtítulos de una palabra | A, C | `palabra_clave` |
| R04 | Montaje de diseño con tipografía en tensión | B | `titulo_gancho` |
| R05 | Texto protagonista | C | `palabra_clave`, `anotacion` |
| R06 | Motion graphics de tarjetas y cifras | B | `dato_grafico`, `ui_demo`, `notificacion`, `comparacion` |
| R07 | Variación de encuadres y comparación con el original | A | `comparacion` |
| R08 | Composición cinematográfica horizontal | ninguno por defecto | — |
| R09 | Preguntas y reacciones | C | `palabra_clave`, `chat_burbujas` |

## R01 · Conversación entre dos personajes

Alternancia de interlocutores con texto breve y rótulos pequeños de apoyo.

**Qué se observa**

- Dos encuadres que alternan según quién habla; el cambio de plano marca el cambio de turno.
- Texto corto por turno, colocado junto al rostro y no sobre él, a veces con una palabra en color.
- Rótulos pequeños tipo etiqueta (por ejemplo, cuántas personas vieron algo) como apoyo al argumento.

**Elementos:** alternancia de planos, subtítulo lateral corto, etiquetas de apoyo.

**Cuándo usarlo:** Contenido que simula o relata un diálogo, o que contrasta dos posiciones.

**Cuidados:** Solo con material propio de ambos planos; no se simula a otra persona ni se genera una voz.

## R02 · Explicación de herramientas a cámara

Persona a cámara con pasos y diagramas que aparecen a medida que explica.

**Qué se observa**

- Encuadre de busto estable; el gráfico ocupa el tercio inferior o superior sin tapar el rostro.
- Lista de pasos numerados que entra de a uno ("1 · …", "2 · …") sincronizada con la frase.
- Tarjetas con borde y un icono simple para cada herramienta o etapa de un flujo.
- Subtítulo de una línea con una palabra destacada, mientras el gráfico explica el detalle.

**Elementos:** lista numerada animada, tarjetas de flujo, subtítulo de una línea, icono simple.

**Cuándo usarlo:** Explicar un proceso, un flujo de trabajo o una herramienta paso a paso.

**Cuidados:** Los nombres de herramientas deben ser los reales; no mostrar funciones que no existen.

## R03 · Entrevista con subtítulos de una palabra

Encuadre cercano con subtítulos grandes en mayúsculas y una palabra resaltada en amarillo.

**Qué se observa**

- Primer plano que llena el cuadro; el texto se ubica en el tercio medio-inferior.
- Un evento por una o dos palabras, en mayúsculas, con contorno grueso para el contraste.
- Color de énfasis (amarillo) en la palabra clave; el resto en blanco.
- {'Cadencia rápida': 'el texto cambia casi con cada palabra, sincronizado con el habla.'}

**Elementos:** subtítulo en mayúsculas, palabra destacada, primer plano.

**Cuándo usarlo:** Entrevistas o monólogos con ritmo alto donde el texto sostiene la atención.

**Cuidados:** No tapar la boca ni el rostro; mantener la posición estable dentro de la zona segura.

## R04 · Montaje de diseño con tipografía en tensión

Primeros planos y composiciones gráficas con tipografía como elemento principal.

**Qué se observa**

- Cortes rápidos entre planos detalle y composiciones con mucho espacio negativo.
- Paleta muy limitada (blanco, negro y un rojo dominante) con texto pequeño y técnico superpuesto.
- Textos que se desplazan o se deslizan al entrar, alineados a una cuadrícula visible.

**Elementos:** cortes rápidos, paleta limitada, texto pequeño superpuesto, entrada por deslizamiento.

**Cuándo usarlo:** Aperturas, transiciones de bloque o piezas sobre diseño y marca.

**Cuidados:** Es un lenguaje de montaje sobre imágenes de archivo; con un solo plano a cámara se traduce en tipografía y paleta, no en cortes de material ajeno.

## R05 · Texto protagonista

Las palabras clave se vuelven el elemento principal, con jerarquía de tamaños y color.

**Qué se observa**

- {'Una frase en dos o tres líneas con tamaños muy distintos': 'la palabra importante, grande.'}
- Color de énfasis vivo (verde lima o amarillo) sobre blanco; las palabras menores, pequeñas y apagadas.
- Pequeños elementos gráficos (una flecha, un subrayado, un tachado) que refuerzan una idea.
- Transiciones breves con trama de líneas entre ideas distintas.

**Elementos:** jerarquía de tamaños, color de énfasis, icono pequeño, transición de trama.

**Cuándo usarlo:** Frases con una idea fuerte, contrastes o definiciones.

**Cuidados:** Muchos tamaños a la vez cansan; limitar a una palabra grande por evento.

## R06 · Motion graphics de tarjetas y cifras

Composiciones animadas con tarjetas, maquetas de teléfono y cifras grandes.

**Qué se observa**

- Una cifra grande sobre una tarjeta de color que se "dibuja" (barras o líneas que crecen).
- Maquetas de pantalla de teléfono que entran con una ligera rotación y se alejan al terminar.
- Texto de titular dividido en palabras con distinta tipografía y color, sobre fondo claro o muy oscuro.
- Entradas y salidas suaves; una sola composición por momento.

**Elementos:** cifra grande, tarjeta animada, maqueta de pantalla, titular dividido.

**Cuándo usarlo:** Explicar un número, un resultado o una interfaz sin tener capturas.

**Cuidados:** Las cifras deben ser reales o rotularse "Ejemplo"; una interfaz recreada se rotula "Ilustración".

## R07 · Variación de encuadres y comparación con el original

Vista dividida que compara el original con una variante de encuadre generada.

**Qué se observa**

- {'Pantalla partida': 'arriba la variante, abajo el original con una etiqueta "VIDEO ORIGINAL".'}
- Variaciones de encuadre moderadas (más cerca, más abierto) sobre el mismo discurso.
- La etiqueta de procedencia evita confundir lo generado con lo grabado.

**Elementos:** pantalla partida, etiqueta de procedencia, variación de encuadre.

**Cuándo usarlo:** Para comparar un reencuadre o una toma generada contra el original antes de aceptarla.

**Cuidados:** Es el patrón detrás de `shots compare`. La comparación es una herramienta de revisión; una variante que cambie fondo o identidad se descarta.

## R08 · Composición cinematográfica horizontal

Imagen ancha centrada en un entorno con movimiento amplio, con franjas negras.

**Qué se observa**

- Imagen horizontal dentro de un cuadro vertical, con franjas arriba y abajo.
- Movimiento de sujeto y cámara amplio; poco texto en pantalla.

**Elementos:** encuadre ancho, franjas, poco texto.

**Cuándo usarlo:** Casi nunca en este producto; es solo una referencia de atmósfera.

**Cuidados:** El prompt prohíbe las bandas cinematográficas por rutina en video vertical; no se aplica por defecto ni como estilo A/B/C.

## R09 · Preguntas y reacciones

Subtítulos en mayúsculas para preguntas, con una palabra clave resaltada y pausas de reacción.

**Qué se observa**

- Subtítulo en blanco con contorno negro, en el tercio medio, de dos a cuatro palabras por evento.
- La palabra que sostiene la pregunta o el nombre propio va en color de acento.
- Pausas breves de reacción (un segundo sin texto nuevo) antes de la respuesta.

**Elementos:** subtítulo de pregunta, palabra destacada, pausa de reacción.

**Cuándo usarlo:** Contenido con preguntas, opciones o respuestas rápidas.

**Cuidados:** No forzar el formato de preguntas si el contenido no las tiene.

## Cómo se usan

- Los archivos de `styles/` listan en `references` los patrones y enlaces que inspiran cada estilo.
- En `mapa_edicion.csv`, la columna `referencia` lleva el ID del patrón aplicado (por ejemplo `R03`).
- Para agregar un patrón nuevo, abrí un issue con la plantilla "Estilo nuevo" y describilo en texto, sin adjuntar material de terceros.
