# Demo: capturas de la app real (S16.02)

Todas las imágenes de `docs/assets/screenshots/` son capturas de la interfaz de VOZ
corriendo de verdad, sin maquetas. Se generan con un script, así que se pueden
rehacer cuando cambie la UI.

**Fecha:** 2026-09-30. **Commit base:** `46f2e1d` (más los cambios sin commitear de
la oleada 5c-2 en el árbol de trabajo). **Máquina:** Bazzite `bazzite-nvidia-open`
(Fedora 44, kernel 7.2.7), NVIDIA GeForce RTX 4060 Laptop, Chrome 154 (flatpak)
en modo headless, ventana de 1440 px de ancho.

## Qué datos se usan

- **Audio:** `reunion-demo.wav`, 17 s, generado en el momento con `espeak-ng`
  (español, dos voces sintéticas que alternan, `es+f3` y `es+m3`). No es una
  grabación de nadie.
- **Motor:** Faster Whisper `turbo` sobre GPU (CUDA, float16), real. El modelo se
  importa por la API (`POST /api/models/faster-whisper:turbo/install` con
  `method=import`, `origin=buzz`) desde el caché de Buzz que ya existe en el
  equipo: hardlink de solo lectura, no se descarga ni se modifica nada.
- **Datos de VOZ:** un directorio temporal con sus propios `XDG_*`; el script
  nunca toca `~/.local/share/voz`, `~/.config/voz` ni `~/.local/state/voz`, y lo
  borra al terminar. El servidor se apaga siempre (`trap`).

El texto transcrito en las capturas es salida real del modelo, sin retocar
(en esta ejecución, el primer segmento salió como «…repasar la entrega en el proyecto de
ingeniería», aunque el texto hablado decía «…entrega del proyecto…»).

## Capturas

| Archivo | Qué muestra | Función real |
| --- | --- | --- |
| `01-inicio.png` | Pantalla de inicio: tarjeta de importación, estado local de la API y gestor de modelos con `turbo` instalado | Importación (S5), estado (`/api/health`), gestor de modelos |
| `02-selector-motor.png` | Tras importar el audio: «Elige el motor» con las opciones de `/api/transcription-options` (Faster Whisper local con modelo instalado o no, y proveedores cloud marcados «CLOUD» y bloqueados sin clave) y la casilla «Detectar quién habla» | Selector de motor y opciones |
| `03-job-en-curso.png` | La tarjeta del job mientras corre, con fases y botón Cancelar | Job con estados por SSE (S5.05/S5.06). Solo se guarda si el script alcanza a verlo; con la GPU el job puede acabar antes |
| `04-job-terminado.png` | El job completado: modelo, perfil y dispositivo (`cuda`) | Job y su selección reproducible |
| `05-forma-de-onda.png` | Reproductor del original y forma de onda con zoom | Reproductor y waveform (S7) |
| `06-transcripcion.png` | Modo Leer/Editar, exportación, panel de hablantes, cola de revisión y la lista de segmentos con marcas de tiempo | Segmentos, exportación, revisión |
| `07-gestor-modelos.png` | Gestor de modelos: `turbo` instalado (1,6 GB), `large-v3` «Disponible en Buzz» con «Importar desde Buzz», el resto «No instalado», la sección «Hablantes» y los proveedores cloud sin configurar | Gestor de modelos (S8), importación desde Buzz |

### Lo que estas capturas no muestran

- **Hablantes separados.** La separación de hablantes necesita el modelo
  `diarization:sherpa-default`, que no está instalado en esta máquina y no se
  descargó para las capturas. El panel sale vacío («Esta transcripción no tiene
  hablantes») y aparece «No instalado» en el gestor. Hasta capturarlo con el
  modelo instalado, no se anuncia como demostrado.
- **Palabras con timing.** El segmento se compone de palabras clicables (37 en esta
  demo, comprobado en el DOM por el script), pero a la vista se leen como texto
  normal: la palabra actual solo se resalta durante la reproducción.
- Nada cloud: no hay claves configuradas y no se llama a ningún proveedor.

## Regenerarlas

```bash
scripts/capture-screenshots.sh                 # reescribe docs/assets/screenshots/
scripts/capture-screenshots.sh /otra/ruta      # salida alternativa
```

Requisitos: `uv` con el entorno del proyecto ya sincronizado (extra `asr-local`:
el script arranca el servidor con `uv run --no-sync` para no quitárselo), `node`
22 o superior, `ffmpeg`, `espeak-ng`, Chrome en flatpak (`com.google.Chrome`) y el
modelo `turbo` en el caché de Buzz. Sin ese modelo el script avisa y solo hace las
capturas que no lo necesitan (`01`, `02` y `07`; esta ruta no se ha probado). Tarda unos
10 segundos. Variables opcionales: `VOZ_CMD`, `CAPTURE_MODEL` (por defecto
`turbo`) y `CHROME_CMD` (por defecto `flatpak run com.google.Chrome`).

Cómo funciona, por si hay que mantenerlo:

- La UI guarda su estado solo en memoria, así que `chrome --screenshot` sirve
  únicamente para la pantalla inicial. El resto se maneja con el protocolo de
  depuración de Chrome (CDP) desde `scripts/capture-screenshots.mjs` (WebSocket
  y `fetch` de Node, sin dependencias): importa el audio inyectando un `File` en
  el campo de archivo, elige el motor, pulsa Transcribir y recorta cada tarjeta.
- El perfil de Chrome se crea en `~/Downloads/voz-capture-chrome.*` porque el
  sandbox flatpak solo puede escribir ahí; se borra al terminar. El audio no
  pasa por el disco del navegador, así que no hace falta ampliar permisos.
- El directorio temporal de datos se crea bajo `~/.cache/voz-capture.*` para
  estar en el mismo sistema de archivos que el caché de Buzz (los hardlinks no
  cruzan sistemas de archivos).
- Las filas de segmentos usan `content-visibility: auto`: solo se pintan a la
  vista, así que la captura de la transcripción hace scroll antes de recortar.
- Si cambia la UI (selectores `.options-card`, `.job-card`, `.audio-card`,
  `.transcript-tools`, `.segments-card`, `.model-manager`), ajusta el `.mjs`.
