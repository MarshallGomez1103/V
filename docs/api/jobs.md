# Proyectos, importación y jobs — Sección 5 (oleada 2026-09-21)

Todos los endpoints son locales (`127.0.0.1`), no descargan modelos ni invocan
proveedores cloud. Los errores usan `{"detail": {"code": "<snake_code>",
"message": "<texto seguro>"}}`; nunca se devuelven rutas del host ni tracebacks.
Las fechas son ISO 8601 con zona. El schema exacto se publica en `/openapi.json`.

## Proyectos

| Método y ruta | Request | Respuesta |
| --- | --- | --- |
| `POST /api/projects` | `{"name": str}` (1–200 chars tras `strip`) | 201 `{"id","name","created_at"}`; 422 `project_name_invalid` |
| `GET /api/projects` | — | `{"projects": [...]}` ordenado por `created_at` desc |

## Importación de medios

`POST /api/projects/{project_id}/media` recibe el archivo como **body crudo**
(`Content-Type: application/octet-stream`) con el header obligatorio
`X-Voz-Filename` (solo basename; el servidor lo sanea). No se usa multipart
para evitar una dependencia adicional. El servidor escribe en un temporal bajo
XDG, ejecuta `ImportMedia` (copia inmutable, SHA-256, ffprobe) y borra el
temporal siempre. La normalización a PCM mono 16 kHz ocurre dentro del job, no
en la subida.

Respuesta 201: `{"media_asset_id","project_id","filename","media_type",
"duration_ms","sha256"}`.

Códigos: 400 `filename_invalid`, 404 `project_not_found`, 413 `media_too_large`,
415 `media_unsupported`, 422 `media_corrupt`, 503 `media_storage_unavailable`,
500 `media_import_failed` (genérico, sin detalles internos).

## Jobs de transcripción

| Método y ruta | Request | Respuesta |
| --- | --- | --- |
| `POST /api/jobs` | `{"project_id","media_asset_id","option_id","language": str\|null, "diarization"?: {...}, "profile"?: str, "prompt"?: str\|null}` | 201 `JobView`; 404 `project_not_found` / `media_asset_not_found` / `option_unknown`; 409 `option_not_startable` (+`blocking_reasons`) / `job_already_active` / `insufficient_vram` / `insufficient_ram` (+`required_mib`, `available_mib`; ver "Memoria insuficiente") / `diarization_unavailable` / `diarization_models_missing` (ver "Diarización"); 422 `diarization_options_invalid` (ver "Diarización") / `quality_profile_unknown` (ver "Perfil de calidad") / `job_prompt_invalid` (ver "Instrucciones de estilo") |
| `GET /api/jobs/{job_id}` | — | `JobView`; 404 `job_not_found` |
| `GET /api/jobs?project_id=` | — | `{"jobs": [JobView]}` |
| `POST /api/jobs/{job_id}/cancel` | — | 202 `JobView` (CANCELLING/CANCELLED); 409 `job_terminal` |
| `GET /api/transcripts/{transcript_id}/segments` | — | `{"segments": [{"id","start_ms","end_ms","text"}]}`; 404 `transcript_not_found` |
| `GET /api/jobs/{job_id}/events` | — | `text/event-stream` (ver abajo) |
| `GET /api/jobs/{job_id}/preview?after_ms=` | — | `{"segments": [{"start_ms","end_ms","text"}]}`; 404 `job_not_found` (ver "Vista previa") |
| `POST /api/shutdown` | cabecera `X-VOZ-Action: shutdown` | 202 `{"status":"stopping"}`; 403 `shutdown_forbidden`; 501 `shutdown_unavailable` (ver "Cerrar el servidor") |
| `GET /api/desktop-shortcut` | — | `{"supported","exists","path"}` (ver "Icono de escritorio") |
| `POST /api/desktop-shortcut` | cabecera `X-VOZ-Action: desktop-shortcut` | 201 `{"supported","exists","path"}`; 403 `desktop_shortcut_forbidden`; 409 `desktop_shortcut_unsupported`; 500 `desktop_shortcut_failed` |

`JobView`:

