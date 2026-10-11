# ADR-0004: Local ASR with explicit models and recoverable chunks

> Translated from Spanish on 2026-10-11 (V1-08b). VOZ is the former name of V (ADR-0009).

- Status: Accepted
- Date: 2026-09-05
- Owners: VOZ maintainers
- Scope: first local ASR provider and recovery of long jobs
- Last review: 2026-09-30 (S16.15/S16.16: wiring note and evidence; the
  decision does not change)
- Related: [ADR-0005](0005-transcription-providers.md) (port and registry),
  [ADR-0006](0006-local-first-privacy.md) (offline and no implicit cloud)

## Context

VOZ needs to integrate Faster Whisper without turning the Internet, CUDA or an
external cache into implicit requirements. It must also process long
recordings without losing the chunks already confirmed after cancelling or
closing the application. The common contract cannot expose Faster Whisper or
CTranslate2 types, host paths or engine-specific flags.

## Decision

Faster Whisper is an infrastructure adapter under `TranscriptionProvider`. The
adapter receives an open audio descriptor and resolves exclusively one exact
local installation; it never hands a remote name to the runtime. It is
instantiated with `local_files_only=True` and translates output, language,
cancellation and failures into canonical application types.

Models are represented by `ModelDescriptor`, whose installable provenance
contains both the source repository and a pinned revision. Installation is a
separate operation that requires explicit confirmation, uses
`huggingface_hub.snapshot_download` with that revision and publishes a copy with
a manifest under the XDG data directory. Download metadata lives under the XDG
cache directory. Importing VOZ, building the provider or transcribing does not
start downloads.

The installable revision must be a full Git commit SHA, hexadecimal and 40
characters long; mutable branches and tags do not form a recoverable identity.
The storage and cache identity includes provider, model, source and revision.
The provider keeps at most one active engine so as not to hold the `fast` and
`quality` profiles in VRAM at the same time, and serializes its concurrent
initialization. The composition root pins the provider to the exact descriptor
with which it resolved device and compute; it cannot reuse that decision with
another model or profile.

`faster-whisper` is distributed as the optional `asr-local` extra; the basic
startup loads neither its runtime nor CUDA. The pinned revision and the
manifest are the initial provenance evidence. Additional checksums and advanced
catalog administration belong to Section 8.

The `fast` and `quality` profiles will be canonical descriptors resolved to an
observable device/compute decision. A fallback from CUDA to CPU will never be
silent.

The orchestrator splits the normalized duration into ordered chunks with global
offsets and a small overlap. The audio adapter opens a physical PCM WAV bounded
to each chunk so as not to decode the whole recording repeatedly. The provider
produces local offsets and application converts them only once to the global
timeline. Each chunk becomes a recoverable unit. The confirmation of its
segments, requested and detected language, checkpoint and job progress happens
in a single SQLite transaction. On resume, only chunks whose complete
confirmation exists for the same job, plan, provider, model, source, revision
and requested language are skipped.

The checkpoint keeps the completed ASR fraction and the job's monotonic global
progress separately. That way, an ASR stage that begins with previous progress
can be resumed without confusing the two progress spaces.

## Lifecycle and cancellation fix — 2026-09-07 (Cut A)

The S4 → S5 audit reproduced two defects: assigning the new engine evaluated
its load while still holding the previous one, and an empty iterable could
return success despite a cancellation. This fix corresponds to S4.04/S4.13; it
does not start Section 5 or a Model Manager.

- A replacement first resolves the installation and checks cancellation. It then
  empties the key and the reference to the previous engine **before** calling
  the new factory. If that load fails, the cache stays empty and either the new
  or the previous model can be retried. If resolution fails, the previous cache
  remains valid; no other load has started.
- `FasterWhisperProvider.close()` is explicit, idempotent and final. It uses the
  same lock that protects loading and inference, including lazy iteration: it
  waits for the active call, empties the cache and rejects future
  transcriptions with a non-retryable `PROVIDER_FAILED`. A new cycle requires
  another adapter.
- The runtime owner must call `LocalAsrRuntime.close()` in its shutdown
  `finally` (`contextlib.closing(runtime)` also works). This method delegates to
  the concrete adapter. No `close()` is added to `TranscriptionProvider`:
  acquiring/releasing the engine belongs to infrastructure/the composition root,
  not to the transcription contract consumed by application. The current HTTP
  application does not create an ASR runtime; no lifespan or fictitious executor
  is added.
- The adapter checks cancellation before loading, after resolving/loading, after
  `engine.transcribe()`, during iteration and before returning success. It also
  covers empty iterables and cancellation when they are exhausted, without
  relying on the additional check in `RecoverableTranscription`. The
  `CANCELLED` code is preserved.
- Segment generators are closed in `finally`; local references to the
  engine/iterable are cleared so that cancellation tracebacks do not retain
  them. SDK failures also clear the locals of terminated frames in their
  cause/context chains, including partially built engines. Type, message and
  stack are preserved, but not the locals for post-mortem debugging. The
  released property is the adapter's: no global GC is forced, the CUDA allocator
  is not manipulated and no resource framework is implemented.

