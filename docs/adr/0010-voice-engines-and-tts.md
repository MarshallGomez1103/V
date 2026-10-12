# ADR-0010: Voice engines and models, and the speech synthesis (TTS) architecture

- Status: Accepted
- Date: 2026-10-11
- Owners: V maintainers
- Scope: the engine/model split for every voice capability (STT, TTS,
  diarization and later ones), the `SpeechSynthesisProvider` port, the first
  TTS engine, the shared compute slot, OpenAI-compatible engines in both
  directions, isolated runtimes, model licensing and capability declarations
  (Programa V slices V2-01 to V2-06, V3-01 to V3-05, V4-01 to V4-05, V6-01,
  V6-05, V10-07)
- Related: [ADR-0001](0001-modular-monolith.md) (hexagonal boundaries),
  [ADR-0004](0004-local-asr-and-recoverable-chunks.md) (explicit models),
  [ADR-0005](0005-transcription-providers.md) (provider port, no plugin
  framework), [ADR-0006](0006-local-first-privacy.md) (local-first, explicit
  cloud), [ADR-0007](0007-local-diarization-sherpa-onnx.md) (sherpa-onnx,
  no torch), [ADR-0009](0009-rename-to-v.md) (V as a voice harness)
- Diagrams: [components](../architecture/03-componentes.md)

## Context

V started as a local transcriber and is becoming a **local voice harness**:
the user picks any speech-to-text or text-to-speech model, downloads it
explicitly and runs it on their own hardware, without payments or accounts.
External APIs are optional and only used when the user configures them.
KittenTTS, which triggered the TTS discussion, is one possible model, not the
axis of the design.

Facts that shape the decision:

- **The STT side already has several real engines** behind
  `TranscriptionProvider` (`src/voz/application/ports/transcription.py`):
  Faster Whisper, whisper.cpp and optional cloud providers. The rule of
  [ADR-0005](0005-transcription-providers.md) (no plugin framework, explicit
  registry in the composition root) has held up and is kept.
- **Native inference holds the GIL.** sherpa-onnx's diarization call keeps the
  GIL for minutes, freezing the HTTP server, live progress and the cancel
  button. `src/voz/infrastructure/diarization/worker.py` solved it by running
  the native call in a child process that talks over pipes
  (`VOZ P <done> <total>`, `VOZ R ...`, `VOZ END`); cancelling kills the
  child. TTS inference is the same kind of native call.
- **sherpa-onnx already ships an offline TTS engine** in the installed
  `diarization` extra. Verified in the project environment on 2026-10-11
  (`.venv/bin/python`, no network, no model downloaded):
  - `sherpa_onnx.__version__ == "1.13.8"`; TTS names exported: `OfflineTts`,
    `OfflineTtsConfig`, `OfflineTtsModelConfig` and one model config per
    family: `OfflineTtsKittenModelConfig`, `OfflineTtsKokoroModelConfig`,
    `OfflineTtsMatchaModelConfig`, `OfflineTtsVitsModelConfig` (Piper voices),
    `OfflineTtsPocketModelConfig`, `OfflineTtsSupertonicModelConfig`,
    `OfflineTtsZipvoiceModelConfig`.
  - `OfflineTtsConfig(model, rule_fsts='', rule_fars='', max_num_sentences=1,
    silence_scale=0.2)`; `OfflineTtsModelConfig(vits, matcha, kokoro,
    zipvoice, kitten, pocket, supertonic, num_threads=1, debug=False,
    provider='cpu')`. Exactly one family config is filled per model; the
    family is therefore model metadata, not code.
  - `OfflineTts(config)` exposes `sample_rate` and `num_speakers` (read-only
    properties) and `generate`, with three overloads:
    1. `generate(text, sid=0, speed=1.0, callback=None)`;
    2. `generate(text, config: GenerationConfig, callback=None)`, where
       `GenerationConfig` has `sid`, `speed`, `silence_scale`, `num_steps`,
       `reference_audio`, `reference_sample_rate`, `reference_text` and
       `extra`;
    3. `generate(text, prompt_text, prompt_samples, sample_rate, speed=1.0,
       num_steps=4, callback=None)` (zero-shot prompt, i.e. voice cloning).
  - `callback(samples: float32 ndarray, progress: float) -> int` is called
    during generation; returning non-zero stops it early.
  - The result (`GeneratedAudio`) carries `samples` (float32, mono) and
    `sample_rate`. The sample rate is a property of the model, not a request
    option; a voice is a speaker id (`sid`) in `[0, num_speakers)`.