```json
{
  "id": "uuid", "project_id": "uuid", "media_asset_id": "uuid",
  "state": "TRANSCRIBING", "progress": 0.42,
  "error_code": null, "diarization_error_code": null, "transcript_id": null,
  "started_at": "2026-10-03T01:18:33.481300+00:00",
  "stage_started_at": "2026-10-03T01:18:34.200000+00:00",
  "stage_progress": 0.5, "eta_seconds": 42.3,
  "selection": {
    "option_id": "option-v1-…", "provider_id": "faster-whisper",
    "model_id": "turbo", "source": "…", "revision": "sha40",
    "profile": { "...": "ProcessingProfile completo" },
    "execution": { "device": "cuda", "precision": "float16", "fallback_reason": null },
    "language": null,
    "quality_profile": { "name": "default", "version": 1, "beam_size": 5, "temperature": [0.0, 0.2, 0.4, 0.6, 0.8, 1.0], "condition_on_previous_text": true, "no_speech_threshold": 0.6, "vad": null },
    "glossary": [],
    "prompt": null,
    "diarization": { "enabled": false, "speakers": { "exact": null, "minimum": null, "maximum": null } }
  },
  "created_at": "…", "updated_at": "…"
}
```

`state` toma los valores de `TranscriptionJobState`: `QUEUED, PROBING,
PREPROCESSING, TRANSCRIBING, ALIGNING, DIARIZING, MERGING, PERSISTING,
COMPLETED, FAILED, CANCELLING, CANCELLED`. La UI muestra la etapa a partir de
este campo, nunca de logs.

### Progreso por etapa y tiempos

Además de `progress` (global, 0..1, monótono) cada `JobView` y cada evento SSE
llevan:

| Campo | Significado |
| --- | --- |
| `started_at` | ISO o `null`: cuando el job salió de `QUEUED` por primera vez. |
| `stage_started_at` | ISO o `null`: cuando empezó el estado actual (se reinicia en cada transición y cuando una etapa se rehace tras reanudar). |
| `stage_progress` | 0..1 o `null`: avance **dentro** de la etapa actual. `PREPROCESSING` = audio normalizado por ffmpeg (solo si hay que normalizar); `TRANSCRIBING` = chunks completados más la posición dentro del chunk actual; `DIARIZING` = chunks de embeddings que reporta sherpa-onnx. `null` sin medida (p. ej. `ALIGNING`, o los primeros ~20 % de la diarización: carga de modelos y segmentación, que no reportan nada) y en estados terminales. |
| `eta_seconds` | segundos estimados que faltan de **la etapa actual**, o `null`. Es `transcurrido × (1 − sp) / sp` con `transcurrido = ahora − stage_started_at`; `null` si `stage_progress` es `null` o < 0,02, y `0` si es 1. Se calcula al emitir cada evento: el cliente puede seguir descontando entre eventos. Se sobreestima al comienzo de `DIARIZING` (el tiempo de carga y segmentación cuenta como transcurrido) y tras reanudar un job interrumpido a mitad de `TRANSCRIBING`. |

`progress` pondera las etapas: `PREPROCESSING` 0–0,02, `TRANSCRIBING` 0,02–0,8
(0,02–0,98 si no se pidió diarización), `DIARIZING` 0,8–0,98 y la persistencia
final hasta 1,0. Nunca queda en 1,0 mientras el job trabaja. El runner escribe el
avance intermedio como máximo ~2 veces por segundo; los cambios de estado y los
checkpoints se escriben siempre. Migración `0008_job_stage_prompt` (columnas
`started_at`, `stage_started_at`, `stage_progress` en `transcription_jobs`; los
jobs previos quedan con `started_at = created_at`, `stage_started_at =
updated_at` y, si estaban en `ALIGNING`/`DIARIZING`/`MERGING`/`PERSISTING`, su
`progress` recortado a 0,8/0,98).

### Texto visible antes de los hablantes

