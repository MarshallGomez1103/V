# Projects, media import and jobs — Section 5 (wave of 2026-09-21)

Common rules (loopback, `Host` check, error shape) are in [README.md](README.md).
No endpoint on this page downloads models or calls cloud providers unless the
job explicitly selects one. Errors use `{"detail": {"code": "<snake_code>",
"message": "<safe text>"}}`; host paths and tracebacks are never returned.
Dates are ISO 8601 with a time zone. The exact schema is published at
`/openapi.json`.

## Projects

| Method and path | Request | Response |
| --- | --- | --- |
| `POST /api/projects` | `{"name": str}` (1–200 chars after `strip`) | 201 `{"id","name","created_at"}`; 422 `project_name_invalid` |
| `GET /api/projects` | — | `{"projects": [...]}` ordered by `created_at` descending |

Renaming and deleting projects are documented in [library.md](library.md); the
per-project glossary is in [projects.md](projects.md).

## Media import

`POST /api/projects/{project_id}/media` receives the file as the **raw request
body** (`Content-Type: application/octet-stream`) with the required header
`X-Voz-Filename`: a percent-encoded UTF-8 base name (no path separators, no
control or bidirectional-override characters, at most 255 characters; the server
validates it). Multipart is not used, to avoid an extra dependency. The server
streams the body into a temporary directory under XDG (mode `0700`), runs
`ImportMedia` (immutable copy, SHA-256, ffprobe) and always deletes the
temporary file. Normalization to mono 16 kHz PCM happens inside the job, not
during upload. The default upload limit is 8 GiB.

201 response: `{"media_asset_id","project_id","filename","media_type",
"duration_ms","sha256"}`.

Codes: 400 `filename_invalid` (missing, malformed or unsafe `X-Voz-Filename`),
400 `media_empty` (zero-byte body), 404 `project_not_found`, 413
`media_too_large`, 415 `media_unsupported` (no decodable audio), 422
`media_corrupt`, 503 `media_probe_unavailable` (ffprobe missing, timed out or
returned something unusable), 503 `media_storage_unavailable`, 507
`disk_space_insufficient` (see "Insufficient disk space"), 500
`media_import_failed` (generic, no internal details).

## Transcription jobs

| Method and path | Request | Response |
| --- | --- | --- |
| `POST /api/jobs` | `{"project_id","media_asset_id","option_id","language": str\|null, "diarization"?: {...}, "profile"?: str, "prompt"?: str\|null, "cloud_consent"?: bool}` | 201 `JobView`; 404 `project_not_found` / `media_asset_not_found` / `option_unknown`; 409 `option_not_startable` (+`blocking_reasons`) / `job_already_active` / `insufficient_vram` / `insufficient_ram` (+`required_mib`, `available_mib`; see "Insufficient memory") / `diarization_unavailable` / `diarization_models_missing` (see "Diarization"); 422 `diarization_options_invalid` (see "Diarization") / `quality_profile_unknown` (see "Quality profile and glossary") / `job_prompt_invalid` (see "Style instructions") / `cloud_consent_required` (see "Cloud consent") |
| `GET /api/jobs/{job_id}` | — | `JobView`; 404 `job_not_found` |
| `GET /api/jobs?project_id=` | — | `{"jobs": [JobView]}` of that project, newest first. `project_id` is required (a missing or malformed value gives the standard 422 validation payload) |
| `POST /api/jobs/{job_id}/cancel` | — | 202 `JobView` (CANCELLING/CANCELLED); 404 `job_not_found`; 409 `job_terminal` |
| `GET /api/transcripts/{transcript_id}/segments` | — | `{"segments": [SegmentItem]}` (item shape in [segments.md](segments.md)); 404 `transcript_not_found` |
| `GET /api/jobs/{job_id}/events` | — | `text/event-stream` (see below) |
| `GET /api/jobs/{job_id}/preview?after_ms=` | — | `{"segments": [{"start_ms","end_ms","text"}]}`; 404 `job_not_found` (see "Live preview") |
| `POST /api/transcripts/{transcript_id}/rediarize` | `{"speakers"?: {...}}` | 202 `JobView` (see "Recomputing speakers") |
| `POST /api/shutdown` | header `X-VOZ-Action: shutdown` | 202 `{"status":"stopping"}`; 403 `shutdown_forbidden`; 501 `shutdown_unavailable` (see "Shutting down the server") |
| `GET /api/desktop-shortcut` | — | `{"supported","exists","broken","path"}` (see "Desktop icon") |
| `POST /api/desktop-shortcut` | header `X-VOZ-Action: desktop-shortcut` | 201 `{"supported","exists","broken","path"}`; 403 `desktop_shortcut_forbidden`; 409 `desktop_shortcut_unsupported`; 500 `desktop_shortcut_failed` |
| `DELETE /api/desktop-shortcut` | header `X-VOZ-Action: remove-desktop-shortcut` | 200 `{"supported","exists","broken","path"}`; 403 `desktop_shortcut_forbidden`; 500 `desktop_shortcut_remove_failed` |

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
    "profile": { "name": "…", "device_preference": "…", "gpu_precisions": ["…"], "cpu_precision": "…" },
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

