# ADR-0002: SQLite with explicit mapping and Alembic migrations

> Translated from Spanish on 2026-10-11 (V1-08b). VOZ is the former name of V (ADR-0009).

- Status: Accepted
- Date: 2026-09-02
- Owners: VOZ maintainers
- Scope: initial local persistence: SQLite, migrations and the XDG filesystem layout
- Last review: 2026-09-30 (S16.13; fixes the file name and adds the filesystem
  layout)
- Diagrams: [containers](../architecture/02-contenedores.md)

## Context

VOZ needs projects, media, transcriptions, speakers and jobs to survive the
application being closed. The product runs for one person on a single machine
and does not need a database server. At the same time, the domain must not
depend on SQLAlchemy nor adopt table details as business rules.

Long jobs also require incremental writes and concurrent reads from the UI.
Schema evolution must be reproducible and cannot depend on implicitly creating
tables at every startup.

## Decision

The first persistent implementation will use SQLite through SQLAlchemy 2, with
versioned Alembic migrations and `journal_mode=WAL` enabled on every adapter
connection.

- The default file is `~/.local/share/voz/voz.sqlite3`
  (`DATABASE_FILENAME` in `src/voz/bootstrap.py`), resolved by the existing XDG
  module. The original wording of this ADR said `voz.db`; the code never used
  that name.
- Repository contracts will live in `application/ports` and will work with
  domain entities.
- Tables, metadata and row-to-entity conversion will live exclusively in
  `infrastructure/persistence`.
- Domain entities will not be ORM models and will not import SQLAlchemy.
- The initial migration will be the authoritative source of the distributed
  schema.
- Tests may create a temporary SQLite engine without writing data into the
  checkout or into the real XDG directories.
- Each repository operation has an explicit transactional boundary (each method
  opens `engine.begin()` or `engine.connect()`). A future unit of work may
  coordinate several operations if a use case that needs it appears. Today the
  only atomic multi-table write is the chunk commit (segments, checkpoint and
  job) in `SqliteTranscriptionCheckpointStore`
  ([ADR-0004](0004-local-asr-and-recoverable-chunks.md)).
- Each connection enables `foreign_keys=ON`, `journal_mode=WAL` and
  `busy_timeout` (5,000 ms by default); `create_sqlite_engine` requires an
  absolute path and has no default value tied to the checkout or the working
  directory.
- The migration is applied in the application lifespan with `upgrade_to_head`
  (`src/voz/infrastructure/persistence/migrate.py`), never at module import
  time, and it is idempotent. The scripts live in `migrations/versions/`
  (checkout) or inside the wheel (`pyproject.toml`, `force-include`).

## Filesystem and XDG

The database does not contain the media: it stores identity, hash, size,
duration, type and display name. The bytes live on the filesystem under XDG
directories resolved by `resolve_voz_paths`
(`src/voz/infrastructure/paths.py`), which ignores empty or relative `XDG_*`
variables.

| Location (without `XDG_*` variables) | Contents | Written by |
| --- | --- | --- |
| `~/.local/share/voz/voz.sqlite3` (+ `-wal`, `-shm`) | Database | `create_sqlite_engine` |
| `~/.local/share/voz/projects/<project_uuid>/originals/<media_uuid>.original` | Immutable original, read-only permissions | `FileSystemMediaStorage` |
| `~/.local/share/voz/projects/<project_uuid>/derivatives/<media_uuid>.inference.wav` | Mono 16 kHz PCM derivative | `FfmpegMediaNormalizer` |
| `~/.local/share/voz/models/` | Installed models with a manifest | `FileSystemModelStore` |
| `~/.cache/voz/uploads/` | Staging for HTTP uploads, deleted on every path | `interfaces/api/media.py` |
| `~/.cache/voz/downloads/` | Model download metadata | `FileSystemModelStore` |
| `~/.config/voz/`, `~/.local/state/voz/` | Resolved and checked by `voz doctor`; the code does not write to them yet | Nobody |

Rules:

- Nothing at runtime is written inside the checkout; tests use `tmp_path`.
- No disk path is stored in SQLite or sent to the browser: destinations are
  derived from UUIDs (`original_path_for`, `FfmpegMediaNormalizer`).
  `test_schema_and_adapters_never_persist_host_paths` checks it.
