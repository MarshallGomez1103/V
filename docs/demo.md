# Demo: capturas de la app real (S16.02)

Todas las imágenes de `docs/assets/screenshots/` son capturas de la interfaz de VOZ
corriendo de verdad, sin maquetas. Se generan con un script, así que se pueden
rehacer cuando cambie la UI.

**Fecha:** 2026-10-03 (UI Carbon con temas, acentos, español/inglés, progreso en vivo y línea de tiempo de hablantes; capturas en tema oscuro, español salvo la 09). **Commit base:** `46f2e1d` (más los cambios sin commitear de
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
| `01-inicio.png` | Inicio (`#/`, UI Shell de Carbon): estado de la API y la biblioteca de transcripciones; vacía al empezar, con los pasos para empezar y el botón «Nueva transcripción» | `/api/health`, biblioteca (`/api/library`) |
| `02-selector-motor.png` | Configuración tras importar: ficha y reproductor del original, «Motor y calidad» (motor, perfil y sus parámetros técnicos con tooltips), «Opciones» (hablantes, instrucciones de estilo, glosario) y el botón Transcribir | Selector de motor (`/api/transcription-options`), perfiles, glosario |
| `03-hablantes-modelo.png` | «Detectar quién habla» activado sin el modelo de hablantes: aviso, botón «Descargar modelo de hablantes (33 MB)» en línea y Transcribir bloqueado hasta tenerlo | Modelo `diarization:*` del gestor de modelos |
| `04-job-en-curso.png` | El job mientras corre: etapas con su avance, tiempo transcurrido, restante estimado, dispositivo y modelo, y una frase de lo que ocurre. Solo se guarda si el script alcanza a verlo; con la GPU el job puede acabar antes | Job por SSE (`started_at`, `stage_progress`, `eta_seconds`) |
| `05-job-terminado.png` | El job completado: etapas, duración del trabajo, modelo, dispositivo (`cuda`) y perfil | Job y su selección reproducible |
| `06-reproduccion.png` | Reproductor con controles Carbon (play/pausa, ±5 s, posición, volumen, velocidad) y forma de onda con zoom | Reproductor y waveform (S7) |
| `07-transcripcion.png` | Lista de transcripción (hablante a la izquierda, tiempos por bloque, texto grande), modo Leer/Editar con autoguardado y búsqueda | Segmentos, edición (S5/S7) |
| `08-propiedades.png` | Panel de propiedades (archivo, idioma, modelo, perfil, calidad, dispositivo), Exportar, Hablantes (renombrar, color, fusionar) y cola de revisión | Exportación, hablantes, revisión |
| `09-english.png` | Los mismos paneles en inglés, desde el selector de idioma de la cabecera | i18n español/inglés |
| `10-ajustes.png` | Menú de ajustes: tema (Automático, White, Gray 10, 90 y 100), color de acento e icono de escritorio | Preferencias en `localStorage`, `/api/desktop-shortcut` |
| `12-biblioteca.png` | Inicio con la transcripción guardada: tabla con buscar, nombre (enlace a su propia URL `#/t/<id>`), fecha, duración, estado, hablantes y las acciones Abrir, Renombrar y Eliminar | Biblioteca (`GET /api/library`), `PATCH`/`DELETE /api/projects/{id}` |
| `13-exportar.png` | Modal «Exportar transcripción»: formato con su utilidad, opciones explicadas («Incluir tiempos», «Agrupar por hablante») y vista previa de las primeras líneas con las opciones actuales | Exportación (`/api/transcripts/{id}/export`) |
| `14-hablantes.png` | Panel de hablantes con tiempo de habla y porcentaje, filtrar la transcripción, saltar a la intervención anterior/siguiente, escuchar una muestra y «Recalcular hablantes». Solo se genera con `CAPTURE_DIARIZATION_DIR` | `/api/transcripts/{id}/speakers` (`talk_ms`, `first_ms`), `POST /api/transcripts/{id}/rediarize` |
| `15-audio.png` | Reproductor con volumen al 200 % (aviso de saturación), velocidad en desplegable y la línea de atajos | Web Audio (`GainNode`), reproductor (S7) |
| `11-gestor-modelos.png` | Gestor de modelos (`DataTable`): estados rectangulares con tooltip, tamaños reales (en catálogo y en disco), sección «Hablantes» | Gestor de modelos (S8) |

### Lo que estas capturas no muestran

- **Hablantes separados (sin `CAPTURE_DIARIZATION_DIR`).** El entorno de capturas es
  una carpeta temporal sin el modelo `diarization:sherpa-default` (no se descarga para
  las capturas). Por eso el panel de hablantes sale vacío y la línea de tiempo no se ve;
  sí se ve el aviso de descarga (`03`). Con `CAPTURE_DIARIZATION_DIR` apuntando a una
  carpeta con ese modelo (se copia al temporal, nunca se modifica) la transcripción
  pide hablantes y se genera `14-hablantes.png`.
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
capturas que no lo necesitan (`01` y `11`; esta ruta no se ha probado). Tarda unos
10 segundos. Variables opcionales: `VOZ_CMD`, `CAPTURE_MODEL` (por defecto
`turbo`), `CHROME_CMD` (por defecto `flatpak run com.google.Chrome`) y
`CAPTURE_DIARIZATION_DIR` (carpeta del modelo de hablantes, opcional; ver arriba).

Cómo funciona, por si hay que mantenerlo:

- Las rutas son por hash (`#/`, `#/nueva`, `#/t/<id>`, `#/modelos`, `#/proveedores`), pero
  la importación y las configuraciones viven en memoria, así que `chrome --screenshot`
  sirve únicamente para pantallas sueltas. El resto se maneja con el protocolo de
  depuración de Chrome (CDP) desde `scripts/capture-screenshots.mjs` (WebSocket
  y `fetch` de Node, sin dependencias): fuerza `prefers-color-scheme: dark`,
  importa el audio inyectando un `File` en el campo de archivo, elige el motor,
  pulsa Transcribir y recorta cada panel (`section[aria-labelledby="…-title"]`).
  Si cambian esos ids o clases de la UI, hay que ajustar los selectores del script.
- El perfil de Chrome se crea en `~/Downloads/voz-capture-chrome.*` porque el
  sandbox flatpak solo puede escribir ahí; se borra al terminar. El audio no
  pasa por el disco del navegador, así que no hace falta ampliar permisos.
- El directorio temporal de datos se crea bajo `~/.cache/voz-capture.*` para
  estar en el mismo sistema de archivos que el caché de Buzz (los hardlinks no
  cruzan sistemas de archivos).
- Las filas de segmentos usan `content-visibility: auto`: solo se pintan a la
  vista, así que la captura de la transcripción hace scroll antes de recortar.
- Si cambia la UI (paneles `options-title`, `extras-title`, `job-title`,
  `audio-title`, `segments-title`, `props-title`, `review-title`, la clase
  `.voz-models`, `.voz-library`, `.voz-export` y los botones de la cabecera por su nombre accesible), ajusta el `.mjs`.
- La UI elige idioma según el navegador: el script fija `voz.lang=es` en
  `localStorage` antes de cargar. Con `CHROME_NO_SANDBOX=1` añade `--no-sandbox`
  (para un Chromium local en vez del Chrome de flatpak).
