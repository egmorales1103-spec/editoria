# ADR-0001: Motor de gráficos con HTML/CSS y Playwright, no Remotion

- Estado: aceptada
- Fecha: 8 de noviembre de 2026

## Contexto

Los motion graphics (títulos, listas, burbujas de chat, datos, comparaciones) se deben generar desde plantillas parametrizables, con fondo transparente y de forma reproducible. Las dos opciones razonables eran Remotion (React) y HTML/CSS renderizado con un navegador headless.

Remotion es *source-available*, no código abierto según la OSI. Su licencia es gratuita para personas y organizaciones pequeñas (hasta 3 personas, según su documentación a la fecha de esta decisión) y exige una licencia de empresa a partir de 4. Un repositorio público basado en Remotion trasladaría esa restricción a cada persona que lo use, y la empresa que impulsa el proyecto ya supera ese tamaño.

## Decisión

Usar **plantillas HTML/CSS renderizadas con Playwright/Chromium headless** (Apache-2.0 y BSD, respectivamente):

- Cada plantilla es una carpeta con `template.html`, `params.schema.json` y `meta.yaml`.
- Solo se permiten animaciones CSS o Web Animations API; están prohibidos `setTimeout`/`setInterval` y `requestAnimationFrame`.
- Para cada cuadro, el renderer pausa todas las animaciones (`document.getAnimations()`), fija `currentTime = frame / fps` y captura con `omit_background=True`. El resultado es una secuencia PNG con canal alfa, determinística cuadro a cuadro.
- Toda solicitud `http`/`https` se aborta: el render no usa red. Las fuentes y los assets son locales.
- Caché por hash de plantilla, parámetros, marca y FPS.

## Consecuencias

- Licencias completamente abiertas para el código y para quien lo use.
- Los agentes escriben HTML/CSS con fluidez, y las plantillas se pueden previsualizar en cualquier navegador.
- Costo: requiere descargar Chromium (`playwright install chromium`, cientos de MB) y el render por cuadros es más lento que un motor nativo. Si Chromium falta, `editoria doctor` lo avisa y el flujo continúa sin gráficos, con una advertencia.
- Menos potencia que un motor de video dedicado (sin 3D ni composición compleja). Es suficiente para la biblioteca de la v0.1.

## Alternativas descartadas

- **Remotion:** ver contexto.
- **Dibujo directo con PIL o filtros de FFmpeg:** poco expresivo para tipografía animada y mantenimiento difícil de plantillas.
- **Lottie/After Effects:** requiere herramientas y licencias externas y dificulta que un agente edite las plantillas.