- **KittenTTS 2 is a different case** (`.ai/audit-av/07-KITTENTTS-RESEARCH.md`,
  consulted 2026-10-10): PyTorch per its model card, ~0.5-1 GB of weights,
  and weights under the **Stellon Labs Community License** (free for research
  and limited commercial use below a revenue/funding cap; distribution carries
  attribution requirements; the full text could not be read). It cannot share
  V's environment, which deliberately has no torch
  ([ADR-0007](0007-local-diarization-sherpa-onnx.md)), and its weights cannot
  ship in a V installer or release.
- **V0-09d** (`src/voz/infrastructure/asr/runtime_cache.py`) introduced
  `SingleRuntimeCache`: at most one ASR runtime resident, closed when another
  key is requested and after `ASR_IDLE_SECONDS` without use.
- Many local servers and hosted APIs speak the OpenAI audio API
  (`/v1/audio/transcriptions`, `/v1/audio/speech`); other local apps would
  benefit from reaching V's models through the same shape.

## Decision

### 1. Engine + model

V separates two concepts for every voice capability:

- An **engine** is code that knows how to run a family of models (Faster
  Whisper, whisper.cpp, sherpa-onnx diarization, sherpa-onnx TTS, an
  OpenAI-compatible HTTP endpoint...). Engines are Python modules that ship
  with V, are constructed and registered explicitly in the composition root
  (`src/voz/bootstrap.py`) and are never discovered or loaded dynamically
  (no entry points, no import by name from configuration). This keeps
  [ADR-0005](0005-transcription-providers.md) decision 6 in force for TTS: the
  registry stays a map.
- A **model** is data: weights and configuration files from the pinned
  catalog or added by the user ("Add your own model", V6-05). A model
  declares which engine and family run it. **V never executes code that was
  downloaded**: no `trust_remote_code`, no pickled Python objects, no scripts
  from a model repository. A model whose engine is not installed is shown as
  unusable, never "fixed" by fetching code.

### 2. A separate `SpeechSynthesisProvider` port

TTS gets its own port in `src/voz/application/ports/speech_synthesis.py`
(**planned**, V2-03), structurally typed (`Protocol`) like
`TranscriptionProvider`, and **not** a set of optional methods on it. The
conceptual contract:

| Member | Purpose |
| --- | --- |
| `describe()` | engine id, display name, locality (`local` / `cloud`), whether it streams |
| `voices(model)` | voices of an installed model (id, display name, languages) |
| `languages(model)` | languages the model can speak |
| `requirements(model)` | runtime readiness and resource hints (RAM, threads, device) |
| `synthesize(chunk, voice, options, cancellation)` | renders one text chunk to PCM; cancellable |
| `close()` | releases the engine (child process, sessions) |

Errors are typed with stable codes: `voice_not_found`, `model_not_installed`,
`runtime_unavailable`, `synthesis_failed`, `cancelled` (exposed as
`{"detail": {"code", "message"}}`, never with host paths).

TTS has its own domain entities (**planned**, V2-02): `Voice`,
`SynthesisRequest`, `SynthesisJob` (state machine mirroring
`TranscriptionJob`: QUEUED, RUNNING, CANCELLING, CANCELLED, FAILED,
COMPLETED) and `SynthesizedAudio` (relative path, duration, sample rate,
sha256, chunks). No engine or SDK class appears in domain or application
signatures; sherpa-onnx types stay private to `src/voz/infrastructure/tts/`.
Long text is split into ordered chunks by a pure application function
(V2-04) and the chunks are assembled by V, so engines only ever see one chunk.

### 3. First TTS engine: sherpa-onnx `OfflineTts` in a child process

- The first local engine is `sherpa_onnx.OfflineTts` (1.13.8, already
  installed with the `diarization` extra; no new dependency). Families in
  scope are the ones the binding exposes: kitten, kokoro, matcha, vits
  (Piper), pocket, supertonic and zipvoice. Which ones enter the catalog is
  decided by measurement (V4-01) and license review (V4-03), not by this ADR.
- The worker builds `OfflineTtsConfig` from the family declared in the model
  manifest (V4-02); voices map to `sid` in `[0, num_speakers)`; speed maps to
  `speed`.