Al terminar la transcripción (estado `ALIGNING`) el runner persiste ya el
`Transcript` y sus `Segment`s literales. Desde ese momento `JobView.transcript_id`
es el id del transcript **aunque el job siga en `DIARIZING`**, y
`GET /api/transcripts/{id}/segments` devuelve el texto completo con
`speaker_id: null`. Al terminar la diarización se asigna `speaker_id` a esos
mismos segmentos (sin duplicar; ids deterministas). Si la diarización falla el
transcript queda igual (`diarization_error_code`). Si el job se cancela durante
la diarización el texto **se conserva** (`CANCELLED` con `transcript_id` no nulo);
apagar el servidor deja el job en `DIARIZING` y al reabrir solo se rehace la
diarización. `transcript_id` es `null` en `QUEUED`…`TRANSCRIBING` y en jobs
fallidos antes de transcribir.

### Vista previa en vivo (`GET /api/jobs/{job_id}/preview`)

Durante `TRANSCRIBING` devuelve los segmentos ya **confirmados en checkpoints**
(un chunk de 30 min se confirma entero), con el mismo texto recortado que se
guardará y sin segmentos vacíos:

```json
{"segments": [{"start_ms": 750, "end_ms": 5250, "text": "Hacen parte de esta materia…"}]}
```

`?after_ms=<n>` (entero ≥ 0; otro valor → 422) devuelve solo los segmentos con
`end_ms > n`; el cliente pasa el mayor `end_ms` que ya tiene. 404 `job_not_found`
si el job no existe. Sigue funcionando después (los checkpoints se conservan),
pero una vez creado el transcript la fuente de verdad es
`/api/transcripts/{id}/segments`.

### Instrucciones de estilo (`prompt`)

`POST /api/jobs` acepta `prompt` (cadena opcional). Se recorta (`strip`); vacío
equivale a `null`; más de **600 caracteres** tras recortar → 422
`job_prompt_invalid` y no se crea nada. Se guarda en el snapshot
(`selection.prompt`, columna `prompt`, migración 0008) y se pasa al motor:

- **Faster Whisper**: como `initial_prompt`. Convive con el glosario del
  proyecto, que va como `hotwords`; el orden efectivo es primero las hotwords
  (la librería las antepone a cada ventana de decodificación) y después el
  prompt (solo siembra la primera ventana).
- **OpenAI** (`whisper-1`, `gpt-4o-transcribe…`): campo `prompt` de su API. El
  modelo `gpt-4o-transcribe-diarize` no lo admite y se omite.
- **ElevenLabs y whisper.cpp**: lo ignoran.

Whisper **no sigue instrucciones como un chat**: el prompt solo condiciona el
estilo del texto (puntuación, mayúsculas, ortografía, vocabulario y nombres
propios), como si fuera el texto que precede al audio. «Transcribe en tercera
persona» o «resume» no funcionan; un ejemplo de cómo debería verse el texto sí.

### Cerrar el servidor (`POST /api/shutdown`)

Pensado para el botón «Cerrar VOZ» de la web. Exige la cabecera
`X-VOZ-Action: shutdown`; sin ella (o con otro valor) → 403
`shutdown_forbidden`. Una cabecera propia obliga a otro origen a pasar por un
preflight CORS, que VOZ nunca concede. Responde 202 `{"status":"stopping"}` y
unos 0,5 s después pide a uvicorn que termine (`should_exit`): la misma salida
ordenada que Ctrl+C, el proceso termina con código 0 y el job en curso queda
recuperable al reabrir. 501 `shutdown_unavailable` si el servidor no lo lanzó el
comando `voz` (p. ej. `uvicorn voz.bootstrap:app` directo). Tras la respuesta el
cliente debe asumir que la API deja de responder.

### Icono de escritorio (`/api/desktop-shortcut`)

Crea un acceso directo en el escritorio y en el menú de aplicaciones que ejecuta
el lanzador `Iniciar-*` de la carpeta de VOZ, con el icono de
`packaging/icons/` (`voz.png`, `voz.ico`, `voz.svg`, derivados de
`favicon.svg`). Solo biblioteca estándar y lo que trae cada sistema.

`GET` → `{"supported": bool, "exists": bool, "path": str|null}`. `supported` es
`false` si VOZ no corre desde una carpeta con lanzadores (p. ej. instalado como
wheel) o en un SO sin soporte. `exists` es `true` si el acceso que creó VOZ sigue
en su sitio. `path` es dónde quedó, con el directorio personal abreviado como
`~` (nunca rutas absolutas del host).

