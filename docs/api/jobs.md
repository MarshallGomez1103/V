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
| `POST /api/jobs` | `{"project_id","media_asset_id","option_id","language": str\|null, "diarization"?: {...}}` | 201 `JobView`; 404 `project_not_found` / `media_asset_not_found` / `option_unknown`; 409 `option_not_startable` (+`blocking_reasons`) / `job_already_active` / `insufficient_vram` / `insufficient_ram` (+`required_mib`, `available_mib`; ver "Memoria insuficiente") / `diarization_unavailable`; 422 `diarization_options_invalid` (ver "Diarización") |
| `GET /api/jobs/{job_id}` | — | `JobView`; 404 `job_not_found` |
| `GET /api/jobs?project_id=` | — | `{"jobs": [JobView]}` |
| `POST /api/jobs/{job_id}/cancel` | — | 202 `JobView` (CANCELLING/CANCELLED); 409 `job_terminal` |
| `GET /api/transcripts/{transcript_id}/segments` | — | `{"segments": [{"id","start_ms","end_ms","text"}]}`; 404 `transcript_not_found` |
| `GET /api/jobs/{job_id}/events` | — | `text/event-stream` (ver abajo) |

`JobView`:

```json
{
  "id": "uuid", "project_id": "uuid", "media_asset_id": "uuid",
  "state": "TRANSCRIBING", "progress": 0.42,
  "error_code": null, "diarization_error_code": null, "transcript_id": null,
  "selection": {
    "option_id": "option-v1-…", "provider_id": "faster-whisper",
    "model_id": "turbo", "source": "…", "revision": "sha40",
    "profile": { "...": "ProcessingProfile completo" },
    "execution": { "device": "cuda", "precision": "float16", "fallback_reason": null },
    "language": null,
    "diarization": { "enabled": false, "speakers": { "exact": null, "minimum": null, "maximum": null } }
  },
  "created_at": "…", "updated_at": "…"
}
```

`state` toma los valores de `TranscriptionJobState`: `QUEUED, PROBING,
PREPROCESSING, TRANSCRIBING, ALIGNING, DIARIZING, MERGING, PERSISTING,
COMPLETED, FAILED, CANCELLING, CANCELLED`. La UI muestra la etapa a partir de
este campo, nunca de logs.

### Selección reproducible (S5.20)

Al crear el job se revalida `option_id` contra la consulta actual de
`/api/transcription-options`; si `can_start` es falso se responde 409 con los
`blocking_reasons`. El job guarda un snapshot completo (proveedor, modelo,
procedencia, revisión, perfil, decisión de ejecución e idioma) en
`transcription_job_selections`. El `option_id` solo no es un checkpoint
reproducible.

### Eventos SSE (S5.06)

`GET /api/jobs/{job_id}/events` emite `event: job` con `data: JobView` al
conectar y cada vez que cambian `state`, `progress` o `updated_at` (sondeo del
repositorio cada ~500 ms, sin bloquear el event loop). Envía `: ping` como
keep-alive cada 15 s. Al llegar a un estado terminal emite el último `job` y
`event: end`, y cierra. Job inexistente → 404 antes de abrir el stream.

### Ejecución y recuperación (S14.01, S14.08)

Un `JobRunner` en un hilo procesa jobs de uno en uno: `PREPROCESSING` normaliza
si falta el derivado, `TRANSCRIBING` ejecuta la transcripción recuperable por
chunks con checkpoints SQLite, y `PERSISTING` crea `Transcript` y `Segment`s
literales. Al arrancar el servidor se re-encolan los jobs procesables sin
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
(`uuid5` del job), por lo que reanudar tras una interrupción en `PERSISTING`
añade solo los segmentos que faltan: el resultado es idéntico al de una
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
- 409 `diarization_unavailable`: se pidió activar la diarización pero no están
  instalados los modelos o falta el runtime (extra `diarization`). No se crea el
  job; pedirla desactivada funciona siempre. La disponibilidad la decide el port
  `DiarizationAvailability`, cableado en `bootstrap.py`; sin cablear cuenta como
  no disponible.

La petición se guarda en el snapshot del job (`transcription_job_selections`,
columna `diarization_json`, migración `0005_job_diarization`) y se devuelve en
`JobView.selection.diarization` como `{"enabled": bool, "speakers": {"exact",
"minimum", "maximum"}}` (`null` en lo no pedido). Las filas anteriores a la
migración quedan con la diarización desactivada.

### Etapa del pipeline

Con la diarización activa el runner, tras `TRANSCRIBING` (y `ALIGNING`):

1. entra en `DIARIZING`, **libera el motor ASR** mediante el callback inyectado
   `release_asr(selection)` (S6.15/S14.07: los modelos de ASR y de diarización
   nunca conviven en memoria) y ejecuta el `DiarizationProvider` sobre el mismo
   derivado normalizado que usó el ASR;
2. en `PERSISTING`, tras crear el transcript y sus segmentos, `AssignSpeakers`
   guarda `Speaker`s, `SpeakerTurn`s y asigna `speaker_id` a cada segmento. Es
   idempotente: reanudar tras una caída en `PERSISTING` vuelve a diarizar (los
   turnos vivían solo en memoria) y reutiliza los `Speaker`s ya creados.

Cancelación (`POST …/cancel`) y apagado del servidor se atienden entre etapas y
también **dentro** de la diarización (mismo token): cancelar termina en
`CANCELLED` sin transcript; apagar deja el job en `DIARIZING` para reanudarlo.

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