`selection.profile` is the full processing profile (name, device preference,
ordered GPU precisions, CPU precision), the same shape as in
[transcription-options.md](transcription-options.md).

`state` takes the values of `TranscriptionJobState`: `QUEUED, PROBING,
PREPROCESSING, TRANSCRIBING, ALIGNING, DIARIZING, MERGING, PERSISTING,
COMPLETED, FAILED, CANCELLING, CANCELLED`. The UI shows the stage from this
field, never from logs.

### Per-stage progress and timing

Besides `progress` (global, 0..1, monotonic), every `JobView` and every SSE event
carries:

| Field | Meaning |
| --- | --- |
| `started_at` | ISO string or `null`: when the job first left `QUEUED`. |
| `stage_started_at` | ISO string or `null`: when the current state began (reset on every transition and when a stage is redone after a resume). |
| `stage_progress` | 0..1 or `null`: progress **within** the current stage. `PREPROCESSING` = audio normalized by ffmpeg (only if normalization is needed); `TRANSCRIBING` = completed chunks plus the position inside the current chunk; `DIARIZING` = embedding chunks reported by sherpa-onnx. `null` when there is no measure (for example `ALIGNING`, or the first ~20 % of diarization: model loading and segmentation, which report nothing) and in terminal states. |
| `eta_seconds` | Estimated seconds left in **the current stage**, or `null`. It is `elapsed × (1 − sp) / sp` with `elapsed = now − stage_started_at`; `null` if `stage_progress` is `null` or below 0.02, and `0` if it is 1. It is computed when each event is emitted: the client may keep counting down between events. It is overestimated at the start of `DIARIZING` (loading and segmentation time counts as elapsed) and after resuming a job interrupted mid-`TRANSCRIBING`. |

`progress` weights the stages: `PREPROCESSING` 0–0.02, `TRANSCRIBING` 0.02–0.8
(0.02–0.98 if diarization was not requested), `DIARIZING` 0.8–0.98 and the final
persistence up to 1.0. It never sits at 1.0 while the job is working. The runner
writes intermediate progress at most ~2 times per second; state changes and
checkpoints are always written. Migration `0008_job_stage_prompt` (columns
`started_at`, `stage_started_at`, `stage_progress` on `transcription_jobs`;
earlier jobs keep `started_at = created_at`, `stage_started_at = updated_at`
and, if they were in `ALIGNING`/`DIARIZING`/`MERGING`/`PERSISTING`, their
`progress` clamped to 0.8/0.98).

### Text visible before the speakers

When transcription finishes (state `ALIGNING`) the runner already persists the
`Transcript` and its literal `Segment`s. From then on `JobView.transcript_id` is
the transcript id **even while the job is still in `DIARIZING`**, and
`GET /api/transcripts/{id}/segments` returns the full text with
`speaker_id: null`. When diarization finishes, `speaker_id` is assigned to those
same segments (no duplicates; deterministic ids). If diarization fails the
transcript stays as it is (`diarization_error_code`). If the job is cancelled
during diarization the text is **kept** (`CANCELLED` with a non-null
`transcript_id`); shutting the server down leaves the job in `DIARIZING` and on
reopening only diarization is redone. `transcript_id` is `null` in
`QUEUED`…`TRANSCRIBING` and in jobs that failed before transcribing.

