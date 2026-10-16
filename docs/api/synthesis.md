# Speech synthesis (text to speech)

Common rules (loopback, `Host` check, error shape) are in [README.md](README.md).
Design: [ADR-0010](../adr/0010-voice-engines-and-tts.md). Implementation:
`src/voz/interfaces/api/synthesis.py`.

V renders text with a selected synthesis engine and keeps the result as one WAV
(PCM 16-bit mono, at the model's native sample rate). A job is queued, rendered
chunk by chunk by a background worker that shares the process-wide compute slot
with transcription (only one heavy job runs at a time), and ends `COMPLETED`,
`FAILED` or `CANCELLED`. Synthesis never downloads models. Local processing is
the default; explicitly configured and selected
[OpenAI-compatible servers](providers.md#openai-compatible-servers-v4-04) can
process text remotely, with cloud consent recorded before configuration.
Responses never contain host paths: audio is addressed by job id.

## Endpoints

| Method and path | Request | Response |
| --- | --- | --- |
| `GET /api/synthesis/options` | — | `Options` (below) |
| `POST /api/synthesis` | `{"text","provider_id","model_id","voice_id","language"?: str\|null,"speed"?: float}` | 201 `SynthesisView` + `"reused": false`; 200 with `"reused": true` when an identical request is already done or in progress (see "Reuse"); errors below |
| `GET /api/synthesis/{id}` | — | `SynthesisView` plus the full `text`; 404 `synthesis_job_not_found` |
| `GET /api/synthesis/{id}/events` | — | `text/event-stream` (see "Progress events"); 404 `synthesis_job_not_found` |
| `POST /api/synthesis/{id}/cancel` | — | 202 `SynthesisView` (`CANCELLING` or `CANCELLED`); 404 `synthesis_job_not_found`; 409 `synthesis_job_terminal` |
| `GET /api/synthesis/{id}/audio?download=` | optional `Range` header | `audio/wav` (see "Audio"); 404 `synthesis_job_not_found` / `synthesis_audio_missing`; 409 `synthesis_audio_not_ready`; 416 |
| `GET /api/synthesis?limit=` | — | `{"items": [SynthesisView]}`, newest first; `limit` defaults to 50 and is clamped to 1–200 |
| `DELETE /api/synthesis/{id}` | header `X-VOZ-Action: delete-synthesis` | 204; 403 `synthesis_delete_forbidden`; 404 `synthesis_job_not_found`; 409 `synthesis_job_active` (cancel it first); 500 `synthesis_delete_failed` |

### Options

```json
{
  "providers": [{"provider_id": "sherpa-onnx", "display_name": "...", "locality": "local"}],
  "models": [{
    "provider_id": "sherpa-onnx", "model_id": "...", "display_name": "...",
    "runtime_ready": true, "languages": ["en"],
    "voices": [{"id": "0", "name": "...", "languages": ["en"]}]
  }],
  "max_chars": 20000,
  "speed": {"min": 0.5, "max": 2.0}
}
```

Only available models with the `synthesis` capability of a registered engine
are listed: installed local weights or explicitly configured server models.
`providers[].locality` distinguishes `local` from `cloud`; the UI displays CLOUD
before and during remote generation. A model whose engine cannot read it is
left out (the Model Manager explains why). `max_chars` is the text limit after trimming.

### SynthesisView

```json
{
  "id": "uuid", "state": "RUNNING", "progress": 0.5,
  "chunks_done": 1, "chunks_total": 2, "error_code": null,
  "created_at": "...", "updated_at": "...", "started_at": "...",
  "provider_id": "...", "model_id": "...", "voice_id": "...",
  "language": null, "speed": 1.0,
  "text_length": 32, "text_preview": "first 160 characters",
  "audio": {"duration_ms": 2100, "sample_rate": 22050, "size_bytes": 92652,
            "url": "/api/synthesis/<id>/audio"}
}
```

`state` is one of `QUEUED`, `RUNNING`, `PERSISTING`, `COMPLETED`, `FAILED`,
`CANCELLING`, `CANCELLED`. Progress is counted in text chunks (sentences
packed up to the engine's chunk limit). `audio` is present only when the job is
`COMPLETED`. `error_code` is set only when `FAILED`; it is a stable code from
the engine (`voice_not_found`, `model_not_installed`, `runtime_unavailable`,
`synthesis_failed`, `text_too_long`), the use cases
(`synthesis_provider_not_found`, `synthesis_model_unknown`), storage
(`io_error`, ...) or the runner (`synthesis_internal_error`,
`synthesis_runner_crashed`).

## Creating a job

Errors of `POST /api/synthesis`:

| Status | Code | When |
| --- | --- | --- |
| 404 | `synthesis_provider_not_found` | no engine with that `provider_id` |
| 404 | `synthesis_model_unknown` | the engine has no such synthesis model |
| 404 | `synthesis_voice_not_found` | the model has no such voice |
| 409 | `synthesis_model_not_installed` | the model is known but its files are missing |
| 409 | `synthesis_runtime_unavailable` | the engine cannot run that model now |
| 422 | `synthesis_request_invalid` | blank text, text over `max_chars`, speed out of range, NUL characters |

A body that is not valid JSON, misses a field, or carries a text longer than
twice `max_chars` gets FastAPI's standard 422 validation payload.

### Reuse

The request (engine, model and revision, voice, speed, language, output format
and trimmed text) is hashed. If a `COMPLETED` job with the same hash still has
its audio, it is returned with `"reused": true` and status 200 instead of
rendering again. An identical job that is still queued or running is returned
the same way, so double-clicks do not render twice.

## Progress events

`GET /api/synthesis/{id}/events` sends `event: job` with a `SynthesisView`
(without the full text) every time the stored job changes, `: ping` comments
while nothing changes, and a final `event: end` with `{}` once the job is
terminal. Same framing as `GET /api/jobs/{id}/events` in [jobs.md](jobs.md).

## Audio

`GET /api/synthesis/{id}/audio` streams the WAV with `Accept-Ranges: bytes`.
A single `Range` (`bytes=a-b`, `bytes=a-`, `bytes=-n`) answers 206 with
`Content-Range`; an unsatisfiable one answers 416 with
`Content-Range: bytes */<size>`; malformed or multi-range headers are ignored
and the full file is sent (200). `Content-Disposition` is `inline` (or
`attachment` with `?download=true`) with the file name
`v-<YYYY-MM-DD>-<voice>.wav`, where the date is the job's UTC creation date and
the voice id keeps only ASCII letters, digits, `-` and `_`.

## Deleting

`DELETE /api/synthesis/{id}` removes the WAV first and then the records, so a
failed delete can be retried. Running jobs must be cancelled first (409
`synthesis_job_active`). The custom header is required, like every destructive
action (see [README.md](README.md)).

## Engines

The engine list is composed at startup: the local sherpa-onnx engine
(`provider_id` `sherpa-onnx-tts`) is registered when the `sherpa_onnx` runtime
is importable; otherwise `providers` is empty and `POST` answers
`synthesis_provider_not_found`. `models` are the speech synthesis models
installed from the Model Manager ([models.md](models.md)); both the list and
the engine read the model store on every request, so a model installed or
deleted there appears or disappears without a restart. Tests use a
deterministic fake engine (`src/voz/infrastructure/tts/fake.py`).

## History in the Voice workspace

Voice lists the latest 50 synthesis jobs, newest first, including jobs from
previous sessions. Each entry shows a text preview, voice, duration when audio
is available, creation date and job state. Available model metadata supplies
voice names; the stored voice ID remains visible when its model was removed.
The list also remains available when no synthesis models are installed.

Completed jobs can be played and downloaded as WAV. Deleting a terminal job
requires confirmation and removes its stored result; active jobs must finish
or be cancelled first. Cancelling the confirmation preserves the result. The
list refreshes after the current generation finishes and after deletion. Errors
show a retry action and never expose host paths or raw server messages.

### Keyboard and focus

The Voice workspace supports keyboard operation through its text field,
selectors, sample/generation controls, audio players and history actions. After
cancelling a generation, focus returns to Generate when no other control has
focus; editing in another control is preserved. Cancelling a history deletion
returns focus to its Delete button. A successful deletion moves focus to the
history summary, so keyboard navigation stays within the workspace.