- Inference runs in a **child process**, generalizing the protocol of
  `src/voz/infrastructure/diarization/worker.py` (V3-01): argv carries model
  paths and options, stdin carries the request, stdout carries prefixed
  progress, audio and end/error lines; anything else on stdout is ignored.
  Cancellation terminates the child; a crash of the child becomes
  `synthesis_failed` and never takes down the server. The native `callback`
  is used for progress inside the child, not across the process boundary.
- **Output contract:** WAV, PCM signed 16-bit little endian, **mono**, at the
  **model's native sample rate** (no resampling by default). The float32
  samples returned by the engine are converted in the child or the adapter.
  The stored file records its sample rate and sha256.
- **Streaming is opt-in per engine:** only an engine whose `describe()`
  declares it may deliver partial audio before a chunk ends. The baseline is
  per-chunk progress, which every engine supports through chunking.
- **Voice cloning is not enabled.** The prompt/reference overloads of
  `generate` (zero-shot) stay unused until the consent decision in point 9 is
  implemented.

### 4. One shared compute slot

STT, TTS and diarization share a **single compute slot** (V3-03): at most one
heavy inference runs at a time; other jobs wait in a visible queue. This
avoids CPU/GPU contention and memory spikes on laptop hardware. The slot
builds on V0-09d's `SingleRuntimeCache` (one resident runtime, closed when
another is requested or after the idle timeout) rather than replacing it; a
TTS child process counts as the resident runtime while it runs.

### 5. OpenAI-compatible engines, in both directions

- **V as a client** (V4-04): one engine, configured by the user with a
  `base_url`, an optional key (stored through `ProviderSecrets`) and a model
  name, implements STT (`POST /v1/audio/transcriptions`) behind
  `TranscriptionProvider` and TTS (`POST /v1/audio/speech`) behind
  `SpeechSynthesisProvider`. A `base_url` whose host is a loopback address
  counts as **local**; any other host counts as **CLOUD** and follows
  [ADR-0006](0006-local-first-privacy.md): explicit consent before the first
  request, visible in the UI, and **never** used as a fallback for a local
  engine.
- **V as a server** (V10-07): V exposes `/v1/models`,
  `/v1/audio/transcriptions` and `/v1/audio/speech`, delegating to the same
  use cases, so other local apps can use V's models. These endpoints are
  reachable **only on loopback by default**; when V is bound to a network
  host they require the local token of V10-02.

### 6. Isolated runtimes only for heavy engines (deferred)

Engines whose dependencies cannot live in V's environment (torch, a
conflicting ONNX Runtime; e.g. native KittenTTS or KittenTTS 2) run in their
own `uv` environment under `$XDG_DATA_HOME/voz/runtimes/<family>/`, created
only when the user explicitly installs that runtime, with a lock versioned in
`packaging/runtimes/<family>/`, and driven through the same child-process
protocol. This is **deferred** (V3-02, V4-05): the first TTS engine does not
need it.

### 7. Licenses are catalog data

Every catalog model declares its license (and source and pinned revision);
the license is shown before download (V6-03). Weights with restrictive terms
(for example KittenTTS 2 under the Stellon Labs Community License) are
**never redistributed** by V: not bundled in installers, wheels or releases.
The user downloads them explicitly from the upstream source. User-added
models are registered with the license "declared by the user / unknown".

### 8. Capabilities per model, with an invariant

Model descriptors carry capabilities. V6-01 extends `ModelCapability`
(`src/voz/domain/entities/model_descriptor.py`, which today has
`transcription`, `diarization` and others) with `synthesis`, `alignment` and
`wake_word`. **Invariant:** no model may declare a capability for which no
registered engine implements the corresponding port; a test enforces it.

### 9. Consent for voice cloning (future)

Any feature that synthesizes speech in the voice of a reference recording
requires explicit, recorded consent from the user that they have the right to
use that voice, keeps the reference audio local, and is out of scope until a
dedicated slice designs it.

## Positive consequences

- Adding a model is a data change; adding a model family to an existing
  engine is a small mapping; adding an engine is an explicit, reviewed code
  change. No plugin surface is exposed.
- The first TTS engine costs no new dependency and keeps V torch-free.
- A crash, hang or GIL-holding native call in an engine cannot freeze or kill
  the server, and cancellation is reliable (kill the child).