### Live preview (`GET /api/jobs/{job_id}/preview`)

During `TRANSCRIBING` it returns the segments already **confirmed in
checkpoints** (a 30-minute chunk is confirmed as a whole), with the same trimmed
text that will be stored and without empty segments:

```json
{"segments": [{"start_ms": 750, "end_ms": 5250, "text": "Hacen parte de esta materia…"}]}
```

`?after_ms=<n>` (integer ≥ 0; any other value → 422) returns only segments with
`end_ms > n`; the client passes the largest `end_ms` it already has. 404
`job_not_found` if the job does not exist. It keeps working afterwards
(checkpoints are retained), but once the transcript exists the source of truth is
`/api/transcripts/{id}/segments`.

### Style instructions (`prompt`)

`POST /api/jobs` accepts `prompt` (optional string). It is stripped; empty is
equivalent to `null`; more than **600 characters** after stripping → 422
`job_prompt_invalid` and nothing is created. It is stored in the snapshot
(`selection.prompt`, column `prompt`, migration 0008) and passed to the engine:

- **Faster Whisper**: as `initial_prompt`. It coexists with the project glossary,
  which is sent as `hotwords`; the effective order is hotwords first (the library
  prepends them to every decoding window) and then the prompt (it only seeds the
  first window).
- **OpenAI** (`whisper-1`, `gpt-4o-transcribe…`): the `prompt` field of its API.
  The `gpt-4o-transcribe-diarize` model does not accept it and it is omitted.
- **ElevenLabs and whisper.cpp**: ignore it.

Whisper **does not follow instructions like a chat model**: the prompt only
conditions the style of the text (punctuation, capitalization, spelling,
vocabulary and proper names), as if it were the text preceding the audio.
"Transcribe in the third person" or "summarize" do not work; an example of what
the text should look like does.

### Cloud consent (`cloud_consent`)

An option whose `cloud` flag is `true` (see `transcription-options.md`) sends the
audio off this machine. `POST /api/jobs` accepts it only with `cloud_consent: true`
(a strict JSON boolean; `"true"`, `1` and the like are rejected with a 422
validation error). Without it, or with `false`, the answer is 422
`cloud_consent_required`: nothing is created, the job is not enqueued and no
request reaches the provider. The check runs after the option is resolved, so an
unknown or non-startable option keeps its own error. Local options (including a
loopback OpenAI-compatible server) ignore the field. The field is not stored in
the job: it authorizes this one request. A client that predates the field keeps
working for local options and fails closed for cloud ones.

### Shutting down the server (`POST /api/shutdown`)

Intended for the web UI's "Close V" button. It requires the header
`X-VOZ-Action: shutdown`; without it (or with another value) → 403
`shutdown_forbidden`. A custom header forces another origin through a CORS
preflight, which V never grants. It answers 202 `{"status":"stopping"}` and about
0.5 s later asks uvicorn to exit (`should_exit`): the same orderly exit as
Ctrl+C. The process ends with code 0 and the job in progress stays recoverable on
reopening. 501 `shutdown_unavailable` if the server was not launched by the `voz`
command (for example `uvicorn voz.bootstrap:app` directly). After the response
the client must assume the API stops answering.

### Desktop icon (`/api/desktop-shortcut`)

Creates a shortcut named **V** on the desktop and in the application menu. Two
modes, chosen when it is created:

- **Source checkout**: runs the `Start-V-*` launcher (`start-v-linux.sh`,
  `Start-V-macOS.command`, `Start-V-Windows.bat`) with the icon from
  `packaging/icons/` (`voz.png`, `voz.ico`).
- **Installed as a tool** (no checkout, Linux only): `Exec=v` (or `Exec=voz` if
  `v` is not on `PATH`) with the icon shipped in the package. The entry uses the
  bare command name, so the desktop session must have it on its `PATH` (for
  `uv tool install`, `~/.local/bin`); otherwise the icon shows as broken. Windows
  and macOS shortcuts are only offered from a checkout.

It uses only the standard library and what each system ships.