`POST` (cabecera `X-VOZ-Action: desktop-shortcut`; 403
`desktop_shortcut_forbidden` sin ella) crea o rehace el acceso y responde 201 con
el mismo cuerpo que `GET`. 409 `desktop_shortcut_unsupported`; 500
`desktop_shortcut_failed` (mensaje sin rutas). Linux: `voz.desktop` en el
escritorio (`xdg-user-dir DESKTOP`) y en `$XDG_DATA_HOME/applications`, con
`gio set … metadata::trusted` si existe `gio`. Windows: `VOZ.lnk` vía PowerShell
(respeta un escritorio movido por OneDrive). macOS: `VOZ.app` mínima que abre
`Iniciar-Mac.command` en Terminal (icono `.icns` con `sips`, si está). El
registro de dónde quedó vive en `<state>/desktop-shortcut.txt`, nunca en la
carpeta del código.

### Selección reproducible (S5.20)

Al crear el job se revalida `option_id` contra la consulta actual de
`/api/transcription-options`; si `can_start` es falso se responde 409 con los
`blocking_reasons`. El job guarda un snapshot completo (proveedor, modelo,
procedencia, revisión, perfil, decisión de ejecución e idioma) en
`transcription_job_selections`. El `option_id` solo no es un checkpoint
reproducible.

### Perfil de calidad y glosario (S13.01-S13.03)

`profile` (opcional, por defecto `"default"`) elige una receta de decodificación
de `GET /api/quality-profiles`; un nombre desconocido responde 422
`quality_profile_unknown` y no crea nada. La selección guarda en
`quality_profile` el perfil **completo** con sus parámetros efectivos (no solo el
nombre) y en `glossary` los términos del glosario del proyecto **en el momento de
crear el job** (ver `docs/api/projects.md`); editar el glosario después no
cambia jobs ya creados. Los jobs anteriores a esta función devuelven
`quality_profile: null` y `glossary: []` y siguen con los valores por defecto del
motor. Detalle, parámetros y qué motores lo respetan: `docs/quality-profiles.md`.

### Eventos SSE (S5.06)

`GET /api/jobs/{job_id}/events` emite `event: job` con `data: JobView` al
conectar y cada vez que cambian `state`, `progress`, `stage_progress`,
`stage_started_at` o `updated_at` (sondeo del
repositorio cada ~500 ms, sin bloquear el event loop). Envía `: ping` como
keep-alive cada 15 s. Al llegar a un estado terminal emite el último `job` y
`event: end`, y cierra. Job inexistente → 404 antes de abrir el stream.

### Ejecución y recuperación (S14.01, S14.08)

Un `JobRunner` en un hilo procesa jobs de uno en uno: `PREPROCESSING` normaliza
si falta el derivado, `TRANSCRIBING` ejecuta la transcripción recuperable por
chunks con checkpoints SQLite, `ALIGNING` crea `Transcript` y `Segment`s
literales (visibles desde ya) y `DIARIZING` asigna los hablantes. Al arrancar el servidor se re-encolan los jobs procesables sin
repetir chunks confirmados. `POST …/cancel` marca `CANCELLING` y el runner
termina en `CANCELLED` entre unidades recuperables. Los fallos se exponen como
`error_code` estable.

### Espacio en disco insuficiente (S14.03)

Antes de importar un original se exige `tamaño del archivo + 64 MiB` libres en
el almacén de originales; antes de normalizar, `duration_ms * 32` bytes (PCM
mono 16 kHz s16) `+ 64 MiB` en el almacén de derivados. Si no alcanza, el error
tipado `InsufficientDiskSpace` (`code="disk_space_insufficient"`,
`retryable=true`) se traduce así, sin dejar artefactos parciales:

| Contexto | Resultado |
| --- | --- |
| `POST /api/projects/{project_id}/media` | 507 `{"detail": {"code": "disk_space_insufficient", "message": …}}`; el temporal de subida se elimina. También se devuelve 507 si el disco se llena mientras se recibe el cuerpo (`ENOSPC`). |
| `JobRunner` (normalización pendiente) | job `FAILED` con `error_code = "disk_space_insufficient"`; el job no se reintenta solo, la UI puede ofrecer reintentar tras liberar espacio. |