- There is no transaction spanning SQLite and the filesystem. Consistency is
  achieved by ordering the operations and compensating: `ImportMedia` publishes
  the original, persists the row and, if the row fails, discards the original;
  if the outcome is ambiguous, it reconciles before deleting
  ([ADR-0003](0003-ffmpeg-ingestion.md)).
- Originals are immutable; every derivative is written to another directory.

**Planned, not implemented:** `projects/<id>/chunks|exports|artifacts`,
`~/.cache/voz/waveforms|temp`, `~/.config/voz/config.toml`, database backup or
export, and a retention/deletion policy for projects.

## Positive consequences

- There is no external service to install or administer.
- WAL lets local reads continue while short writes are being committed.
- The domain can be tested without a database.
- Adapters can be replaced without changing the use cases.
- Alembic leaves an auditable path for evolving the schema.

## Costs and limits

- SQLite remains single-machine storage, not remote multi-user storage.
- There is an explicit conversion between rows and entities.
- Synchronous operations must not run in the event loop during heavy jobs; the
  application layer will have to send them to a worker where applicable.
- WAL creates auxiliary `-wal` and `-shm` files, which are runtime data and do
  not belong in Git.

## Alternatives considered

### Postgres

Rejected for the first version. It adds installation, credentials and an
external process without adding value for the single-user local case.

### ORM inside the domain

Rejected. It would couple core invariants and tests to the SQLAlchemy
lifecycle and make replacing persistence harder.

### Storing the media as BLOBs inside SQLite

Rejected. Recordings weigh gigabytes; the database file and its WAL would grow
without control, and FFmpeg and the player need file descriptors. The SHA-256
hash is stored as the content identity.

### Storing absolute paths in the database

Rejected. It ties the database to the host layout, makes leaks toward the API
easier and breaks when the data directory is moved. Destinations are derived
from UUIDs.

### Placing the database in the checkout or the working directory

Rejected. It would mix private data with code and with Git; it contradicts the
XDG rule in [AGENTS.md](../../AGENTS.md).

### Creating tables automatically without migrations

Rejected as a distribution mechanism. It can be useful in test fixtures, but it
does not record how an existing database evolves.

## Current evidence (2026-09-30)

| Requirement | Test or code |
| --- | --- |
| Per-connection pragmas and WAL reopening | `tests/integration/persistence/test_database.py` |
| Migrations equivalent to the metadata and safe downgrade | `tests/integration/persistence/test_migrations.py` |
| Idempotent migration at startup | `tests/integration/persistence/test_runtime_migrate.py` |
| Repositories rebuild entities and survive reopening the engine | `tests/integration/persistence/test_sqlite_repositories.py`, `tests/unit/infrastructure/persistence/test_repositories.py` |
| Reproducible job selection in SQLite | `tests/integration/persistence/test_sqlite_job_selections.py` |
| No host paths in the schema | `test_schema_and_adapters_never_persist_host_paths` |
| XDG resolution with absolute overrides and fallback | `tests/unit/test_xdg_paths.py` |
| Import with filesystem/SQLite compensation | `tests/integration/application/test_import_media_sqlite.py`, `tests/unit/application/test_import_media.py` |
| Domain without SQLAlchemy | `tests/unit/domain/test_entity_invariants.py` |

Current schema (`schema.py`): `projects`, `media_assets`, `transcripts`,
`segments`, `words`, `speakers`, `speaker_turns`, `transcription_jobs`,
`transcription_checkpoints`, `transcription_job_selections`.

## Verification

The decision is considered implemented when:

- no module under `domain` imports SQLAlchemy;
- the ports do not expose `Session`, tables or SQL expressions;
- the initial migration creates every table of Section 2;
- a new connection reports `journal_mode=wal` when the file allows it;
- repositories rebuild equivalent entities after closing and opening another
  engine on the same file;
- tests use temporary paths and do not create `voz.sqlite3` in the repository;
- no host path is persisted or returned over HTTP;
- runtime data is only written under the resolved XDG directories.