`GET` → `{"supported": bool, "exists": bool, "broken": bool, "path": str|null}`.
`supported` is `false` if V runs neither from a folder with launchers nor with
the `v`/`voz` command on `PATH`, or on an unsupported OS. `exists` is `true` if
the shortcut V created is in place **and what it opens still exists** (the
launcher, or the command on `PATH`). `broken` is `true` if the shortcut is in
place but its target is gone (for example the checkout was moved or deleted); a
broken shortcut is `exists: false`, `broken: true`, and `path` is still returned
so it can be recreated or removed. `path` is where it ended up, with the home
directory abbreviated as `~` (never absolute host paths).

`POST` (header `X-VOZ-Action: desktop-shortcut`; 403
`desktop_shortcut_forbidden` without it) creates or recreates the shortcut and
answers 201 with the same body as `GET`. 409 `desktop_shortcut_unsupported`; 500
`desktop_shortcut_failed` (message without paths).

`DELETE` (header `X-VOZ-Action: remove-desktop-shortcut`; 403
`desktop_shortcut_forbidden` without it, and the `POST` header does not work here)
removes every copy and the record, and answers 200 with the same body as `GET`.
It is idempotent and works even when `supported` is `false`. It deletes only files
V made (it recognises them by an `X-V-Shortcut=true` key, by the recorded path or
by the app bundle identifier), never a file of the same name that the user wrote.
500 `desktop_shortcut_remove_failed` (message without paths).

Per platform. Linux: `v.desktop` on the desktop (`xdg-user-dir DESKTOP`) and in
`$XDG_DATA_HOME/applications`, with `gio set … metadata::trusted` if `gio` exists.
Windows: `V.lnk` via PowerShell (honors a desktop moved by OneDrive). macOS: a
minimal `V.app` that opens `Start-V-macOS.command` in Terminal (`.icns` icon via
`sips`, if available). The record of where it was placed and what it opens lives
in `<state>/desktop-shortcut.txt`, never in the code folder.

Shortcuts from before the rename (`voz.desktop`, `VOZ.lnk`, `VOZ.app`, named
`VOZ`) are recognised: creating a new one replaces them (no duplicates) and
`DELETE` removes them too.

At startup the server calls `refresh()` (the composition root, not an endpoint):
if a shortcut V made is broken, or predates this record, it is regenerated for the
current checkout or tool install. It never creates a shortcut that was not there
(a user who removed it keeps it removed), leaves a working shortcut that points at
another checkout alone, and never fails startup.

### Reproducible selection (S5.20)

When the job is created, `option_id` is revalidated against the current
`/api/transcription-options` query; if `can_start` is false the response is 409
with the `blocking_reasons`. The job stores a full snapshot (provider, model,
provenance, revision, profile, execution decision and language) in
`transcription_job_selections`. The `option_id` alone is not a reproducible
checkpoint.

### Quality profile and glossary (S13.01–S13.03)

`profile` (optional, defaults to `"default"`) picks a decoding recipe from
`GET /api/quality-profiles`; an unknown name answers 422
`quality_profile_unknown` and creates nothing. The selection stores the **full**
profile with its effective parameters in `quality_profile` (not just the name),
and in `glossary` the project glossary terms **as of the moment the job is
created** (see [projects.md](projects.md)); editing the glossary later does not
change jobs already created. Jobs that predate this feature return
`quality_profile: null` and `glossary: []` and keep using the engine defaults.
Details, parameters and which engines honor it: [quality-profiles.md](../quality-profiles.md).

### SSE events (S5.06)

`GET /api/jobs/{job_id}/events` emits `event: job` with `data: JobView` on
connect and every time `state`, `progress`, `stage_progress`, `stage_started_at`
or `updated_at` changes (the repository is polled every ~500 ms without blocking
the event loop). It sends `: ping` as a keep-alive every 15 s. On reaching a
terminal state it emits the last `job` and then `event: end` (data `{}`), and
closes. A nonexistent job → 404 `job_not_found` before the stream opens.

### Execution and recovery (S14.01, S14.08)

