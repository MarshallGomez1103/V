# Project transcription queue

"Transcribe project" creates one ordinary [transcription job](jobs.md) for every
recording of a project that can be transcribed, in import order, all with the
same options. The single worker runs them one after another. The queue is not a
second state machine: it only groups the jobs and remembers their order, so
cancellation, checkpoints, progress and recovery after a restart are exactly
those of a single job. Errors have the shape `{"detail": {"code", "message"}}`;
no host paths. Common rules: [README.md](README.md). Design:
[ADR-0015](../adr/0015-transcription-range-and-project-queue.md).

| Method and path | Request | Response |
| --- | --- | --- |
| `POST /api/projects/{project_id}/transcription-queue` | `{"option_id", "language"?, "diarization"?, "profile"?, "prompt"?}` | 201 `Queue`; 404 `project_not_found`, `option_unknown`; 409 `transcription_queue_active`, `transcription_queue_empty` (with `skipped`), `option_not_startable`, `insufficient_vram`, `insufficient_ram`, `diarization_unavailable`, `diarization_models_missing`; 422 `transcription_queue_cloud_unsupported`, `diarization_options_invalid`, `quality_profile_unknown`, `job_prompt_invalid`, `job_options_unsupported` |
| `GET /api/projects/{project_id}/transcription-queue` | — | 200 `{"queue": Queue \| null}` (the most recent one); 404 `project_not_found` |
| `POST /api/transcription-queues/{queue_id}/cancel` | — | 202 `Queue`; 404 `transcription_queue_not_found`; 409 `transcription_queue_finished` |

The request body has the same options, with the same meaning and validation, as
`POST /api/jobs` ([jobs.md](jobs.md)), without `project_id`, `media_asset_id`,
`clip` or `cloud_consent`. Every item is the whole recording.

```json
{
  "id": "uuid",
  "project_id": "uuid",
  "created_at": "2026-11-11T12:00:00+00:00",
  "state": "running",
  "progress": 0.35,
  "counts": {"total": 10, "pending": 5, "running": 1, "done": 3, "error": 1, "cancelled": 0, "skipped": 2},
  "items": [
    {
      "position": 0,
      "media_asset_id": "uuid",
      "filename": "class-1.mp3",
      "job_id": "uuid",
      "status": "done",
      "job_state": "COMPLETED",
      "progress": 1.0,
      "error_code": null,
      "transcript_id": "uuid"
    }
  ],
  "skipped": [
    {"media_asset_id": "uuid", "filename": "class-0.mp3", "reason": "already_transcribed"}
  ]
}
```

## Which recordings enter

A recording enters when it has a probed duration, no unfinished job and no
completed job. A recording whose jobs all failed or were cancelled enters again.
The others are skipped, never silently: each is listed in `skipped` with one
reason, checked in this order:

1. `already_transcribed`: it has a completed job.
2. `job_active`: it has a job that has not finished (including `CANCELLING`).
3. `duration_unknown`: the probe did not report a duration.

When nothing enters, no queue is created: 409 `transcription_queue_empty`, and
the `detail` carries `skipped` with the same shape. Nothing requires a manual
review: the system decides, applies and reports counts.

## Rules

- **Atomic.** The queue row, every job, every selection snapshot and every
  position are written in one transaction. A failure leaves nothing behind.
- **One unfinished queue per project.** While any item of the project's latest
  queue is pending or running, a new request answers 409
  `transcription_queue_active`.
- **Local only.** A cloud option is refused with 422
  `transcription_queue_cloud_unsupported` and nothing is created; consent for a
  cloud provider covers one run and a queue cannot ask for it. Use `POST /api/jobs`
  for a cloud recording.
- **Order.** `position` is zero-based, in import order (`created_at`, then id).
  The jobs are enqueued in that order. There is one worker for the whole
  application, so queues of different projects run one after another, and a job
  started on its own while a queue runs waits behind the queue's jobs.
- **Isolated errors.** A failed item keeps its `error_code` and the worker goes
  on with the next one. Failed items are not retried automatically.
- **Restart.** Unfinished jobs are re-enqueued ordered by creation time, then
  queue position, then id; each resumes from its own checkpoints and finished
  items are not repeated.

## State, status and progress

The queue has no state of its own; everything is read off its jobs.

| `job_state` | item `status` |
| --- | --- |
| `QUEUED` | `pending` |
| `PROBING`, `PREPROCESSING`, `TRANSCRIBING`, `ALIGNING`, `DIARIZING`, `MERGING`, `PERSISTING`, `CANCELLING` | `running` |
| `COMPLETED` | `done` |
| `FAILED` | `error` |
| `CANCELLED` | `cancelled` |

- `state` is `running` while any item is `pending` or `running`, otherwise
  `finished`. A queue with errors or cancellations is `finished` once nothing is
  left to run.
- `counts.total` is the number of items (skipped recordings are not items);
  `counts.skipped` is the length of `skipped`.
- `progress` is `(done + error + cancelled + the sum of progress of the running
  items) / total`, from 0 to 1.
- `transcript_id` is `null` until the item's transcript exists, as in
  [jobs.md](jobs.md).

## Cancelling

- One item: `POST /api/jobs/{job_id}/cancel` ([jobs.md](jobs.md)); the queue goes
  on with the next item.
- The whole queue: `POST /api/transcription-queues/{queue_id}/cancel` cancels the
  pending items first and then the running one, so the worker cannot start the
  next item in between. It answers 202 with the queue as it is at that moment;
  the running item ends `CANCELLED` when the worker reaches its next checkpoint,
  and the queue is `finished` from then on. Items that finished meanwhile keep
  their status. A queue that already finished answers 409
  `transcription_queue_finished`.

## Storage

Tables `transcription_queues` and `transcription_queue_items` (migration
`0011_transcription_clip_and_queue`). Deleting the project deletes its queues.
Jobs of a queue are ordinary rows of `transcription_jobs`.
