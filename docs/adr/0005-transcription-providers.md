# ADR-0005: Transcription provider port without a plugin framework

> Translated from Spanish on 2026-10-11 (V1-08b). VOZ is the former name of V (ADR-0009).

- Status: Accepted
- Date: 2026-09-30
- Owners: VOZ maintainers
- Scope: the `TranscriptionProvider` contract, the registry and the rule for
  growing providers (S16.15)
- Related: [ADR-0001](0001-modular-monolith.md) (boundaries),
  [ADR-0004](0004-local-asr-and-recoverable-chunks.md) (Faster Whisper),
  [ADR-0006](0006-local-first-privacy.md) (cloud only by explicit choice)
- Diagrams: [components](../architecture/03-componentes.md)

## Context

The master plan anticipates several engines: Faster Whisper (the main local
one), whisper.cpp, OpenAI and ElevenLabs (optional cloud), plus diarization and
alignment. The use cases must not know the types of a specific SDK. At the same
time, [AGENTS.md](../../AGENTS.md) forbids building a dynamic plugin framework
before at least two real providers demonstrate the necessary abstraction.

Today there is **a single real provider**: Faster Whisper. Designing the
extension point from a single example tends to bake that engine's details into
the contract, so the abstraction is kept minimal and revisited when the second
one arrives.

## Decision

1. **A single, structural port.** `TranscriptionProvider` is a
   `runtime_checkable` `Protocol` in `src/voz/application/ports/transcription.py`,
   with the `provider_id` property and the method
   `transcribe(*, audio: BinaryIO, options: TranscriptionOptions, cancellation: TranscriptionCancellationToken | None) -> TranscriptionResult`.
   Adapters do not inherit from application: they satisfy the protocol.
2. **Engine-independent canonical types** in the same module:
   `TranscriptionOptions` (`ModelDescriptor`, optional language and optional
   `TranscriptionClip`), `TranscriptionResult` and `TranscriptionSegment`
   (integer milliseconds, ordered and non-overlapping, literal text),
   `TranscriptionFailureCode` (`transcription_model_not_installed`,
   `transcription_gpu_unavailable`, `transcription_invalid_audio`,
   `transcription_provider_failed`, `transcription_cancelled`) and
   `TranscriptionError` with a safe message and `retryable`. SDK types (engine,
   segments, `compute_type`) remain private to the adapter (`_Engine`,
   `_EngineSegment` in `src/voz/infrastructure/asr/faster_whisper.py`).
3. **Model identity in the domain.** `ModelDescriptor` and `ProcessingProfile`
   (`src/voz/domain/entities/`) carry `provider_id`, model, provenance
   (`source` + pinned `revision`) and capabilities (`ModelCapability`). Audio
   arrives as an open descriptor, never as a path.
4. **Explicit, deterministic registry.** `TranscriptionProviderRegistry`
   (`src/voz/application/transcription_provider_registry.py`) is an in-memory
   dictionary injected through the constructor: it validates that the candidate
   implements the port, that `provider_id` is a safe identifier
   (`[a-z0-9][a-z0-9._-]{0,63}`), rejects duplicates without replacing them and
   lists in lexical order. It does not discover modules, does not import by name
   and does not read configuration.
5. **Composition in a single place.** `create_local_asr_runtime`
   (`src/voz/bootstrap.py`) builds `FasterWhisperProvider` for an exact
   descriptor and registers it; `create_app` exposes `provider_for(selection)`
   to the `JobRunner`, which receives a
   `Callable[[JobSelection], TranscriptionProvider]` and never imports an
   adapter.
6. **No-plugin-framework rule.** Until **two real, executed providers** exist
   (not test doubles), no entry points, dynamic module loading, plugin
   manifests, base hierarchies or generalization of
   `create_local_asr_runtime` are added. The current registry is a map, not a
   plugin mechanism. The arrival of the second provider (whisper.cpp,
   Section 9, or an optional cloud one) forces a review of this ADR and the
   extraction of only what the two really share.