A single-threaded `JobRunner` processes jobs one at a time: `PREPROCESSING`
normalizes if the derivative is missing, `TRANSCRIBING` runs recoverable
chunked transcription with SQLite checkpoints, `ALIGNING` creates the literal
`Transcript` and `Segment`s (visible immediately) and `DIARIZING` assigns the
speakers. On server start, processable jobs are re-enqueued without repeating
confirmed chunks. `POST …/cancel` marks `CANCELLING` and the runner ends in
`CANCELLED` between recoverable units. Failures are exposed as a stable
`error_code`.

### Insufficient disk space (S14.03)

Before importing an original, `file size + 64 MiB` must be free in the originals
store; before normalizing, `duration_ms * 32` bytes (mono 16 kHz s16 PCM)
`+ 64 MiB` in the derivatives store. If there is not enough, the typed error
`InsufficientDiskSpace` (`code="disk_space_insufficient"`, `retryable=true`) is
translated as follows, leaving no partial artifacts:

| Context | Result |
| --- | --- |
| `POST /api/projects/{project_id}/media` | 507 `{"detail": {"code": "disk_space_insufficient", "message": …}}`; the upload temporary file is removed. 507 is also returned if the disk fills up while the body is being received (`ENOSPC`). |
| `JobRunner` (pending normalization) | job `FAILED` with `error_code = "disk_space_insufficient"`; the job is not retried automatically, the UI can offer a retry after space is freed. |

The check is optional in the use cases (`disk_space=None` skips it) and is wired
in `bootstrap.py` with the `ShutilDiskSpace` adapter.

### Insufficient memory (S14.05, S14.06)

`POST /api/jobs` compares the **measured** free memory (VRAM via `nvidia-smi`;
RAM via `/proc/meminfo`, `MemAvailable`) with the model's estimated requirement
on the device and precision the option already resolved (`execution`). If it is
not enough, the job is not created and the response is 409:

```json
{"detail": {"code": "insufficient_vram", "message": "Not enough free GPU memory to load this model. Choose a smaller model or use the CPU.", "required_mib": 5000, "available_mib": 1200}}
```

`insufficient_ram` is analogous for CPU (message: choose a smaller model or free
memory). The message never includes the GPU name or paths; the suggestion is in
the text itself and the client can compare `required_mib`/`available_mib`.

Approximate requirements (MiB; `application/resource_requirements.py`,
conservative estimate, not measured on V): float16 VRAM tiny 600, base 800, small
1500, medium 3000, turbo 2500, large-v3 5000 (x0.7 for `int8`/`int8_float16`);
CPU int8 RAM tiny 500, base 600, small 1000, medium 2200, turbo 2200, large-v3
3500 (x2 for wider precisions). A model outside the table, or unmeasured memory,
**never blocks**: the estimate is an early warning, not a guarantee.

### Resume idempotency (S14.14)

`recover()` and `enqueue()` do not duplicate a job that is already queued or
running. When persisting, `Transcript` and `Segment`s use deterministic
identities (`uuid5` of the job), so resuming after an interruption in
`ALIGNING`/`DIARIZING`/`PERSISTING` adds only the missing segments: the result is
identical to a clean run and repeating the stage duplicates nothing.

## Diarization (S6.13, S6.15, S14.07)

Diarization (who is speaking) is an **optional** job stage, off by default and
always local (sherpa-onnx, ADR-0007). It is requested when the job is created:

```json
{"project_id": "…", "media_asset_id": "…", "option_id": "…",
 "diarization": {"enabled": true, "speakers": {"exact": 2}}}
```

| Field | Rule |
| --- | --- |
| `diarization` | optional; absent or `null` = disabled |
| `enabled` | boolean; defaults to `false` if missing. With `false`, `speakers` is ignored (although its shape is validated) |
| `speakers` | optional object with `exact`, `minimum`, `maximum` (integers from 1 to 32; `null` is equivalent to absent). `exact` excludes the other two and `minimum <= maximum`. Without hints, the engine estimates the number of speakers |

Errors:

- 422 `diarization_options_invalid`: invalid shape or values (unknown field,
  non-boolean/non-integer, outside 1–32, `exact` together with
  `minimum`/`maximum`, `minimum > maximum`). Evaluated before touching the
  project or the option.
