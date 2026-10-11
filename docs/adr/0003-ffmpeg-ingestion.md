# ADR-0003: FFmpeg ingestion over immutable originals

> Translated from Spanish on 2026-10-11 (V1-08b). VOZ is the former name of V (ADR-0009).

- Status: Accepted
- Date: 2026-09-03
- Owners: VOZ maintainers
- Scope: local media inspection, storage and normalization
- Last review: 2026-09-30 (S16.14; adds the current wiring and evidence)
- Diagrams: [components](../architecture/03-componentes.md)

## Context

VOZ must accept audio or video according to its real content, preserve exactly
the bytes the user selected and produce a derivative suitable for ASR.
Recordings can be long, have misleading extensions, contain several streams or
fail after a superficial inspection. In addition, a path can change between two
opens, and FFmpeg processes can finish, fail or be cancelled at any moment.

The UI must not know host paths and the domain must not depend on FFmpeg or on
the filesystem. The relevant boundary is not a list of extensions, but whether
the local FFmpeg installation can decode a real audio stream.

## Decision

Ingestion is coordinated in `application` through typed ports and executed in
`infrastructure` adapters:

1. `MediaStoragePort` copies the selected file to an original whose destination
   is derived only from UUIDs, computes SHA-256 during the same read and
   publishes without replacing existing content.
2. `MediaProbePort` inspects the already-open descriptor of that immutable copy.
   The adapter uses `ffprobe`, validates available streams and codecs and
   returns only allowed metadata, never a path.
3. `ImportMedia` persists the hash, size, duration and a conservative MIME type.
   If the outcome of a write is ambiguous, it reconciles by identity before
   running a destructive compensation.
4. `MediaNormalizationPort` receives the original's descriptor and the
   project/media identities. The FFmpeg adapter selects the absolute index of
   the first decodable audio stream and produces signed 16-bit PCM, mono,
   16 kHz.
5. Temporary files are created inside confined directories, stay open during the
   subprocess and are published atomically without replacement. The source and
   the temporary file are handed to FFmpeg through inherited descriptors on
   Linux.

Normalization reports monotonic progress and checks for cancellation before,
during and right before publishing. A decode failure is translated into a typed
error; stderr, private paths and tracebacks are not part of the normal user
message.

## Storage invariants

- The original is never modified nor used as FFmpeg output.
- Display names are not used as identities or as destination components.
- Directories under the trusted root are opened with `dir_fd` and
  `O_NOFOLLOW`; `lstat` and `fstat` are compared wherever a race could change
  the identity.
- File and directory are synchronized with `fsync` before a durable publication
  is confirmed.
- Cleanup or rollback failures are not silenced as success; they are reported
  when the filesystem prevents confirming the final state.
- Success, failure and cancellation leave no known temporary files or child
  processes.

## Positive consequences

- Probe, hash and metadata correspond to the same immutable bytes.
- WAV, MP3, M4A, OGG, OPUS and WebM share the same contract.
- The file extension does not decide compatibility.
- The application can import and normalize without handing paths to the domain
  or the UI.
- Cancelling does not publish a partial derivative.

## Costs and limits

- The descriptor-based secure adapter uses POSIX/Linux capabilities available
  on Bazzite. A Windows port will need another equivalent mechanism.
- The full technical metadata is kept in the probe result; the initial schema
  persists hash, size, duration and MIME type.
- A persistent filesystem error can prevent confirming a rollback. That state is
  exposed as an explicit error for later reconciliation.
- This ADR covers the local pipeline callable from application. HTTP import and
  its contract are documented in [docs/api/jobs.md](../api/jobs.md); here we
  only record how it is wired (next section).
- FFmpeg and ffprobe are system binaries, not vendored. Without them, import
  fails with a typed error (`MediaProbeFailureCode.TOOL_UNAVAILABLE`, HTTP 503
  `media_probe_unavailable`) and `voz doctor` reports it as a failure. No
  minimum version is pinned or verified; **planned** if a concrete
  incompatibility appears.
- Tested compatibility: synthetic WAV, MP3, M4A, OGG, OPUS and WebM fixtures on
  Linux. Other platforms and containers are experimental.

## Alternatives considered

### Validate by extension

Rejected. An extension can be wrong and does not prove that a decodable audio
stream exists.

### Inspect the path and copy afterwards