- The OpenAI-compatible engine lets users reuse local inference servers they
  already run, and V can serve its own models to other apps.
- The privacy rule of ADR-0006 extends to TTS and to user-configured endpoints
  without special cases.

## Costs and limits

- One child process per synthesis run reloads the model each time
  (ponytail: a warm worker only if V4-01 measures load time as dominant).
- A single compute slot serializes work: a long transcription delays a short
  TTS request. Accepted for laptop hardware; revisited only with evidence.
- The output is always WAV at the model's rate; compressed formats or
  resampling are export-time features, not part of the engine contract.
- Loopback-vs-cloud is decided by the host of `base_url`; a LAN server the
  user trusts is treated as cloud (consent once), which is deliberate.
- The contract will be validated by one real local engine first; the
  OpenAI-compatible engine is the second implementation that tests it.
- Per-family quirks (lexicons, dict dirs, rule FSTs, `lang` for Kokoro) live
  in the family mapping and must be covered by tests with fake workers; real
  models are opt-in (`VOZ_TTS_E2E_MODEL`).

## Alternatives considered

| Alternative | Why it was rejected |
| --- | --- |
| Optional TTS methods on `TranscriptionProvider` | Capabilities evolve separately (ADR-0005 decision 7); it would force every STT engine to stub TTS |
| Plugin framework (entry points, dynamic imports, downloaded engine code) | Security and compatibility surface; contradicts ADR-0005 and the rule that downloaded code is never executed |
| Run TTS in-process or in a thread | The native call holds the GIL and freezes the server (proven by diarization); a native crash would kill V |
| KittenTTS 0.8/2 as the first engine, in an isolated runtime (previous plan section C) | Needs a second environment and, for v2, torch and restrictive weights; sherpa-onnx already runs the Kitten family with no new dependency |
| Separate compute queues for STT and TTS | CPU/GPU contention and memory spikes on the target hardware |
| Treat any configured `base_url` as local | Would send audio or text off the machine without consent, violating ADR-0006 |
| Bundle model weights in the installer | License restrictions (Stellon Labs) and size; ADR-0004/0006 require explicit downloads |

## Current evidence (2026-10-11)

| Requirement | Code or test |
| --- | --- |
| Child-process precedent for GIL-holding native calls | `src/voz/infrastructure/diarization/worker.py`, `_ChildEngine` in `src/voz/infrastructure/diarization/sherpa.py` |
| One resident runtime, released when idle | `src/voz/infrastructure/asr/runtime_cache.py`, `tests/unit/test_asr_runtime_cache.py` |
| Structural provider port and explicit registry | `src/voz/application/ports/transcription.py`, `src/voz/application/transcription_provider_registry.py` |
| Capabilities in the model descriptor (to be extended) | `src/voz/domain/entities/model_descriptor.py` (`ModelCapability`) |
| sherpa-onnx TTS API available, no new dependency | verified in `.venv` on 2026-10-11 (see Context); sherpa-onnx 1.13.8 |
| `SpeechSynthesisProvider`, TTS entities, worker, compute slot, catalog, OpenAI-compatible engine and server | **planned** (V2-02, V2-03, V3-01, V3-03, V4-02, V4-03, V4-04, V10-07) |

## Verification

This decision is considered respected when:

- no module outside `src/voz/infrastructure/tts/` (and
  `src/voz/infrastructure/diarization/`) imports `sherpa_onnx`, and the server
  process never calls `OfflineTts.generate` directly;
- every TTS engine passes the same contract suite
  (`tests/contract/test_speech_synthesis_provider.py`, planned) with typed
  errors and cancellation;
- no code loads engines by name from configuration or executes files from a
  model directory; model import accepts weights and configuration only;
- the capability invariant test (V6-01) passes for the whole catalog;
- every catalog model has a license, source and pinned revision/sha256, and
  restricted weights are absent from wheels and installers
  (`tests/packaging/test_wheel_contents.py`);
- an OpenAI-compatible `base_url` outside loopback is never called without
  recorded consent and never selected as a fallback;
- the `/v1/*` server endpoints reject non-loopback clients without the token;
- at most one heavy inference (ASR, diarization or TTS) runs at a time.

**Review criterion:** revisit this ADR when an isolated runtime (V3-02) is
actually implemented, when a second local TTS engine arrives, or when voice
cloning is proposed.