Cancellation is cooperative: it does not interrupt a blocked native call and
closing waits for it to return. The release of references is tested with
deterministic engines and weakrefs, without `gc.collect()` or a GPU; it does
not prove VRAM release or real CUDA transcription. The experimental rating of
S4 is kept.

Regression evidence: `test_faster_whisper_lifecycle.py` covers replacement
without overlap, failed load/retry, closing before/after loading or failing,
concurrent closing through events and an observable lock, cancellation per
phase, cleanup with a retained exception (including chained SDK failures and
partial construction) and empty success. The existing suite keeps engine reuse,
serialization and canonical results; the bootstrap test verifies that closing
the runtime reaches the registered provider.

## Wiring update — 2026-09-30

The Cut A note saying that the HTTP application does not create an ASR runtime
became outdated with Section 5 and does not alter the decision:

- `create_app()` (`src/voz/bootstrap.py`) builds one `LocalAsrRuntime` per
  descriptor on demand through `provider_for(selection)`, using the
  `ModelDescriptor` stored in the job snapshot. The `lifespan` calls
  `runtime.close()` for each one on shutdown and closes the `JobRunner` first.
- The `JobRunner` runs `RecoverableTranscription` in a thread; at startup,
  `runner.recover()` re-enqueues the non-terminal jobs and the confirmed
  checkpoints avoid repeating chunks (`tests/integration/application/test_job_runner.py::test_recover_resumes_transcribing_job_without_repeating_chunk`).
- Model installation (`FileSystemModelStore.install`) is **not** exposed through
  HTTP or the CLI: no code in `src/voz/` invokes it. A model must already be
  installed for an option to be startable (`can_start` in
  `/api/transcription-options`). A Model Manager with a user interface is
  Section 8, **planned**.
- Only Faster Whisper is implemented. The remaining providers and their
  registry are covered in [ADR-0005](0005-transcription-providers.md).

## Positive consequences

- Offline mode does not depend on remote resolution during transcription.
- An installation identifies exactly the source and revision.
- Faster Whisper and future providers share result, errors and cancellation.
- Closing VOZ does not invalidate already-confirmed chunks.
- Memory and decoding are bounded by the chunk size.
- Domain and application do not import ASR SDKs.

## Costs and limits

- Installing the extra and a model remains a separate action from the
  bootstrap.
- Real CUDA availability depends on the machine's driver and runtime; until an
  opt-in test is run, the GPU path is labeled experimental.
- A pinned revision provides provenance reproducibility, but does not replace a
  published checksum; extended verification is left for the Model Manager.
- The overlap requires a deterministic policy so as not to duplicate segments.

## Upstream sources

- Faster Whisper can load a local directory and offers `local_files_only`:
  <https://github.com/SYSTRAN/faster-whisper>
- Hugging Face documents `snapshot_download` with `revision` and `cache_dir`:
  <https://huggingface.co/docs/huggingface_hub/en/package_reference/file_download>
- CTranslate2 exposes the compute types supported per device:
  <https://opennmt.net/CTranslate2/python/ctranslate2.get_supported_compute_types.html>

## Current evidence (2026-09-30)

| Requirement | Test |
| --- | --- |
| Adapter, timestamps, language and canonical errors | `tests/unit/infrastructure/asr/test_faster_whisper.py`, `tests/contract/test_transcription_provider.py` |
| Lifecycle: replacement, `close()`, cancellation per phase | `tests/unit/infrastructure/asr/test_faster_whisper_lifecycle.py` |
| Descriptor catalog, hardware and options | `tests/unit/infrastructure/asr/test_catalog.py`, `test_hardware.py`, `test_options.py`, `tests/unit/application/test_asr_device_selection.py` |
| Explicit installation, pinned revision, manifest | `tests/unit/infrastructure/test_model_storage.py` |
| Composition without downloads and runtime closing | `tests/unit/test_asr_bootstrap.py` |
| Recoverable chunks and resume | `tests/unit/application/test_chunked_transcription.py`, `tests/integration/application/test_recoverable_transcription.py`, `tests/integration/application/test_local_asr_pipeline.py` |
| Opt-in real smoke test with a user-installed model | `tests/integration/application/test_faster_whisper_real_opt_in.py` (`VOZ_FASTER_WHISPER_MODEL_*` variables) |

## Verification

This decision is considered applied when:

- building/using the adapter without a model produces no network access or
  download;
- an unconfirmed installation fails before building the downloader;
- the manifest keeps the exact provider, model, source and revision;
- the adapter converts timestamps to milliseconds and preserves text and
  language;
- failures and cancellation are translated to stable codes without private
  paths;
- the profiles and fallback are observable through deterministic tests;
- reopening SQLite recovers confirmed chunks without repeating them.
- the contract suite runs against the adapter and an opt-in real smoke test
  exists that never selects or downloads models on its own.