La comprobación es opcional en los casos de uso (`disk_space=None` la omite) y
se cablea en `bootstrap.py` con el adaptador `ShutilDiskSpace`.

### Memoria insuficiente (S14.05, S14.06)

`POST /api/jobs` compara la memoria **libre medida** (VRAM vía `nvidia-smi`; RAM
vía `/proc/meminfo`, `MemAvailable`) con el requisito estimado del modelo en el
dispositivo y precisión que la opción ya resolvió (`execution`). Si no alcanza,
no se crea el job y se responde 409:

```json
{"detail": {"code": "insufficient_vram", "message": "Not enough free GPU memory to load this model. Choose a smaller model or use the CPU.", "required_mib": 5000, "available_mib": 1200}}
```

`insufficient_ram` es análogo para CPU (mensaje: elegir un modelo menor o liberar
memoria). El mensaje nunca incluye el nombre de la GPU ni rutas; la sugerencia va
en el propio texto y el cliente puede comparar `required_mib`/`available_mib`.

Requisitos aproximados (MiB; `application/resource_requirements.py`, estimación
conservadora, no medida sobre VOZ): VRAM float16 tiny 600, base 800, small 1500,
medium 3000, turbo 2500, large-v3 5000 (x0,7 para `int8`/`int8_float16`); RAM en
CPU int8 tiny 500, base 600, small 1000, medium 2200, turbo 2200, large-v3 3500
(x2 para precisiones más anchas). Un modelo fuera de la tabla, o memoria sin
medir, **nunca bloquea**: la estimación es un aviso temprano, no una garantía.

### Idempotencia de la reanudación (S14.14)

`recover()` y `enqueue()` no duplican un job ya en cola o en ejecución. Al
persistir, `Transcript` y `Segment`s usan identidades deterministas
(`uuid5` del job), por lo que reanudar tras una interrupción en
`ALIGNING`/`DIARIZING`/`PERSISTING` añade solo los segmentos que faltan: el resultado es idéntico al de una
ejecución limpia y repetir la etapa no duplica nada.

## Diarización (S6.13, S6.15, S14.07)

La diarización (quién habla) es una etapa **opcional** del job, desactivada por
defecto y siempre local (sherpa-onnx, ADR-0007). Se pide al crear el job:

```json
{"project_id": "…", "media_asset_id": "…", "option_id": "…",
 "diarization": {"enabled": true, "speakers": {"exact": 2}}}
```

| Campo | Regla |
| --- | --- |
| `diarization` | opcional; ausente o `null` = desactivada |
| `enabled` | booleano; si falta se toma `false`. Con `false` se ignora `speakers` (aunque se valida su forma) |
| `speakers` | objeto opcional con `exact`, `minimum`, `maximum` (enteros de 1 a 32; `null` equivale a ausente). `exact` excluye a los otros dos y `minimum <= maximum`. Sin pistas, el motor estima el número de hablantes |

Errores:

- 422 `diarization_options_invalid`: forma o valores inválidos (campo desconocido,
  no booleano/entero, fuera de 1–32, `exact` junto a `minimum`/`maximum`,
  `minimum > maximum`). Se evalúa antes de tocar el proyecto o la opción.
- 409 `diarization_models_missing`: se pidió activar la diarización y los
  modelos de hablantes **no están instalados** (se arregla descargándolos). No se
  crea nada. Para saber antes de crear el job si están instalados, consultar
  `GET /api/models` y mirar la entrada `diarization:sherpa-default`
  (`kind: "diarization"`, `installed`, `runtime_available`); se descargan con
  `POST /api/models/diarization:sherpa-default/install`
  `{"method":"download","confirm":true}` (ver `docs/api/models.md`).
- 409 `diarization_unavailable`: se pidió activar la diarización pero falta el
  runtime (extra `diarization`; descargar modelos no lo arregla) o no está
  cableada. Se evalúa antes que `diarization_models_missing`. No se crea el
  job; pedirla desactivada funciona siempre. La disponibilidad la decide el port
  `DiarizationAvailability` (`runtime_available`, `models_installed`),
  cableado en `bootstrap.py`.

