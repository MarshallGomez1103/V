# ADR-0001: Local modular monolith with hexagonal architecture

> Translated from Spanish on 2026-10-11 (V1-08b). VOZ is the former name of V (ADR-0009).

- Status: Accepted
- Date: 2026-09-01
- Owners: VOZ maintainers
- Scope: initial product architecture and hexagonal boundaries
- Last review: 2026-09-30 (S16.12, no change to the decision)
- Diagrams: [C4 context](../architecture/01-contexto.md),
  [containers](../architecture/02-contenedores.md),
  [components](../architecture/03-componentes.md)

## Context

VOZ will be a local-first application for importing audio or video, running
long transcriptions, editing synchronized results and exporting them. On a
single machine it will share the GPU, filesystem, database and lifecycle. The
first version needs a simple installation, operation without Internet after
models are downloaded, and the ability to incorporate different transcription
and diarization providers.

The heavy work must run without blocking the interface and must be able to
save recoverable progress. However, splitting the application into independent
services from the start would add ports, deployments, serialization,
distributed observability and new failure modes without isolating any physical
resource: they would all still compete for the same GPU and the same disk.

The variation worth isolating lies between the domain and the external
mechanisms: FastAPI, SQLite, FFmpeg, ASR engines, cloud providers and the web
interface.

## Decision

VOZ will initially be implemented as a **local modular monolith** with a
**Clean/Hexagonal architecture** and an **asynchronous internal job
pipeline**.

Dependencies point toward the core:

```text
Web UI / CLI / API
        |
        v
Application use cases
        |
        v
Domain

Infrastructure adapters implement application/domain ports
```

These boundaries are established:

- **Domain:** entities, value objects, rules and invariants with no framework
  dependencies.
- **Application:** use cases, ports and pipeline coordination.
- **Infrastructure:** adapters for persistence, filesystem, FFmpeg, models,
  ASR, diarization and observability.
- **Interfaces:** HTTP API, CLI and translation between external and internal
  contracts.
- **Web UI:** client of the HTTP/event contract; it knows neither host paths
  nor provider details.

External providers will implement common contracts, for example
`TranscriptionProvider`, `DiarizationProvider` and `AlignmentProvider` (today
only the first exists; see the review below). The selection and construction of
adapters happens in a composition root.

Long operations will be modeled as jobs with explicit state, progress,
cancellation, typed errors and checkpoints where applicable. For server-to-
browser progress, SSE will be preferred; WebSocket will only be added if a
concrete bidirectional need appears.

SQLite and the filesystem are initial infrastructure decisions, not domain
dependencies. Runtime data will follow the XDG Base Directory specification and
will be kept outside the checkout.

## Positive consequences

- A single installation and a single local process are enough for the first
  version.
- The domain can be tested without loading the GPU, FFmpeg, FastAPI or cloud
  clients.
- Replacing Faster Whisper with whisper.cpp does not require changing the
  domain.
- Adding a cloud provider does not force a redesign of the canonical transcript
  representation or of the core UI.
- Persistence and providers can evolve through ports and adapters.
- Checkpoints and progress events are kept without introducing distributed
  infrastructure.
- Local deployment, diagnostics and privacy are easier to reason about.

## Costs and limits

- The module boundaries depend on discipline and tests; a process boundary does
  not enforce them.
- A task that blocks the event loop can affect the whole application. CPU/GPU
  work must run through appropriate workers/processes.
- A process failure can interrupt every module, so incremental persistence and
  recovery are real requirements.
- SQLite does not aim to cover distributed multi-user use.
- The composition root must avoid coupling use cases to concrete
  implementations.

## Alternatives considered

### Microservices from v1

Rejected. It multiplies deployment, communication, observability and recovery,
but does not separate the GPU nor improve the case of a local user.

### Direct integration with Buzz's process or GUI

Rejected as the central architecture. Buzz can be a reference and its cache can
be integrated through an optional adapter, but its internal details will not be
VOZ's contract.

### Electron/Tauri desktop application from the start

Postponed. The local web flow served by `voz` will be validated first. A
desktop wrapper can be evaluated later without changing the core.

### Event Sourcing or full CQRS

Rejected for v1. Separate commands and queries at the use-case level, together
with job checkpoints, cover the known needs with less complexity.

### Layers without ports (application calls SQLAlchemy and FFmpeg directly)

Rejected. It would have removed the adaptation code, but use-case tests would
need a real database, binaries and models, and changing a provider would touch
business logic.

### Architecture tool (import-linter or another) from the start

Postponed. It would add a development dependency; the existing AST test covers
the most important case. It will be reassessed when the planned guard is
documented (dependency rule in [AGENTS.md](../../AGENTS.md)).

## Hexagonal boundaries: rules and current evidence (review 2026-09-30)

Mapping of layers to real code:

| Layer | Directory | May import |
| --- | --- | --- |
| Domain | `src/voz/domain/` | only the standard library and its own package |
| Application (use cases and ports) | `src/voz/application/`, `src/voz/application/ports/` | domain and the standard library |
| Infrastructure (outbound adapters) | `src/voz/infrastructure/` | application (ports), domain and concrete SDKs |
| Interfaces (inbound adapters) | `src/voz/interfaces/` | application, domain and transport frameworks |
| Composition root | `src/voz/bootstrap.py` | all layers; the only place that wires adapters |

Evidence per rule (the "Automated" column distinguishes a test that fails if
the rule is broken from a one-off check made during the review):

