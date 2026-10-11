# Library, media info, rename and delete projects — plan v3, Slice A

Local (`127.0.0.1`). Errors have the shape `{"detail": {"code", "message"}}`; no
host paths. Common rules: [README.md](README.md). The library is the home screen:
one row per project.

## `GET /api/library` (CP-A1)

→ `200 {"items": [item]}` ordered by **most recent activity** first
(`max(project creation, last update of its latest job)`; the id breaks ties). One
query per table, no N+1.

```json
{
  "project_id": "uuid",
  "name": "Physics class",
  "created_at": "2026-10-03T01:17:42+00:00",
  "updated_at": "2026-10-03T01:37:13+00:00",
  "media": {
    "media_asset_id": "uuid",
    "filename": "clase.m4a",
    "media_type": "audio/aac",
    "duration_ms": 6464073
  },
  "latest_job": {
    "id": "uuid",
    "state": "COMPLETED",
    "transcript_id": "uuid",
    "model_id": "turbo",
    "progress": 1.0,
    "error_code": null,
    "created_at": "2026-10-03T01:18:33+00:00"
  },
  "speaker_count": 11,
  "segment_count": 1312
}
```

- `updated_at` is the activity date used for ordering.
- `media`: the recording of the latest job; if the project has no job, the first
  uploaded recording. **`null` if the project never received a recording** (a
  created project whose upload failed): the UI must tolerate it. `filename` is
  the original name (`display_name`); `media_type` is the type detected on import
  and, if probing did not recognize it, the one suggested by the file extension
  (`mimetypes`, only as a hint); it is `null` if there is none.
- `latest_job`: the project's most recent job (`created_at`, id); `null` without
  jobs. `transcript_id` exists only once the transcript row is stored (from the
  end of ASR, before the speakers); `model_id` is the model of the job's
  selection. `state` ∈ job states (`QUEUED` … `COMPLETED`, `FAILED`,
  `CANCELLING`, `CANCELLED`).
- `speaker_count` and `segment_count` are those **of the latest job's
  transcript** (`0` if there is no transcript yet). `speaker_count` counts only
  speakers with **at least one segment** (a speaker that appears only in turns,
  with no segment, does not count).

## `GET /api/media/{media_asset_id}`

Path-free recording record, to reopen a job by URL without guessing anything:

```json
{"media_asset_id": "uuid", "project_id": "uuid", "filename": "clase.m4a",
 "media_type": "audio/aac", "duration_ms": 6464073, "sha256": "…", "size_bytes": 81037665}
```

`404 media_asset_not_found`. `media_type` follows the same rule as the library.

## `GET /api/media/{media_asset_id}/original`

Streams the immutable original inline for the browser player. It serves
`Range` requests (`Accept-Ranges: bytes`) and sends `Cache-Control: private,
max-age=3600`; the `Content-Type` is the stored `media_type`, or
`application/octet-stream` if there is none. There is no `Content-Disposition`
and no host path in the response. 404 `media_asset_not_found` if the asset does
not exist; 404 `media_file_missing` if the row exists but the file is no longer
on disk.

## `PATCH /api/projects/{project_id}` (CP-A2)

Body `{"name": str}`. Same validation as on creation: it is stripped and must be
1 to 200 characters with no control characters. → `200` the project
(`{"id","name","created_at"}`).

| Status | Code | Meaning |
| --- | --- | --- |
| 404 | `project_not_found` | the project does not exist (evaluated before the name) |
| 422 | `project_name_invalid` | empty, whitespace only, > 200 or with control characters; nothing is saved |

## `DELETE /api/projects/{project_id}` (CP-A2)

Requires the header `X-VOZ-Action: delete-project` (like the server shutdown: a
page from another origin cannot send it without a preflight, which V never
allows). → `204` with no body.

It deletes **everything** that belongs to the project:

- rows, in a single statement with `ON DELETE CASCADE`: jobs, selections,
  checkpoints, transcripts, segments, words, speakers, turns, recordings
  (`media_assets`) and glossary;
- files: the `projects/<project_id>/` folder in V's data folder (read-only
  originals and derivatives). It uses the primitives of
  `infrastructure/safe_fs.py` (`remove_directory_tree`): a chain of directories
  without following links, internal symlinks are removed as links (never their
  target) and on Windows the read-only attribute is cleared.

Order: **files first, then rows**. If the files cannot be deleted the project
stays intact and can be retried (file deletion is idempotent).

| Status | Code | Meaning |
| --- | --- | --- |
| 403 | `project_delete_forbidden` | the header `X-VOZ-Action: delete-project` is missing |
| 404 | `project_not_found` | the project does not exist |
| 409 | `project_busy` | some job of the project is not terminal (`QUEUED` … `PERSISTING`, `CANCELLING`); cancel it and wait |
| 500 | `project_delete_failed` | the files could not be deleted; nothing was deleted from the database |

The model cache and the Buzz cache are never touched (they do not belong to the
project). The small waveform cache (`cache/waveforms/`) is left in place: it is
content-addressed and may be shared between projects.
