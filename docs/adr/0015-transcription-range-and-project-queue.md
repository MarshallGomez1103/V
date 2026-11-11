# ADR-0015: Transcription range and per-project transcription queue

- Status: Accepted
- Date: 2026-11-11
- Owners: V maintainers
- Scope: transcribing only a chosen stretch of a recording, adding several
  recordings to one project, and transcribing a project's recordings one after
  another as a recoverable queue: semantics, storage, migration, HTTP contract
  and UI. Everything described here is **planned** until its evidence row says
  otherwise.
- Related: [ADR-0002](0002-sqlite-persistence.md) (SQLite, Alembic, XDG),
  [ADR-0003](0003-ffmpeg-ingestion.md) (immutable originals),
  [ADR-0004](0004-local-asr-and-recoverable-chunks.md) (recoverable chunks),
  [ADR-0006](0006-local-first-privacy.md) (no implicit cloud),
  [ADR-0007](0007-local-diarization-sherpa-onnx.md) (local diarization),
  [ADR-0012](0012-project-folders.md) (folders, Proposed)

## Context

- A person often needs only part of a recording (a class without the first
  minutes of chatter) and wants to transcribe many recordings of one course
  without starting each job by hand.
- Uploads are already copied into the data directory, hashed and made
  read-only before anything else happens
  (`src/voz/infrastructure/media_storage.py`, `FileSystemMediaStorage`); the
  temporary upload is always removed (`src/voz/interfaces/api/media.py`).
- A project can already hold many recordings (`media_assets.project_id`), but
  the import screen keeps only the first dropped file and always creates a new
  project (`apps/web/src/components/NewProjectCard.tsx`), and no route lists a
  project's recordings.
- Transcription runs in one global worker that drains a FIFO of jobs, fails one
  job without stopping the worker and re-enqueues every unfinished job on start
  (`src/voz/application/job_runner.py`, `JobRunner`).
- Chunks are planned over the normalized timeline and each chunk result is
  shifted by its processing start, so segment and word times are already
  absolute (`src/voz/application/chunked_transcription.py`,
  `plan_audio_chunks`, `globalize_chunk_result`). The inference audio can
  already return a bounded clip of the normalized file
  (`src/voz/infrastructure/inference_audio.py`, `_read_clip`).
- Diarization reads the whole normalized file today
  (`JobRunner._diarize`).

## Decision

### 1. The range

- A range is a half-open interval `[start_ms, end_ms)` in integer milliseconds
  on the timeline of the original recording. It is the existing
  `TranscriptionClip` value (`src/voz/application/ports/transcription.py`).
- Valid when `0 <= start_ms < end_ms <= duration_ms` and
  `end_ms - start_ms >= 1000`. `duration_ms` is the duration probed at import
  and stored on the media asset; originals are immutable, so it does not change
  afterwards. A recording without a probed duration cannot be trimmed.
- The range belongs to one job: it is part of the job's immutable selection
  snapshot. No range means the whole recording; every existing job is read
  that way. Nothing is written to the original and no trimmed file is created:
  the range is a reference over the original and its shared normalized
  derivative.
- If the normalized derivative turns out a few milliseconds shorter than the
  probed duration, the last chunk is clamped to the available frames; a range
  that starts beyond the derivative fails with the existing
  `inference_audio_invalid` code.

### 2. Transcribing only the range

- Chunks are planned over `[start_ms, end_ms)` instead of `[0, duration_ms)`.
  Processing bounds are clamped to the range, so the engine never receives audio
  outside it; ownership spans cover the range exactly once.
- Because each chunk result is already shifted by its processing start,
  segments and words keep the times of the original recording: a word spoken at
  12:03 of the file is stored at 12:03 even when the range starts at 10:00. The
  player, the waveform, the export formats and the live preview need no offset.
- Without a range the plan is identical to the previous one, so checkpoints of
  existing jobs stay valid. The range is part of the snapshot the checkpoints
  are validated against, so a resumed job keeps its plan.
- The whole recording is still normalized once and the derivative is reused by
  later jobs and by the waveform.

### 3. Speakers and words

- With a range, diarization reads the same clip and its turns are shifted by
  `start_ms` before they are stored, so speaker turns are also in original
  times and never fall outside the range. Recomputing speakers reuses the
  stored selection, so it keeps the range.
- Word timestamps come from the same chunk results and follow section 2.

### 4. Recordings of a project

- A project view lists every recording of a project and accepts several
  dropped files; each one is uploaded to that project through the existing
  import, so its copy lives in the data directory, outside the source checkout,
  and the dropped file is never modified.
- `GET /api/projects/{project_id}/recordings` uses the `Recording` shape that
  ADR-0012 proposes, without `folder_id`; folders add that field later.

### 5. Project transcription queue

- "Transcribe project" creates one ordinary transcription job per eligible
  recording, in import order (`created_at`, then id), all with the same options,
  inside one database transaction, plus a queue row that groups them with a
  position. Jobs are enqueued in position order.
- Eligible: a recording with a probed duration, no unfinished job and no
  completed job. The others are skipped and reported with a reason:
  `already_transcribed`, `job_active` or `duration_unknown`. If nothing is
  eligible, no queue is created.
- One unfinished queue per project at a time.
- Only local options: a queue cannot use a cloud provider.
- Order and concurrency: the single global worker runs one job at a time.
  Queues of different projects therefore run one after another, and a job
  started on its own while a queue is running waits behind the queue's jobs.
- Resume: on start, unfinished jobs are re-enqueued ordered by `created_at`,
  then queue position, then id; each job resumes from its own checkpoints.
  Finished items are not repeated.
- Isolated error: a failed item keeps its error code and the worker continues
  with the next one.
