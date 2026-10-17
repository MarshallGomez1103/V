# Model manager — query and delete (S8.02, S8.03, S8.07, S8.08)

Section 8 of the roadmap. The canonical catalog (`faster_whisper_catalog()`,
S8.01) defines six Faster Whisper models with pinned source and revision. This
contract queries and deletes; downloading runs as a background task (final
section). No response contains host paths. Common rules: [README.md](README.md).

## Namespaced keys (MODELS-UI-002)

The manager gathers into a single catalog (`ManagedModelCatalog`) the
faster-whisper models, the whisper.cpp models (only if `whisper-cli` exists),
speaker separation (sherpa-onnx) and the speech synthesis models (sherpa-onnx
TTS; listed once the composition root enables the engine). A bare `model_id` can repeat across providers
(`small` exists in faster-whisper and in whisper.cpp), so the API addresses every
model by its **key** `"<provider_id>:<model_id>"`:

| Key | Family |
| --- | --- |
| `faster-whisper:turbo` | faster-whisper ASR |
| `whisper-cpp:small` | whisper.cpp ASR (requires `whisper-cli`) |
| `diarization:sherpa-default` | Speaker segmentation + embeddings |
| `sherpa-onnx-tts:piper-es_MX-ald-medium` | Speech synthesis (Piper voice, Spanish, Mexico) |

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
      "capabilities": ["cpu", "gpu", "language_detection", "transcription", "translation", "word_timestamps"],
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
| `kind` | Free-form family string (`asr`, `diarization`, `tts` today). Clients must not reject unknown values; group by `capabilities` instead. |
| `requires` | Runtime the model needs in order to be used: `whisper-cli` (whisper.cpp), `diarization` (optional extra with sherpa-onnx), `tts` (the sherpa-onnx runtime for speech synthesis) or `null`. |
| `runtime_available` | `false` if that runtime is missing: the model is listed but the UI does not offer to install it ("requires the diarization extra"). whisper.cpp is not even listed without `whisper-cli`. |
| `model_id` | Identifier within the provider; for faster-whisper, the same as in `/api/transcription-options`. |
| `source`, `revision` | Pinned provenance: repository commit SHA or, for custom folder/URL imports, a content-derived revision. Catalog release assets use SHA-256 and may have null source/revision. |
| `capabilities` | Sorted list of capability strings the model declares (vocabulary below). Always present; never empty. |
| `profile` | `fast` or `quality`; `null` for diarization and speech synthesis. |
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

### Grouping and license in the UI (V6-03)

`license`, `source`, `revision` and `capabilities` are the whole contract the
Model Manager needs; V6-03 added no fields. The web client derives the section of
each model from its **primary capability**, in this order: `transcription` ->
Transcription; `diarization` (or `kind: "diarization"`) -> Speakers; `synthesis`
-> Speech synthesis. A model without recognizable capabilities (a response from
before V6-01) falls into Transcription. A section with no models is not shown.
The license, a short `source@revision` (first 7 characters of the SHA) and the
readable capabilities are shown in the download confirmation dialog, before
anything is installed. `source` and `revision` are `null` for release-asset
models (diarization); the dialog then says the files are verified with SHA-256.

### Capability vocabulary

Values are stable (persisted and serialized): new ones are only added.

| Value | Meaning | Declared today by |
| --- | --- | --- |
| `transcription` | Speech to text | faster-whisper, whisper.cpp |
| `translation` | Translate to English while transcribing | faster-whisper |
| `language_detection` | Detects the spoken language | faster-whisper, whisper.cpp |
| `word_timestamps` | Native per-word timings in the transcript (ADR-0008) | faster-whisper, whisper.cpp |
| `diarization` | Speaker separation | `diarization:sherpa-default` |
| `cpu`, `gpu` | Hardware the engine can run on | ASR models; `cpu` also diarization and speech synthesis |
| `synthesis` | Text to speech | the `sherpa-onnx-tts:*` models |
| `alignment` | Forced alignment by a standalone aligner | none (words are native) |
| `wake_word` | Wake-word detection | none yet |
| `realtime` | Streaming recognition | none yet |

