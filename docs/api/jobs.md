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
| `POST /api/jobs` | `{"project_id","media_asset_id","option_id","language": str\|null}` | 201 `JobView`; 404 `project_not_found` / `media_asset_not_found` / `option_unknown`; 409 `option_not_startable` (+`blocking_reasons`) / `job_already_active` |
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
  "error_code": null, "transcript_id": null,
  "selection": {
    "option_id": "option-v1-…", "provider_id": "faster-whisper",
    "model_id": "turbo", "source": "…", "revision": "sha40",
    "profile": { "...": "ProcessingProfile completo" },
    "execution": { "device": "cuda", "precision": "float16", "fallback_reason": null },
    "language": null
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