La petición se guarda en el snapshot del job (`transcription_job_selections`,
columna `diarization_json`, migración `0005_job_diarization`) y se devuelve en
`JobView.selection.diarization` como `{"enabled": bool, "speakers": {"exact",
"minimum", "maximum"}}` (`null` en lo no pedido). Las filas anteriores a la
migración quedan con la diarización desactivada.

### Etapa del pipeline

Con la diarización activa el runner, tras `TRANSCRIBING` (y `ALIGNING`):

1. entra en `DIARIZING` con el transcript ya persistido (ver "Texto visible
   antes de los hablantes"), **libera el motor ASR** mediante el callback
   inyectado `release_asr(selection)` (S6.15/S14.07: los modelos de ASR y de
   diarización nunca conviven en memoria) y ejecuta el `DiarizationProvider`
   sobre el mismo derivado normalizado que usó el ASR, informando
   `stage_progress`;
2. sin salir de `DIARIZING`, `AssignSpeakers` guarda `Speaker`s, `SpeakerTurn`s
   y asigna `speaker_id` a los segmentos ya existentes. Es idempotente: reanudar
   tras una caída en `DIARIZING` vuelve a diarizar (los turnos vivían solo en
   memoria) y reutiliza los `Speaker`s ya creados.

Cancelación (`POST …/cancel`) y apagado del servidor se atienden entre etapas y
también **dentro** de la diarización (mismo token): cancelar termina en
`CANCELLED` conservando el texto; apagar deja el job en `DIARIZING` para
reanudarlo.

Velocidad: sherpa-onnx corre en CPU con `min(8, núcleos − 1)` hilos (antes 2).
Medido con 11 min de audio sintético en una CPU de 20 hilos (con otra carga
activa): 2 hilos 147 s, 4 hilos 85 s, 8 hilos 70 s, 19 hilos 79 s. No se usa
CUDA (no hay wheel GPU de sherpa-onnx instalada).

### Fallo de diarización: el ASR nunca se pierde

Si la diarización falla (modelo ausente, runtime ausente, fallo del proveedor o
de la asignación), el transcript **se persiste igual** y el job termina
`COMPLETED` con `error_code = null`. El fallo se expone en
`JobView.diarization_error_code`, un código estable
(`diarization_model_unavailable`, `diarization_runtime_unavailable`,
`diarization_invalid_audio`, `diarization_provider_failed`; nunca mensajes ni
rutas). El código se persiste en `transcription_job_selections.diarization_error_code`
(misma migración) y no se reintenta solo: un job con el código guardado no
vuelve a diarizar al reanudarse. Se eligió la tabla de selecciones y no
`transcription_jobs` para no ampliar la entidad de dominio `TranscriptionJob`,
cuyo `error_code` solo es válido para jobs `FAILED`.

### Umbral de clustering y hablantes residuales (plan v3, CP-A3)

Por defecto el motor estima el número de hablantes con un umbral de distancia
(`DEFAULT_THRESHOLD` en `infrastructure/diarization/sherpa.py`). Medido con la
grabación real de una clase de 1 h 47 min (profesor y pocos estudiantes), sobre
copia de la base y los medios en un XDG temporal:

| Umbral | Clusters crudos | Tras fundir residuales | Reparto del habla tras fundir |
| --- | --- | --- | --- |
| 0.3 | 11 | 5 | 35.7 / 32.9 / 21.0 / 6.7 / 3.6 % |
| **0.4** (default) | 6 | **3** | 69.0 / 27.5 / 3.5 % |
| 0.45 | 5 | 2 | 68.9 / 31.1 % |
| 0.5 | 3 | 2 | 68.5 / 31.5 % |
| 0.6 | 2 | 2 | 68.5 / 31.5 % |
| 0.7 | 1 | 1 | 100 % |

Con 0.3 el profesor aparece partido en dos clusters (35.7 % + 32.9 % ≈ el 69 % que
un solo cluster agrupa desde 0.4). 0.4 conserva al profesor entero y una tercera
voz; unir dos hablantes en la UI es fácil, separar uno no. El default era 0.3.

**Hablantes residuales.** El proveedor funde cada cluster con muy poca habla
(menos del 2 % del habla total, o menos de 10 s con un tope del 5 % para que un
audio corto no pierda a sus dos interlocutores) en el cluster mayor más cercano
**en el tiempo** (`application/diarization_cleanup.py`; marcado `ponytail:`
porque el motor no expone embeddings). Nunca baja del `exact`/`minimum` pedido.
En la grabación real: 11 clusters crudos a 0.3 pasan a 5.

**El motor corre en un proceso hijo** (`infrastructure/diarization/worker.py`).
La llamada nativa de sherpa-onnx retiene el GIL todo el paso de segmentación
(unos 4 min en 1 h 47 min), lo que congelaba el servidor entero: el SSE, el
progreso y el botón Cancelar. Medido en un clip de 4 min: hueco máximo de un hilo
latido 8.3 s antes, 0.1 s ahora. Cancelar mata el hijo en menos de 0.2 s incluso
en la fase silenciosa. Coste: los modelos se recargan en cada pasada (~1 s).

## Recalcular hablantes (`POST /api/transcripts/{transcript_id}/rediarize`)

Recalcula **solo** los hablantes de una transcripción terminada, sin volver a
transcribir (no se llama al ASR ni se tocan textos, tiempos, ediciones ni
revisiones).

```json
{"speakers": {"exact": 2}}
```

`speakers` admite `exact`, `minimum`, `maximum` con las reglas de la
diarización (1–32, `exact` excluye a los otros, `minimum <= maximum`); `{}` o sin
`speakers` = el motor estima. → **202** con la vista del job (`JobView`, como
`POST /api/jobs`): es **el mismo job de la transcripción**, reabierto en
`DIARIZING` (`progress` 0.8, `stage_progress` `null` al inicio, `transcript_id`
el de siempre). Se sigue con `GET /api/jobs/{id}` o el SSE
`/api/jobs/{id}/events` (que hay que volver a abrir tras el 202): `stage_progress`
y `eta_seconds` como en cualquier job, y al acabar vuelve a `COMPLETED`.

| Estado | Código | Significado |
| --- | --- | --- |
| 404 | `transcript_not_found` | la transcripción no existe |
| 409 | `rediarize_unavailable` | no hay un job que la haya producido |
| 409 | `job_already_active` | hay otro job sin terminar (el worker es único) |
| 409 | `diarization_unavailable` | falta el runtime de diarización |
| 409 | `diarization_models_missing` | faltan los modelos de hablantes (se bajan en el gestor de modelos) |
| 422 | `diarization_options_invalid` | cuerpo inválido |

Semántica:

- Se guardan las nuevas pistas en la selección del job
  (`transcription_job_selections.diarization_json`, y se limpia
  `diarization_error_code`); el estado `COMPLETED`/`FAILED`/`CANCELLED` previo se
  pierde (la entidad ofrece `reopen_for_diarization`). Sin migración.
- **Nombres y colores se conservan por solapamiento**: cada cluster nuevo toma al
  hablante antiguo que habla en los mismos tramos, si ese solapamiento cubre al
  menos el 50 % del habla del cluster o el 50 % del habla del hablante antiguo
  (una persona que el cálculo anterior había partido y ahora vuelve entera
  conserva su nombre). Un hablante antiguo va a un solo cluster, el de mayor
  solapamiento primero (`application/speaker_matching.py`); un cluster que
  mezcla varias personas antiguas toma el nombre de la que más solapa, como al
  fusionar a mano. Los demás reciben "Speaker N" y un color libre de la paleta.
  Los hablantes antiguos que ya nadie referencia se borran.
- Las asignaciones manuales de segmentos a hablantes (`PUT /api/segments/{id}/speaker`)
  **se reemplazan** por las del nuevo cálculo.
- Si el recálculo falla (modelos, audio, proveedor) el job termina `COMPLETED`
  con `diarization_error_code` y los hablantes anteriores intactos (misma regla que
  el primer cálculo). Si el derivado de audio ya no existe se regenera.
- Cancelar (`POST /api/jobs/{id}/cancel`) lo deja `CANCELLED` con el texto y los
  hablantes anteriores intactos; se puede volver a recalcular (cualquier job
  terminal con transcript sirve). Si el servidor se apaga a mitad, el job queda
  en `DIARIZING` y se reanuda al arrancar.
- `GET /api/library` muestra el job como `DIARIZING` mientras dura.
