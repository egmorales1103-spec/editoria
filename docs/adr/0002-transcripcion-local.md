# ADR-0002: Transcripción local con faster-whisper

- Estado: aceptada
- Fecha: 8 de noviembre de 2026

## Contexto

La edición necesita la transcripción con tiempos por palabra para subtítulos, énfasis, segmentación y detección de términos dudosos. El video es material personal o de clientes: contiene rostro, voz y posiblemente información de negocio.

## Decisión

Transcribir **localmente** con [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (extra opcional `transcribe`):

- `word_timestamps` activado, idioma español por defecto.
- El glosario de la marca se pasa como `initial_prompt` para mejorar nombres y términos.
- Modelo configurable: por defecto `large-v3-turbo` en CPU con cuantización int8; `small` como alternativa rápida.
- Las palabras con probabilidad menor a 0,6 se marcan `flagged` y se listan en `transcript_revision.md`. No se inventan palabras.
- Caché por hash del audio: no se vuelve a transcribir lo que no cambió.
- Un backend `fixture` permite tests sin modelos ni red.

## Consecuencias

- Los videos no salen de la máquina para transcribirse (privacidad por defecto); funciona sin conexión una vez descargado el modelo.
- Costo: descarga única del modelo (de 1 a 3 GB según el tamaño) y tiempo en CPU. `editoria doctor` avisa si el modelo no está en caché; no es un error bloqueante.
- La calidad depende del modelo elegido; por eso las palabras dudosas se marcan y se revisan.

## Alternativas descartadas

- **API de transcripción en la nube:** mejor velocidad y calidad en equipos modestos, pero implica enviar el audio a un tercero y requiere claves y costos. Se puede agregar como backend opcional en el futuro, apagado por defecto.
- **Subtítulos automáticos del editor de video:** no son reproducibles ni accesibles desde la CLI.