`synthesis` is implemented by the sherpa-onnx TTS engine. `alignment` and
`wake_word` exist in the vocabulary (ADR-0010 section 8) but no engine implements
them, so no catalog entry can declare them:
`ENGINE_CAPABILITIES` in `src/voz/infrastructure/model_registry.py` maps every
provider to the capabilities its engine implements, and a test fails if an entry
declares anything outside that map. `alignment` is deliberately not declared by
the ASR models: their word timings come from the engine itself, not from an
`AlignmentProvider`.

Capabilities are not read from `.voz-model.json` manifests: they always come
from the trusted catalog, so manifests written before V6-01 (which have no
`capabilities` key) and manifests with arbitrary values keep working.

### Speech synthesis models (V4-03)

Catalog: `src/voz/infrastructure/tts/catalog.py`. Every model is one
`.tar.bz2` of the `tts-models` release of `k2-fsa/sherpa-onnx`, pinned by size
and SHA-256 (`size_bytes` is the archive size). They install through the same
`POST /api/models/{key}/install` task as any other model; `done_bytes` /
`total_bytes` count the archive download.

| Key (`sherpa-onnx-tts:<model_id>`) | Family | Languages | Archive |
| --- | --- | --- | --- |
| `piper-es_MX-ald-medium` | Piper (VITS) | es | 67 196 497 B |
| `piper-es_ES-davefx-medium` | Piper (VITS) | es | 67 184 952 B |
| `piper-en_US-lessac-medium` | Piper (VITS) | en | 67 230 653 B |
| `kitten-nano-en-v0_8-int8` | KittenTTS | en | 31 220 690 B |
| `kokoro-int8-multi-lang-v1_0` | Kokoro (quality, slow) | en, es, fr, hi, it, ja, pt, zh | 132 303 094 B |

All of them declare `capabilities: ["cpu", "synthesis"]`, `kind: "tts"`,
`requires: "tts"` and `multilingual` true only for Kokoro. The `license` string
is honest about the chain of rights (see
[../licenses/models.md](../licenses/models.md)): the Piper voices follow the
Lessac dataset's research-only license, and every archive carries the GPL-3.0
`espeak-ng-data` phoneme data.

Install rules: the archive is verified against its pinned size and SHA-256
**before** anything is extracted (failure: `model_installation_checksum_mismatch`,
nothing written). Extraction is manual: only the files the catalog names, the
`espeak-ng-data` tree and the `LICENSE`/`MODEL_CARD` notices are written, as
regular files, under `<data>/models/tts/<model_id>/`. An archive with an
absolute or `..` member path, or a link or device entry among the files to
extract, or a missing expected file, is rejected as
`model_installation_invalid_snapshot` and nothing is published. Nothing inside an
archive is executed. An interrupted download resumes from its `.part` file.
`installed` is true when the install manifest matches the pinned digest and the
model files have the recorded sizes; `DELETE` removes the whole model directory
(and any partial download) and returns the freed bytes. Deleting a speech
synthesis model while a synthesis job with it is queued, running or persisting
answers 409 `model_in_use`.

## `DELETE /api/models/{key}?confirm=<key>`

Deletes the catalog's pinned installation. `confirm` must repeat the exact id
(case-sensitive); it is a protection against accidental deletion, not
authentication.

| HTTP | `detail.code` | When |
| --- | --- | --- |
| 200 | (body) | `{ "key": "faster-whisper:tiny", "model_id": "tiny", "freed_bytes": 77010000 }` |
| 400 | `model_delete_unconfirmed` | `confirm` is missing or does not match the id in the path. Evaluated first, without touching the disk. |
| 404 | `model_not_installed` | The id is not in the catalog or is not installed. |
| 409 | `model_in_use` | A non-terminal job (queued, in progress or cancelling) has a selection with that model and revision, or, for a diarization model, asked for speakers; for a speech synthesis model, a synthesis job with it is queued, running or persisting. Finish or cancel the job and retry. |
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
No response contains local host paths. Custom imports may expose their accepted public source URL as provenance.

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