- 409 `diarization_models_missing`: diarization was requested and the speaker
  models are **not installed** (fixed by downloading them). Nothing is created.
  To know before creating the job whether they are installed, query
  `GET /api/models` and look at the `diarization:sherpa-default` entry
  (`kind: "diarization"`, `installed`, `runtime_available`); they are downloaded
  with `POST /api/models/diarization:sherpa-default/install`
  `{"method":"download","confirm":true}` (see [models.md](models.md)).
- 409 `diarization_unavailable`: diarization was requested but the runtime is
  missing (the `diarization` extra; downloading models does not fix it) or is not
  wired. Evaluated before `diarization_models_missing`. The job is not created;
  requesting it disabled always works. Availability is decided by the
  `DiarizationAvailability` port (`runtime_available`, `models_installed`), wired
  in `bootstrap.py`.

The request is stored in the job snapshot (`transcription_job_selections`,
column `diarization_json`, migration `0005_job_diarization`) and returned in
`JobView.selection.diarization` as `{"enabled": bool, "speakers": {"exact",
"minimum", "maximum"}}` (`null` for what was not requested). Rows that predate
the migration keep diarization disabled.

### Pipeline stage

With diarization on, after `TRANSCRIBING` (and `ALIGNING`) the runner:

1. enters `DIARIZING` with the transcript already persisted (see "Text visible
   before the speakers"), **releases the ASR engine** through the injected
   callback `release_asr(selection)` (S6.15/S14.07: ASR and diarization models
   never coexist in memory) and runs the `DiarizationProvider` on the same
   normalized derivative the ASR used, reporting `stage_progress`;
2. without leaving `DIARIZING`, `AssignSpeakers` stores `Speaker`s and
   `SpeakerTurn`s and assigns `speaker_id` to the existing segments. It is
   idempotent: resuming after a crash in `DIARIZING` diarizes again (turns lived
   only in memory) and reuses the `Speaker`s already created.

Cancellation (`POST …/cancel`) and server shutdown are honored between stages and
also **inside** diarization (same token): cancelling ends in `CANCELLED` keeping
the text; shutting down leaves the job in `DIARIZING` to be resumed.

Speed: sherpa-onnx runs on CPU with `min(8, cores − 1)` threads (previously 2).
Measured with 11 minutes of synthetic audio on a 20-thread CPU (with other load
active): 2 threads 147 s, 4 threads 85 s, 8 threads 70 s, 19 threads 79 s. CUDA
is not used (no GPU wheel of sherpa-onnx is installed).

### Diarization failure: the ASR is never lost

If diarization fails (missing model, missing runtime, provider or assignment
failure), the transcript **is persisted anyway** and the job ends `COMPLETED`
with `error_code = null`. The failure is exposed in
`JobView.diarization_error_code`, a stable code
(`diarization_model_unavailable`, `diarization_runtime_unavailable`,
`diarization_invalid_audio`, `diarization_provider_failed`; never messages or
paths). The code is persisted in
`transcription_job_selections.diarization_error_code` (same migration) and is
not retried automatically: a job with the code stored does not diarize again
when resumed. The selections table was chosen over `transcription_jobs` so as
not to widen the `TranscriptionJob` domain entity, whose `error_code` is only
valid for `FAILED` jobs.

### Clustering threshold and residual speakers (plan v3, CP-A3)

By default the engine estimates the number of speakers with a distance threshold
(`DEFAULT_THRESHOLD` in `infrastructure/diarization/sherpa.py`). Measured with
a real recording of a 1 h 47 min class (a teacher and a few students), on a copy
of the database and media in a temporary XDG:

| Threshold | Raw clusters | After merging residuals | Speech split after merging |
| --- | --- | --- | --- |
| 0.3 | 11 | 5 | 35.7 / 32.9 / 21.0 / 6.7 / 3.6 % |
| **0.4** (default) | 6 | **3** | 69.0 / 27.5 / 3.5 % |
| 0.45 | 5 | 2 | 68.9 / 31.1 % |
| 0.5 | 3 | 2 | 68.5 / 31.5 % |
| 0.6 | 2 | 2 | 68.5 / 31.5 % |
| 0.7 | 1 | 1 | 100 % |

At 0.3 the teacher appears split into two clusters (35.7 % + 32.9 % ≈ the 69 %
that a single cluster holds from 0.4 on). 0.4 keeps the teacher whole plus a
third voice; merging two speakers in the UI is easy, splitting one is not. The
default used to be 0.3.

**Residual speakers.** The provider merges every cluster with very little speech
(under 2 % of total speech, or under 10 s with a 5 % cap so that a short audio
does not lose both of its speakers) into the largest cluster closest **in time**
(`application/diarization_cleanup.py`; marked `ponytail:` because the engine does
not expose embeddings). It never goes below the requested `exact`/`minimum`. On
the real recording: 11 raw clusters at 0.3 become 5.

**The engine runs in a child process** (`infrastructure/diarization/worker.py`).
The native sherpa-onnx call holds the GIL for the whole segmentation step (about
4 min for 1 h 47 min), which froze the entire server: SSE, progress and the
Cancel button. Measured on a 4-minute clip: maximum gap of a heartbeat thread 8.3
s before, 0.1 s now. Cancelling kills the child in under 0.2 s even in the silent
phase. Cost: the models are reloaded on each pass (~1 s).

## Recomputing speakers (`POST /api/transcripts/{transcript_id}/rediarize`)

Recomputes **only** the speakers of a finished transcript, without
re-transcribing (the ASR is not called and texts, timings, edits and revisions
are not touched).

```json
{"speakers": {"exact": 2}}
```

`speakers` accepts `exact`, `minimum`, `maximum` with the diarization rules
(1–32, `exact` excludes the others, `minimum <= maximum`); `{}` or no `speakers`
= the engine estimates. → **202** with the job view (`JobView`, like
`POST /api/jobs`): it is **the same job as the transcription**, reopened in
`DIARIZING` (`progress` 0.8, `stage_progress` `null` at the start, `transcript_id`
unchanged). Follow it with `GET /api/jobs/{id}` or the SSE stream
`/api/jobs/{id}/events` (which must be reopened after the 202): `stage_progress`
and `eta_seconds` work as in any job, and when it finishes it returns to
`COMPLETED`.

| Status | Code | Meaning |
| --- | --- | --- |
| 404 | `transcript_not_found` | the transcript does not exist |
| 409 | `rediarize_unavailable` | no job produced it |
| 409 | `job_already_active` | another job is unfinished (there is a single worker) |
| 409 | `diarization_unavailable` | the diarization runtime is missing |
| 409 | `diarization_models_missing` | the speaker models are missing (download them in the model manager) |
| 422 | `diarization_options_invalid` | invalid body |

Semantics:

- The new hints are stored in the job selection
  (`transcription_job_selections.diarization_json`, and `diarization_error_code`
  is cleared); the previous `COMPLETED`/`FAILED`/`CANCELLED` state is lost (the
  entity offers `reopen_for_diarization`). No migration.
- **Names and colors are kept by overlap**: each new cluster takes the old
  speaker that talks in the same stretches, if that overlap covers at least 50 %
  of the cluster's speech or 50 % of the old speaker's speech (a person the
  previous computation had split and who now comes back whole keeps their name).
  An old speaker goes to a single cluster, the one with the largest overlap first
  (`application/speaker_matching.py`); a cluster that mixes several old people
  takes the name of the one that overlaps most, as when merging by hand. The
  rest receive "Speaker N" and a free color from the palette. Old speakers that
  nothing references any more are deleted.
- Manual segment-to-speaker assignments (`PUT /api/segments/{id}/speaker`) **are
  replaced** by those of the new computation.
- If the recomputation fails (models, audio, provider) the job ends `COMPLETED`
  with `diarization_error_code` and the previous speakers intact (same rule as
  the first computation). If the audio derivative no longer exists it is
  regenerated.
- Cancelling (`POST /api/jobs/{id}/cancel`) leaves it `CANCELLED` with the text
  and the previous speakers intact; it can be recomputed again (any terminal job
  with a transcript works). If the server shuts down midway, the job stays in
  `DIARIZING` and resumes on start.
- `GET /api/library` shows the job as `DIARIZING` while it lasts.