- Cancelling one item uses the existing job cancel; the queue continues.
  Cancelling the queue cancels its pending items first and then the running
  one.
- Item status is derived from its job: `QUEUED` is `pending`; the processing
  states and `CANCELLING` are `running`; `COMPLETED` is `done`; `FAILED` is
  `error`; `CANCELLED` is `cancelled`. The queue is `running` while any item is
  pending or running, otherwise `finished`. The queue has no state of its own.
- Recording ranges are not part of the queue: every item is the whole
  recording. A trimmed transcription is started from the single-recording
  screen.

### 6. What the person sees

- A trimmed job shows its stretch and what was left out, for example
  "00:10–05:00 of 12:00 (07:00 not transcribed)".
- A queue shows counts and progress: total, pending, running, done, with
  error, cancelled and skipped (by reason), plus one line per item with its
  status and progress. Nothing requires a manual review.

### 7. Storage and migration

- Migration `0011_transcription_clip_and_queue`:
  `transcription_job_selections` gains nullable `clip_start_ms` and
  `clip_end_ms`; new tables `transcription_queues` and
  `transcription_queue_items`. Existing rows are untouched: no range, no queue.
- The existing pre-migration backup applies
  (`src/voz/infrastructure/persistence/migrate.py`, `upgrade_to_head`).
  `downgrade()` drops the tables and the columns; it is for tests.
- Rollback: stop V, restore the `voz-0010_synthesis_request_hash-<timestamp>`
  backup, start the previous version. Ranges and queues created after the
  upgrade are lost; recordings, transcripts and files are not.
- The folder migration proposed in ADR-0012 becomes `0012_project_folders`.

### 8. HTTP contract

Documented in [docs/api/jobs.md](../api/jobs.md),
[docs/api/projects.md](../api/projects.md) and
[docs/api/transcription-queue.md](../api/transcription-queue.md).
New stable codes: `job_clip_invalid`, `job_clip_out_of_range`,
`job_clip_duration_unknown`, `transcription_queue_active`,
`transcription_queue_empty`, `transcription_queue_cloud_unsupported`,
`transcription_queue_not_found`, `transcription_queue_finished`.

### 9. Layers

- Domain: `TranscriptionQueue`, item status and skip reasons
  (`src/voz/domain/entities/transcription_queue.py`), no framework imports.
- Application: range validation in `CreateTranscriptionJob`; chunk planning
  with a range; `CreateTranscriptionQueue`, `GetTranscriptionQueue`,
  `CancelTranscriptionQueue`; `ListRecordings`. Ports only.
- Infrastructure: SQLite schema, migration, queue repository.
- Interfaces: thin routers; wiring in `src/voz/bootstrap.py`.

### 10. What is not done

No trimmed copies on disk, no several ranges per job, no range per queue item,
no cloud in queues, no parallel workers, no queue per folder, no reordering of
a running queue, no automatic retry of failed items.

## Positive consequences

- Two nullable columns and two small tables; existing data is read unchanged.
- Absolute times come from code that already exists; no offset logic is spread
  through export, player or preview.
- The queue reuses the job lifecycle, cancellation, checkpoints and recovery
  instead of adding a second state machine.

## Costs and limits

- A short range of a long recording still normalizes the whole file once.
  Ceiling: normalize only the range if that cost is measured as a problem.
- Diarizing a range holds the range's PCM in memory (about 115 MB per hour at
  16 kHz mono 16-bit); the whole-file path already holds the whole file.
- One global worker: queues of different projects do not overlap.
- The range rules (both ends or none, order) are enforced in code, not by a
  database CHECK, to avoid rebuilding an existing SQLite table.
- A queue item cannot be trimmed yet; adding an optional range per item needs
  no schema change because the range already lives in each job's selection.

## Alternatives considered

### Write a trimmed copy of the audio
Rejected: duplicates bytes, adds a second derivative per range and gives the
transcript a timeline that no longer matches the original.

### Store the range on the recording
Rejected for now: two sources for one job's range (recording and request)
would be ambiguous, and the queue does not need it.

### A queue runner that creates the next job when the previous one ends
Rejected: it would need its own recovery logic; creating all jobs up front
reuses the existing recovery.

### Reject the whole queue when one recording is not eligible
Rejected: the system decides, applies and reports what it skipped.

### Diarize the whole file and drop turns outside the range
Rejected: wasted work on long recordings for no gain.

## Current evidence (2026-11-11)

| Requirement | Code or test |
| --- | --- |
| Uploads copied read-only into the data directory | `src/voz/infrastructure/media_storage.py` (`import_original`) |
| Absolute times from chunk offsets | `src/voz/application/chunked_transcription.py` (`globalize_chunk_result`) |
| Bounded clip of the normalized audio | `src/voz/infrastructure/inference_audio.py` (`_read_clip`) |
| One global worker, recovery on start | `src/voz/application/job_runner.py` (`JobRunner`) |
| Range, queue, recordings route, UI | **planned** |

## Verification

This decision is respected when:

- a job with a range stores every segment, word and speaker turn inside
  `[start_ms, end_ms)` in original times, and the engine receives no audio
  outside the range;
- a job without a range produces the same chunk plan as before;
- the migration upgrades and downgrades a populated database and existing
  selections read as "no range";
- ten recordings in a queue run in order, one at a time; a failing item does
  not stop the others; after a restart the queue resumes in order without
  repeating finished items, also when every job has the same `created_at`;
- an upload into a project leaves its copy under the data directory and the
  dropped file unchanged, and no file appears in the source checkout;
- the range controls work with the keyboard, in English and Spanish.

**Review criterion:** if ranges must be edited after a job starts, several
workers are needed, or queues must reach cloud providers, replace this ADR.