## Custom model imports

The dialog starts with a download link or Hugging Face repository. Paste a source,
choose **Check link**, review its suggested format, size and license, then confirm
the download to this computer. **Manual configuration** retains explicit engine,
family, relative file roles and browser-selected folders.

### Link-only preview

The same preview endpoint accepts a remote source without engine, family or
name; omitted values default to `auto`, an empty family and a derived safe name:

```json
{"source_type": "huggingface", "source": "organization/model"}
```

A full `https://huggingface.co/organization/model` URL is also accepted. For a
direct file link, use `source_type: "url"`. The server reads bounded repository
metadata or sends a HEAD request; it does not download weights at this stage.
The response keeps the usual preview contract and contains a concrete engine
and family when detection succeeds.

Automatic detection recognizes complete CTranslate2 Whisper layouts, one Whisper
GGML file, or an unambiguous Whisper ONNX encoder/decoder/tokens set. TTS detection
requires both an identifiable supported family and the expected files. Direct
`.tar.bz2` archive names can suggest Whisper ONNX, Kitten, Kokoro or VITS/Piper;
that name is only a hint, not proof of the archive's contents. Generic archives
and ambiguous repositories require manual configuration. Matcha's acoustic and
vocoder roles remain manual. The chosen engine must already be available.

`custom_model_detection_ambiguous` and `custom_model_engine_unsupported` return
HTTP 422 with safe feedback. Detection never adds a new model architecture or
runtime. In particular, arbitrary Safetensors, GGUF or ONNX files are not
necessarily compatible. License metadata is not inferred from filenames or
repository names; an absent declaration remains unknown.

Only explicit installation downloads the selected files, checks their digests
and validates loading in the isolated process before publishing the model. See
[model selection and compatibility](../research/voice-models.md) for available
families and possible future engines.

### Explicit metadata and installation

`POST /api/models/custom/preview` inspects an explicitly supplied source and
returns a preview ID, engine/model descriptor, family, declared license, file
count and total byte size. It does not install or load the model. Local sources
are read without modifying the originals; remote previews query metadata only.

```json
{
  "source_type": "folder",
  "source": "../voice-models/my-local-model",
  "engine": "faster-whisper",
  "family": "ctranslate2",
  "display_name": "My local model",
  "license": "unknown"
}
```

Supported engines and families are `faster-whisper` / `ctranslate2`,
`whisper-cpp` / `ggml`, and `sherpa-onnx-tts` / `kitten`, `kokoro`, `vits` or
`matcha`, plus experimental `sherpa-onnx-asr` / `whisper` (encoder, decoder and
tokens roles). See [Whisper ONNX limits](../sherpa-onnx-asr.md). The engine must
already be installed. `source_type` also accepts
`huggingface` for a public repository ID and `url` for a standalone GGML file
or a sherpa `.tar.bz2` package. Multi-file models can be supplied as a folder or
Hugging Face repository. The optional `revision` defaults to `main` for
repository discovery, then resolves to an immutable commit before import.
Optional `file_roles` maps known family roles to relative files when automatic
layout discovery is insufficient.

Confirm the displayed preview through
`POST /api/models/custom/install` with
`{"preview_id": "<preview-id>", "confirm": true}`. The response is `202` with
an ordinary model task. Poll `/api/model-tasks/{id}` for byte progress and
completion; `/api/model-tasks/{id}/cancel` cancels a pending or running import.
Previews are process-local and bounded to 100 pending choices; after expiry or
restart, prepare the source again. Confirmation must be a JSON boolean.