| Rule | Evidence | Automated |
| --- | --- | --- |
| `domain` does not import frameworks | `tests/unit/domain/test_entity_invariants.py::test_domain_does_not_import_framework_or_persistence_packages` walks the AST and bans `fastapi`, `pydantic` and `sqlalchemy`. A `grep` search on 2026-09-30 found no imports of `torch`, `faster_whisper`, `typer`, `uvicorn` or `voz.application` in `src/voz/domain`. | Partial: the banned list is short. |
| `application` does not import adapters or frameworks | `grep` on 2026-09-30 with no results for `fastapi`, `sqlalchemy`, `starlette`, `faster_whisper`, `typer`, `uvicorn`, `voz.infrastructure` and `voz.interfaces` in `src/voz/application`. The test `tests/unit/application/test_transcription_provider_registry.py::test_registry_has_no_domain_infrastructure_or_framework_imports` pins the import list of one module. | Partial: a single module. |
| Use cases depend on ports | `ImportMedia`, `NormalizeImportedMedia`, `PrepareInferenceAudio`, `CreateTranscriptionJob`, `JobRunner` and `RecoverableTranscription` receive `MediaStoragePort`, `MediaProbePort`, `MediaNormalizationPort`, repositories, `TranscriptionCheckpointStore` and `TranscriptionProvider` as fields or parameters. Application unit tests use in-memory doubles (`tests/unit/application/`). | Yes, indirectly: the tests need no SQL, FFmpeg or ASR. |
| Ports do not leak infrastructure details | `src/voz/application/ports/` contains no `Session`, tables or SQL expressions (`grep` with no results for `sqlalchemy`/`Session` in `src/voz/application`). | No |
| Routers only translate transport | Each router is a `create_*_router(...)` function that receives already-built use cases or repositories and translates typed errors to `{"detail": {"code", "message"}}`. Covered by `tests/integration/test_*_api.py`. | Yes, behavior; not the absence of logic. |
| Adapters are instantiated in the composition root | `Sqlite*Repository`, `FileSystemMediaStorage`, `FfprobeMediaProbe`, `FfmpegMediaNormalizer`, `FasterWhisperProvider` and `FileSystemModelStore` are built in `create_app()` and `create_local_asr_runtime()` (`src/voz/bootstrap.py`). Exception: `interfaces/cli/doctor.py` builds read-only probes. `tests/unit/test_asr_bootstrap.py` covers the ASR composition without downloads. | Partial |
| No host paths to the UI | The schema has no path columns (`src/voz/infrastructure/persistence/schema.py`; `test_schema_and_adapters_never_persist_host_paths` in `tests/unit/infrastructure/persistence/test_repositories.py`). Disk destinations are derived from UUIDs. Tests: `test_health_api.py` (no sensitive paths), `test_media_upload_api.py`, `test_media_stream_api.py::test_deleted_original_file_is_reported_missing_without_path`. | Yes |
| Long jobs with state, progress, cancellation and recovery | `TranscriptionJobState` with 12 states and validated transitions (`src/voz/domain/entities/transcription_job.py`); `JobRunner` with a thread, cooperative cancellation and `recover()` (`src/voz/application/job_runner.py`); `tests/integration/application/test_job_runner.py`. | Yes |
| Providers pass common contract tests | `tests/contract/test_transcription_provider.py` parametrizes a structural provider and `FasterWhisperProvider` with a fake engine. Details in [ADR-0005](0005-transcription-providers.md). | Yes |
| Works offline with installed models | See [ADR-0006](0006-local-first-privacy.md). | Partial |

### Actual implementation versus what is written above

Points where the code differs from the initial wording of this ADR, without
changing the decision:

- **"Asynchronous" pipeline**: jobs run in a single daemon thread
  (`JobRunner`, in-memory `queue.Queue`), not in coroutines or processes. The
  heavy work does not run in the event loop: routes that touch SQLite or disk
  are synchronous functions (`def`, which FastAPI runs in its threadpool) or
  use `run_in_threadpool`/`anyio.to_thread` (`media.py`, `media_stream.py`,
  `job_events.py`).
  Scaling to several workers or processes is **planned** (`ponytail:` in
  `job_runner.py`).
- **SSE**: the `GET /api/jobs/{id}/events` endpoint polls the repository about
  every 500 ms; there is no internal event bus
  (`src/voz/interfaces/api/job_events.py`). An in-process pub/sub is
  **planned** if polling stops being enough.
- **`DiarizationProvider` and `AlignmentProvider` contracts**: they do not exist
  yet. Only `TranscriptionProvider` is implemented. See ADR-0005.
- **Web UI**: the compiled bundle is served as static files from
  `src/voz/static` with `StaticFiles`; there is no separate process.

### Known boundary debt

- `interfaces/api/media_stream.py` receives the concrete
  `FileSystemMediaStorage` adapter to resolve the path that `FileResponse`
  serves. The path never reaches the browser, but a read port for originals
  would be more symmetric.
- There is no automatic guard that walks all of `src/voz/application` and
  `src/voz/domain` with a complete list of forbidden imports (frameworks,
  `voz.infrastructure`, `voz.interfaces`, provider SDKs). **Planned**: an AST
  test in the style of the existing domain test, without adding dependencies.

## Compliance rules

This decision is considered respected when:

- `domain` does not import framework or provider packages;
- use cases depend on ports and not on concrete SQL/FFmpeg/SDKs;
- routers contain no business rules;
- the UI does not receive absolute host paths;
- providers pass common contract tests;
- the process works offline with already-installed models;
- long jobs persist recoverable progress.

Changing these rules requires a new ADR that explicitly supersedes this
decision.
