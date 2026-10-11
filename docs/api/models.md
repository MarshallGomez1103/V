# Model manager — query and delete (S8.02, S8.03, S8.07, S8.08)

Section 8 of the roadmap. The canonical catalog (`faster_whisper_catalog()`,
S8.01) defines six Faster Whisper models with pinned source and revision. This
contract queries and deletes; downloading runs as a background task (final
section). No response contains host paths. Common rules: [README.md](README.md).

## Namespaced keys (MODELS-UI-002)

The manager gathers into a single catalog (`ManagedModelCatalog`) the
faster-whisper models, the whisper.cpp models (only if `whisper-cli` exists) and
speaker separation (sherpa-onnx). A bare `model_id` can repeat across providers
(`small` exists in faster-whisper and in whisper.cpp), so the API addresses every
model by its **key** `"<provider_id>:<model_id>"`:

| Key | Family |
| --- | --- |
| `faster-whisper:turbo` | faster-whisper ASR |
| `whisper-cpp:small` | whisper.cpp ASR (requires `whisper-cli`) |
| `diarization:sherpa-default` | Speaker segmentation + embeddings |

All the endpoints on this page (`DELETE /api/models/{key}`,
`POST /api/models/{key}/install`) accept the key in the path (`:` is valid; the
client encodes it with `encodeURIComponent`). For compatibility, an id **without**
`:` is interpreted as faster-whisper. On `DELETE`, `confirm` must repeat exactly
what was sent in the path.

## `GET /api/models`

HTTP 200. One entry for every catalog model, installed or not.

```json
{
  "models": [
    {
      "key": "faster-whisper:tiny",
      "provider_id": "faster-whisper",
      "kind": "asr",
      "requires": null,
      "runtime_available": true,
      "model_id": "tiny",
      "display_name": "Faster Whisper Tiny (fast)",
      "source": "Systran/faster-whisper-tiny",
      "revision": "d90ca5fe260221311c53c58e660288d3deb8d356",
      "license": "MIT",
      "multilingual": true,
      "profile": "fast",
      "size_bytes": 77003619,
      "installed": true,
      "disk_bytes": 77010000,
      "reclaimable_bytes": 10000,
      "shared_bytes": 77000000,
      "external": [{ "origin": "buzz" }]
    }
  ],
  "disk": {
    "models_bytes": 77010000,
    "free_bytes": 120000000000,
    "reclaimable_bytes": 10000
  }
}
```

| Field | Meaning |
| --- | --- |
| `key`, `provider_id` | The API key (see above) and the provider. |
| `kind` | `asr` or `diarization`. The UI groups "Speakers" separately. |
| `requires` | Runtime the model needs in order to be used: `whisper-cli` (whisper.cpp), `diarization` (optional extra with sherpa-onnx) or `null`. |
| `runtime_available` | `false` if that runtime is missing: the model is listed but the UI does not offer to install it ("requires the diarization extra"). whisper.cpp is not even listed without `whisper-cli`. |
| `model_id` | Identifier within the provider; for faster-whisper, the same as in `/api/transcription-options`. |
| `source`, `revision` | Pinned provenance (40-character commit SHA). `null` for diarization: its artifacts are release assets verified by SHA-256. |
| `profile` | `fast` or `quality`; `null` for diarization. |
| `size_bytes` | Sum of the catalog's expected files (what would be downloaded). |
| `installed` | `true` if there is a valid V manifest for exactly that source and revision. A different revision installed earlier does not count. |
| `disk_bytes` | **Real size** of the installed model's files (sum of `lstat`), also if they are hardlinks to the Buzz cache; `null` if not installed. Never 0 for an installed model. |
| `reclaimable_bytes` | What deleting the model would really free: it excludes files that have another hard link (the copy imported from Buzz). `null` if not installed. This is the value that matches `freed_bytes` of the `DELETE`. |
| `shared_bytes` | `disk_bytes − reclaimable_bytes`: what stays on disk because another tool (Buzz) holds the same file. `null` if not installed. |
| `external` | Origins from other tools that hold exactly that source and revision and could be imported (`buzz`). Empty without an external source. No duplicates, no paths. |
| `disk.models_bytes` | Sum of `disk_bytes` of the installed models. |
| `disk.reclaimable_bytes` | Sum of `reclaimable_bytes` of the installed models. |
| `disk.free_bytes` | Free bytes of the data volume; `null` if it cannot be queried. |

### Models imported from Buzz: "0 bytes"

A model imported as a local copy is linked with *hardlinks* to the Buzz cache: it
does not take a second amount of disk space. `disk_bytes` reports its real size
(`lstat`), and `DELETE` returns `freed_bytes` ≈ 0 (only the manifest) because the
weights remain in the Buzz cache. A UI that wants to say "X will be freed" must
use `reclaimable_bytes`, and can show `shared_bytes` as "shared with Buzz";
showing `freed_bytes` or `reclaimable_bytes` as the "size" gives 0.

### Before asking for speakers

The speaker models are the `diarization:sherpa-default` entry
(`kind: "diarization"`). To know whether a job with diarization can be created:
`installed` (models) and `runtime_available` (the `diarization` extra). If
`installed` is false, offer the download
(`POST /api/models/diarization:sherpa-default/install`); otherwise
`POST /api/jobs` answers 409 `diarization_models_missing`.

## `DELETE /api/models/{key}?confirm=<key>`