7. **Additional capabilities, separate and later contracts.**
   `DiarizationProvider` and `AlignmentProvider` (mentioned in ADR-0001) do not
   exist; they will be created with their roadmap section and their own
   canonical types, not as optional methods of `TranscriptionProvider`.
8. **Cloud providers** will implement the same port, but are only selected by
   the user's explicit decision and follow the rules of
   [ADR-0006](0006-local-first-privacy.md). They do not exist in the code.

## Positive consequences

- The use cases (`RecoverableTranscription`, `JobRunner`) are tested with fake
  providers and import no SDK.
- Changing the engine does not alter the canonical transcript representation or
  the UI.
- The absence of a plugin framework avoids public API commitments based on a
  single example.
- Errors reach the API as stable codes without paths or tracebacks.

## Costs and limits

- With a single provider, the registry adds little beyond identity validation;
  it is kept because it is already the surface the second provider will use.
- Parts of the system are Faster Whisper-specific today by design:
  `create_local_asr_runtime` rejects descriptors from another provider with
  `ValueError`; `provider_for` in `create_app` always builds a local Faster
  Whisper runtime; `LocalTranscriptionModelCatalog` and
  `FasterWhisperRuntimeProbe` (`src/voz/infrastructure/asr/options.py`) only
  know that engine. Adding another will require generalizing those points (and
  only then).
- The port does not include `close()`: releasing resources belongs to the
  adapter's owner in the composition root
  ([ADR-0004](0004-local-asr-and-recoverable-chunks.md)).
- The contract suite runs a structural provider and `FasterWhisperProvider`
  with a fake engine; the real-model path is an opt-in smoke test. Proof that
  the contract is sufficient will come with the second real engine.
- Word timestamps, translation and diarization are not part of the current
  contract.

## Alternatives considered

### Plugin framework (entry points, dynamic loading, manifests)

Rejected for now. Forbidden by AGENTS.md until there are two real providers; it
would add security and compatibility surface without a second use case.

### Abstract base class (`ABC`) instead of `Protocol`

Rejected. It would force adapters to import application and inherit; the
structural protocol keeps the dependency pointing inward and allows simple
doubles in tests.

### A single "ASR" port with transcription, alignment and diarization

Rejected. Capabilities vary per engine and evolve separately; they are modeled
as independent ports when they exist.

### Provider selection through conditionals in the use cases

Rejected. It leaks engine details into application and forces modifying it for
each new provider.

### Global registry (singleton) or service locator

Rejected. It hides dependencies and makes tests harder; the registry is an
instance injected from the composition root.

## Current evidence (2026-09-30)

| Requirement | Code or test |
| --- | --- |
| Port and canonical types | `src/voz/application/ports/transcription.py`, `tests/contract/test_transcription_provider.py` (validation of segments, result and options) |
| Contract shared by implementations | same file, `provider_case` fixture with `structural` and `faster-whisper`: valid audio, monotonic timestamps, typed invalid audio, cancellation |
| Registry: identity, duplicates, order, immutable snapshot, rejection of non-providers | `tests/unit/application/test_transcription_provider_registry.py` |
| Registry without infrastructure or framework imports | `test_registry_has_no_domain_infrastructure_or_framework_imports` |
| Faster Whisper as the only real adapter | `src/voz/infrastructure/asr/faster_whisper.py` (`provider_id = "faster-whisper"`) and `tests/unit/infrastructure/asr/` |
| Explicit composition without downloads | `tests/unit/test_asr_bootstrap.py` (`providers.provider_ids() == ("faster-whisper",)`, rejection of another provider) |
| The job uses the provider through a factory | `tests/integration/application/test_job_runner.py` |

## Verification

This decision is considered respected when:

- no use case imports a module under `voz.infrastructure`;
- every provider exposes a safe `provider_id`, unique in the registry;
- every new provider is added to the `tests/contract/` suite and passes the same
  cases;
- SDK types do not appear in public application signatures nor in the API;
- no dynamic provider discovery code exists while there is only one real
  provider.

**Review criterion:** when integrating the second real provider, update or
replace this ADR with what both share and remove the Faster Whisper-specific
points listed in "Costs and limits".
