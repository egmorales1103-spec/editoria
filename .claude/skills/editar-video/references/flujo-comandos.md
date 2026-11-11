# Flujo y comandos

Todos los comandos se ejecutan desde la raíz del repositorio con `uv run editoria ...` (o `editoria ...` si está instalado). La carpeta de proyectos es `./proyectos` salvo `--proyectos <ruta>` o la variable `EDITORIA_PROJECTS`. Si un comando devuelve el código 3, el módulo todavía no está implementado: informalo, no lo simules.

## Estructura del proyecto

```
proyectos/<slug>/
├─ proyecto.yaml              marca, destino, presupuesto, proposal_mode, límites de herramientas
├─ 00_original/               video_base.<ext> + .sha256  (solo lectura)
├─ 01_analisis/               probe.json · transcript.json · transcript_revision.md · silencios.json
│                             cortes.json · rostro.json · segmentos.json · mapa_edicion.csv
├─ 02_tomas/                  higgsfield/paquetes · higgsfield/resultados · comparativas
│                             registro_generaciones.csv
├─ 03_propuestas/             plan_A|B|C.yaml · muestra_A|B|C.mp4 · comparativa_ABC.mp4 · propuestas.md
├─ 04_versiones/V1/           plan.yaml · video.mp4 · subtitulos.ass|srt|vtt|json · graficos/ · audio/
│                             qc/qc.json · qc/qc.md · hoja_contactos.jpg · resumen.md
│                             atribuciones.md · mapa_edicion.csv · .entregado
└─ logs/                      comandos.jsonl · creditos.jsonl
```

## Paso a paso

### 0. `editoria doctor`
Tabla OK/FALTA con la solución para Windows (winget), macOS (brew) y Linux (apt). Sin ffmpeg ≥ 6 con libass no se puede renderizar. Sin Chromium o sin el modelo de whisper se avisa: el flujo sigue sin gráficos o descarga el modelo la primera vez.

### 1. `editoria init <video> --slug <slug> [--brand master-solution]`
Crea el espacio, **copia** el video a `00_original/video_base.<ext>` con su `.sha256` y lo marca de solo lectura. Si no hay video: pedí únicamente ese archivo. Si la ruta apunta a algo que parece una referencia de estilo y no a la grabación de la persona, preguntá antes de usarlo.

### 2. `editoria probe <slug>`
Escribe `01_analisis/probe.json`. Revisá `warnings`:
- VFR (fps variable): el render usa el FPS de origen; avisá si hay riesgo de desfase.
- Horizontal: se recortará 9:16 centrado en el rostro; avisá que se pierde encuadre.
- Ancho < 1080: se escala sin detalle nativo nuevo; no prometas nitidez.
- Sin audio: el flujo de subtítulos no aplica; consultá si es intencional.

### 3. `editoria transcribe <slug> [--model small]`
Palabras con tiempos en `transcript.json` y `transcript_revision.md`. Las palabras con baja probabilidad llevan `flagged: true`. Corregí en el archivo de revisión nombres, términos de IA, cifras y marcas **escuchando el contexto del video**, no adivinando. Si una palabra es incierta, dejala marcada y mencionalo. `--model small` es más rápido y menos preciso.

### 4. `editoria analyze <slug>`
Silencios, cortes duros, zona del rostro (`estimated: true` si no hubo detector: tratá la caja como aproximada), `segmentos.json` por oraciones y pausas con `role` e `intent` vacíos, y `mapa_edicion.csv` con las columnas del mapa.

### 5. Completar `segmentos.json`
Editá `01_analisis/segmentos.json` (lista `segments`). Por segmento: `role` (`hook | body | example | closing | null`), `intent`, `visual`, `reference` (R01–R09, W01–W25) y `method` (`original | reframe | generated`). Criterios en `decisiones-director.md`.

### 6. Tomas complementarias (opcional)
Ver `tomas-higgsfield.md`. Sin herramienta accesible o sin límite de créditos, la V1 se hace con original y reencuadres y se declara "sin tomas generadas".

### 7. `editoria propose <slug> [--window a-b]`
Elige la ventana (el gancho, o la que indiques, de 5 a 10 s) y genera exactamente tres muestras A/B/C sobre **el mismo pasaje**, `comparativa_ABC.mp4` y `propuestas.md` (plantilla `templates/docs/Propuestas_A_B_C.md`). Completá en `propuestas.md` la recomendación y el motivo concreto. Con `proposal_mode: esperar` detenete y preguntá cuál elige la persona.

### 8. Plan V1
```
editoria plan draft <slug> --style A --out proyectos/<slug>/04_versiones/V1/plan.yaml
editoria plan lint <slug> --version V1
```
El borrador ya pasa el linter; después lo enriquecés (énfasis, gráficos, SFX, reencuadres) según el estilo elegido. Referencia del formato en `plan-yaml.md`. Volvé a correr `plan lint` tras cada edición: si devuelve ERROR, corregí el plan (los ERROR no se "negocian").

### 9. `editoria render <slug> --version V1 [--sample-window a-b] [--preset medium] [--crf 18]`
Cadena: lint → `captions build` → `graphics render` → `audio mix` → composición → `qc`. Se niega si hay ERROR del linter o si la versión ya fue entregada. Los pasos sueltos sirven para diagnosticar: `editoria captions build`, `editoria graphics render`, `editoria audio mix`, todos con `<slug> --version V1`. Para probar un tramo: `--sample-window 8-14`.

### 10. Revisión
```
editoria contact-sheet <slug> --version V1 --every 2
editoria qc <slug> --version V1
```
Ver `hojas-contacto-y-qc.md`. Si corregís el plan, repetí 8 → 10 hasta que el QC no tenga FAIL (mientras la versión no esté entregada).

### 11. `editoria deliver <slug> --version V1`
Arma el paquete (video, SRT/VTT/ASS, muestras, tomas aceptadas con su correspondencia, plan, mapa, `resumen.md`, `atribuciones.md`, consumo de créditos) y marca la versión con `.entregado`. Solo lista archivos verificados; lo demás figura como pendiente. Desde ese momento la versión es inmutable.

### 12. Cierre
Presentá la entrega (ver `SKILL.md`), hacé la pregunta de feedback y **detenete**.

## Comandos de apoyo

| Comando | Uso |
|---|---|
| `editoria graphics list` | Plantillas disponibles y sus parámetros |
| `editoria graphics preview <plantilla> --params '{"texto":"Hola"}'` | Ver una plantilla (PNG y MP4 corto) antes de ponerla en el plan |
| `editoria audio sfx` | SFX disponibles con su licencia |
| `editoria audio check-voice <slug> <archivo>` | Desfase y similitud de la voz respecto del original |
| `editoria shots budget <slug>` | Límite, gastado y restante de créditos |
| `editoria run <slug>` | Punta a punta; se detiene siempre tras V1 |