Deletes the catalog's pinned installation. `confirm` must repeat the exact id
(case-sensitive); it is a protection against accidental deletion, not
authentication.

| HTTP | `detail.code` | When |
| --- | --- | --- |
| 200 | (body) | `{ "key": "faster-whisper:tiny", "model_id": "tiny", "freed_bytes": 77010000 }` |
| 400 | `model_delete_unconfirmed` | `confirm` is missing or does not match the id in the path. Evaluated first, without touching the disk. |
| 404 | `model_not_installed` | The id is not in the catalog or is not installed. |
| 409 | `model_in_use` | A non-terminal job (queued, in progress or cancelling) has a selection with that model and revision, or, for a diarization model, asked for speakers. Finish or cancel the job and retry. |
| 500 | `model_remove_failed` | I/O error while deleting; message without paths. |

Errors have the shape `{"detail": {"code", "message"}}`. Completed, failed or
cancelled jobs do not block deletion; they keep their selection snapshot and
their transcript, but cannot be rerun with the model until it is reinstalled.

Known limit: a job created between the in-use check and the deletion is not
protected (a very short window, local single-user app).

## Background installation (MODELS-TASKS-001)

Downloading (1–3 GB from Hugging Face) or importing (from the Buzz cache) does not
fit in one request: the POST enqueues a task and the client polls its state. Tasks
live **only in memory** (`ModelTaskRunner`, one worker thread and a FIFO queue:
one heavy task at a time). They are deliberately not durable: if the app closes
midway, the download resumes by itself from the `.part` files when the user clicks
install again. When the server shuts down, queued or running tasks are cancelled.
No response contains paths or URLs.

### `POST /api/models/{key}/install`

```json
{ "method": "download", "confirm": true }
{ "method": "import", "origin": "buzz", "confirm": true }
```

`method` is `download` or `import` (any other value: 422 validation); `origin`
only applies to `import` (for now `buzz`, the default). `confirm` must be `true`:
downloading is always explicit.

| HTTP | `detail.code` | When |
| --- | --- | --- |
| 202 | (`TaskView` body) | Task enqueued. If there is already an active task (`queued`/`running`) for that model, that same one is returned without creating another. |
| 400 | `model_install_unconfirmed` | `confirm` is absent or not `true`. Evaluated first; nothing is enqueued. |
| 404 | `model_unknown` | The id is not in the catalog. |
| 404 | `external_model_not_found` | `method=import` and there is no compatible copy at the origin. |
| 409 | `model_already_installed` | There is already a valid installation of that source and revision. |

### `GET /api/model-tasks`

`{ "tasks": [TaskView, ...] }`: the active ones and the last 20 finished, from
oldest to newest.

### `GET /api/model-tasks/{task_id}`

`TaskView`, or 404 `model_task_not_found` (unknown id or already dropped from the
history).

### `POST /api/model-tasks/{task_id}/cancel`

202 with the `TaskView`. A queued task becomes `cancelled` immediately; a running
one stays `running` until the store honors the cancellation (between 1 MiB blocks)
and then becomes `cancelled`, keeping the `.part` files. Repeating the cancel on a
running task is idempotent. 409 `model_task_terminal` if it already finished; 404
`model_task_not_found` if it does not exist.

### `TaskView`

```json
{
  "id": "5f0c...e1",
  "key": "faster-whisper:large-v3",
  "model_id": "large-v3",
  "method": "download",
  "origin": null,
  "state": "running",
  "done_bytes": 1073741824,
  "total_bytes": 3087284237,
  "error_code": null,
  "created_at": "2026-09-30T10:00:00Z",
  "updated_at": "2026-09-30T10:00:12Z"
}
```

| Field | Meaning |
| --- | --- |
| `key` | The model's key (`provider:model`). |
| `state` | `queued`, `running`, `completed`, `failed` or `cancelled`. |
| `done_bytes`, `total_bytes` | Accumulated progress across all files. While queued they are 0 and the catalog sum; on completion, `done == total`. |
| `origin` | `buzz` for `import`; `null` for `download`. |
| `error_code` | Only with `failed`; `null` otherwise. Stable codes: those of `ModelInstallationFailureCode` (`model_installation_network_error`, `model_installation_http_error`, `model_installation_checksum_mismatch`, `disk_space_insufficient`, `model_installation_io_error`, `model_installation_invalid_snapshot`, ...), `external_model_not_found` if the copy disappeared before importing, and `model_task_failed` for any unexpected error (the detail goes to the log, never to the response). |

Typical client flow: `POST install` -> poll `GET /api/model-tasks/{id}` while
`state` is `queued`/`running` -> when it finishes, refresh `GET /api/models`
(`installed: true`).

### Speaker separation (`diarization:sherpa-default`)

It is installed and deleted like any other model: `POST install` with
`method=download` enqueues a task that downloads the two pinned artifacts
(pyannote 3.0 segmentation, 6 958 444 bytes, MIT; WeSpeaker embeddings,
26 530 550 bytes, Apache-2.0), with aggregated progress, cancellation and resume
from `.part`. `DELETE` with `confirm=diarization:sherpa-default` removes them. It
does not support `method=import`. The runtime (`sherpa-onnx`, the `diarization`
extra) is independent: without it, `runtime_available` is `false` and the UI does
not offer to install.

Deleting a diarization model also answers 409 `model_in_use` while a
non-terminal job asked for speakers and has not already failed in diarization
(V0-09b). After a successful deletion the cached diarization engines are closed.
