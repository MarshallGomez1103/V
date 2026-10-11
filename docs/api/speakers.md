# Speakers — S6.09, S6.10, S6.11, S6.12 (wave 5b, 2026-09-30)

Local (`127.0.0.1`), no network or models: all these operations edit existing
rows and never rerun diarization. Errors use `{"detail": {"code", "message"}}`;
host paths and tracebacks are never returned. Common rules: [README.md](README.md).

## Speaker item

```json
{"id": "uuid", "name": "Ana", "color": "#4e79a7", "segment_count": 12,
 "talk_ms": 184200, "first_ms": 750}
```

`color` is lowercase `#rrggbb`. `segment_count` counts the segments that
currently point to the speaker. `talk_ms` is the sum of the duration of those
segments (talk time; the percentage is computed by the UI over the sum of all)
and `first_ms` is the start of their first segment (`null` and `0` without
segments), to jump to their first turn. Both follow manual segment edits. A
speaker "belongs" to a transcript if any of its segments or turns
(`speaker_turns`) belongs to it.

## `GET /api/transcripts/{transcript_id}/speakers`

→ `200 {"speakers": [item]}` in creation order (the order of first appearance in
the audio). `404 transcript_not_found`.

## `PATCH /api/speakers/{speaker_id}` (S6.09, S6.10)

Body: `{"name"?: str, "color"?: "#rrggbb"}`. The name is stored without leading or
trailing spaces (1–80 characters). At least one field is required. Name and color
are stored on the speaker, so they survive new diarization runs on the same
transcript (`AssignSpeakers` reuses the speaker).

| Status | Code | Meaning |
| --- | --- | --- |
| 200 | — | updated item |
| 404 | `speaker_not_found` | the speaker does not exist |
| 422 | `speaker_update_invalid` | empty name or one longer than 80 characters, a color that is not `#rrggbb`, or a body with no fields (a malformed body gives FastAPI's standard 422) |

## `POST /api/speakers/{speaker_id}/merge` (S6.11)

Body: `{"into": "<target speaker_id>"}` → `200 {"speaker": target_item}`.

In **one** SQLite transaction it reassigns all of the source's segments and turns
to the target and deletes the source. Texts, revisions and timings do not change.
The target keeps its name and color.

| Status | Code | Meaning |
| --- | --- | --- |
| 404 | `speaker_not_found` | the source does not exist |
| 409 | `speaker_merge_invalid` | target equal to the source, nonexistent, or sharing no transcript with the source |

## `PUT /api/segments/{segment_id}/speaker` (S6.12)

Body: `{"speaker_id": "uuid" | null}` → `200` segment item (same shape as in
[segments.md](segments.md)). It only changes `speaker_id`: it does not touch the
text, `edited` or `revision`. `null` leaves the segment without a speaker.

| Status | Code | Meaning |
| --- | --- | --- |
| 404 | `segment_not_found` | the segment does not exist |
| 409 | `segment_speaker_invalid` | the speaker does not exist or does not belong to the segment's transcript |

## Speakers from cloud providers (INTEGRITY-001)

When the ASR provider already labels each segment (`speaker`: ElevenLabs with
diarization, diarized OpenAI) and the job did **not** request local diarization,
the pipeline creates the speakers when persisting the transcript:

- One `Speaker` per label, named `Hablante 1..N` (a literal stored name, in
  Spanish) in order of first appearance, with the color from the fixed palette.
  They appear in `GET .../speakers` and in `segment_count` like any other
  speaker.
- The speaker id derives from the transcript and the label
  (`uuid5(transcript_id, "speaker:<label>")`): resuming the job reuses the same
  rows and keeps edited names and colors. No turns (`speaker_turns`) are created:
  the provider does not deliver them.
- If local diarization was requested, the local one wins and the cloud labels are
  ignored. Segments without a label stay without a speaker.
- If creating the speakers fails, the transcript is kept and the code is stored
  in the job selection's `diarization_error_code`.
- Limitation: ElevenLabs reuses labels (`speaker_0`) per long-audio chunk, so the
  same label in different chunks is merged into one speaker. OpenAI prefixes the
  label with the chunk (they are not merged).

## Notes

- There is no transaction shared with `AssignSpeakers` (see its `ponytail:`
  note): editing speakers while a diarization runs on the same transcript is not
  supported.
- Reassigning by hand does not create new speakers; you only choose among those
  of the transcript (`GET .../speakers`).