Rejected. The file can change between opens, mixing the metadata of one content
with the hash of another.

### Write directly to the final destination

Rejected. A failure or cancellation would leave a partial derivative that would
look complete.

### Expose paths from the use cases

Rejected. It would couple application to the host layout and make leaks toward
the API or the browser easier.

## Current wiring (2026-09-30)

```text
POST /api/projects/{id}/media        (interfaces/api/media.py)
  raw body -> temporary file in ~/.cache/voz/uploads (always deleted)
  -> ImportMedia (application/import_media.py)
       MediaStoragePort  = FileSystemMediaStorage   (immutable copy + SHA-256)
       MediaProbePort    = FfprobeMediaProbe        (on the already-published copy)
       MediaAssetRepository (SQLite)

job in PREPROCESSING state           (application/job_runner.py)
  -> PrepareInferenceAudio -> re-probe of the immutable original
  -> NormalizeImportedMedia -> MediaNormalizationPort = FfmpegMediaNormalizer
  -> projects/<p>/derivatives/<m>.inference.wav  (only if the derivative does not exist)
```

- Normalization happens inside the job, not during the upload (decision of
  Section 5). A resumed job reuses the existing derivative
  (`JobRunner._derivative_exists`).
- The upload rejects empty bodies, unsafe names and sizes above
  `DEFAULT_MAX_UPLOAD_BYTES` (8 GiB). The display name is stored as
  `display_name`; it is never part of the on-disk destination.
- `ffprobe` runs with `timeout_seconds=15` and without a shell
  (`FfprobeMediaProbe`).
- Cancelling a job during normalization reaches FFmpeg through
  `MediaNormalizationCancellationToken`; no partial derivative is published.

## Current evidence (2026-09-30)

| Requirement | Test |
| --- | --- |
| Irrelevant or misleading extension | `tests/integration/audio/test_ffprobe_media_probe.py` |
| Deterministic, decodable fixtures in six formats | `tests/integration/media/test_media_fixtures.py`, licenses in [fixtures-licenses.md](../fixtures-licenses.md) |
| Common probe contract | `tests/contract/test_media_probe_port.py`, `tests/unit/infrastructure/audio/test_ffprobe.py` |
| Immutable copy, hash, symlinks, traversal, `fsync`, cleanup | `tests/unit/infrastructure/test_media_storage.py` |
| Import with compensation and reconciliation | `tests/unit/application/test_import_media.py`, `tests/integration/application/test_import_media_sqlite.py` |
| Mono 16 kHz PCM, intact original, first audio stream | `tests/integration/audio/test_ffmpeg_media_normalizer_integration.py` |
| Cancellation, failing callbacks, symlink and root races, `fsync` failures without partial artifacts | same file |
| Normalization from application | `tests/unit/application/test_normalize_media.py`, `tests/integration/application/test_normalize_imported_media.py` |
| HTTP upload contract without paths | `tests/integration/test_media_upload_api.py` |
| Derivative preparation inside the job | `tests/integration/application/test_job_runner.py::test_missing_derivative_is_prepared_before_transcribing` |

## Additional alternatives considered

### Multipart upload

Not adopted. FastAPI would need an additional dependency for multipart
(documented in [docs/api/jobs.md](../api/jobs.md)); the raw body with the
`X-Voz-Filename` header is streamed directly to a size-limited temporary file
(dependency rule in [AGENTS.md](../../AGENTS.md)).

### Normalize during the upload

Not adopted. It would block the HTTP request with a long, cancellable piece of
work. Normalization is a job stage with progress and cancellation.

### Python audio libraries (PyAV, pydub, soundfile) instead of FFmpeg

Not adopted for now. FFmpeg is already a requirement, decodes the six formats
of the contract and allows passing inherited descriptors without paths. Each
library would add a dependency and another set of codecs to verify.

## Verification

The decision is considered applied when:

- a file with an irrelevant extension is accepted by its streams/codecs;
- the licensed fixtures in six formats are inspected and decoded;
- hash and metadata survive reopening SQLite;
- the import -> normalization path produces 16 kHz mono PCM and leaves the
  original byte-identical;
- cancellation, corruption, callback errors and simulated races do not publish
  partial artifacts nor leave open processes or descriptors;
- traversal, symlink and unsafe-name tests do not write outside the root.