Import copies or downloads allowlisted weights and configuration into owned
staging, calculates per-file SHA-256 values, and validates loading with the
installed engine in a separate process. The validation waits for V's shared
compute slot and releases a resident ASR model first. Cancellation while waiting
never starts the loader. No model scripts, pickle objects or remote Python code
are executed. Child stdout/stderr and loader exceptions are not exposed.

Only successful validation publishes the model. Source folders remain intact,
and failure or cancellation discards the owned staging tree. Each imported file
has a recorded SHA-256 digest. Repository models retain their resolved commit;
other imports derive a pinned revision from the content digest. Unpinned local
previews have null source/revision until import completes. Local host paths are
not returned as provenance. User-supplied license declarations are distinguished
from verified catalog licenses; an absent declaration remains `unknown`.

Imports are limited to 10,000 files and 16 GiB of source bytes. TTS archive
extraction is additionally bounded to 1 GiB. Unsafe archive paths, links,
devices, duplicate extracted entries and unsupported layouts are rejected. URL credentials,
query strings and fragments are not accepted. Available disk space is checked
before copying or downloading. These safeguards do not make native model
parsers a sandbox; import only weights from sources you trust.

After publication, custom models appear live in `GET /api/models` and the
corresponding transcription/synthesis options. They use `custom-` model IDs,
retain their engine's capability declarations, survive restart and use the same
confirmed deletion and active-job protection as catalog models. Deleting an
imported model does not delete its source files or existing synthesized audio.

Errors use stable, path-free codes, including `custom_model_invalid`,
`custom_model_engine_unsupported`, `custom_model_detection_ambiguous`,
`custom_model_runtime_unavailable`,
`custom_model_metadata_unavailable`, `custom_model_preview_expired`,
`custom_model_validation_failed` and `custom_model_validation_timeout`.
Unconfirmed installation uses `model_install_unconfirmed`; cancellation uses
`model_installation_cancelled`. Validation errors never echo request values.

### Browser-selected folders

The custom-model dialog uses the browser's directory picker and sends a copy of
compatible weights/configuration, retaining the original files. It never asks
for or returns a server filesystem path. Unsupported files are excluded before
upload and remain untouched in the source folder.

`POST /api/models/custom/uploads` accepts engine, family, display name, optional
license/file roles and `files: [{"name": "model.bin", "size_bytes": 123}]`.
Names are relative to the selected folder; its outer name is not transmitted.
The `201` receipt contains an opaque `id`, `total_bytes` and `file_count`.

Send each file as raw bytes to
`PUT /api/models/custom/uploads/{id}/files/{index}` in manifest order. A complete
file returns `204`; actual size must match the declared size. Browser upload
progress is distinct from the later installation/validation task.
`POST /api/models/custom/uploads/{id}/preview` requires all files to be complete
and returns the ordinary custom-model preview. Explicit installation then uses
`POST /api/models/custom/install`, as above.

`DELETE /api/models/custom/uploads/{id}` returns `204` and is idempotent.
Cancellation or failed writes discard incomplete uploads. Cleanup is deferred
while a preview or independent staging copy holds the source. Once staged,
validation uses its own copy, so removing the upload cannot interrupt loading.

Uploads use private XDG cache directories and files (0700/0600 on POSIX).
Pending uploads are process-local, bounded to 100 receipts and 16 GiB of total
reserved source bytes, and expire after 20 minutes of inactivity. Expired entries
are cleaned on subsequent upload operations; normal shutdown discards owned
entries. An abrupt process termination can leave private cache files, which this
version does not remove across instances. A queued import whose source expires
before staging must be prepared again.

Unsafe or duplicate relative names, links, file/directory collisions, unsupported
files and inconsistent sizes are rejected without echoing supplied values.
Errors include `custom_model_upload_expired`, `custom_model_upload_incomplete`
and `custom_model_upload_limit`; disk admission uses `disk_space_insufficient`.

`GET /api/models` also returns `custom_engines`, a list of installed runtime
identifiers available for custom imports even before their first model exists.
Older clients can ignore this field; older servers may omit it.
