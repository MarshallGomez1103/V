# Segment editing — S5.12 (wave 3, 2026-09-30)

Local (`127.0.0.1`), no network or providers. Errors use
`{"detail": {"code", "message"}}`; host paths and tracebacks are never returned.
Common rules: [README.md](README.md).

## Segment item (contract shared with the frontend)

It has the same shape in `GET /api/transcripts/{transcript_id}/segments`
(`{"segments": [item]}`) and in the edit response:

```json
{
  "id": "uuid", "start_ms": 0, "end_ms": 250, "text": "Hola, mundo.",
  "edited": true, "revision": 1, "speaker_id": "uuid | null",
  "quality": {"flags": ["low_confidence"], "avg_logprob": -1.3},
  "words": [{"start_ms": 0, "end_ms": 120, "text": "Hola,", "speaker_id": "uuid | null"}]
}
```

`edited` is `false` and `revision` is `0` until the first edit; every successful
edit adds 1 to `revision`. `speaker_id` is `null` if the segment has no speaker
assigned.

`words` (S7.04) are the ASR word timings inside the segment: ordered,
non-overlapping, in milliseconds, with `start_ms < end_ms` inside the segment's
`[start_ms, end_ms]`; `text` has no leading or trailing spaces. It is `[]` when
the model delivered no words (fallback S7.08: the job completes anyway, just
without word timing) and **always `[]` if the segment is edited
(`edited: true`)**: the timings describe the original ASR text, not the corrected
one, so they are not exposed (they stay stored). Each word's probability is kept
in the checkpoints but not exposed.

`words[].speaker_id` (S7.05) is the speaker of the word: the one of the acoustic
turn that contains its midpoint (`start <= (start_ms+end_ms)/2 < end`; with
overlapping turns the one that starts earlier wins); if no turn covers it, it
inherits the segment's `speaker_id` (which may be `null`). It is computed on the
fly in the view (`application/word_speakers.py`) from the transcript's speaker
turns, with no new column on `words`: there is no persistence to migrate or keep
idempotent. `GET /api/transcripts/{id}/segments` passes the turns to
`segment_view`; the edit response (`PUT /api/segments/{id}`) does not, so there
every word inherits the segment's speaker.

## Segment quality (S13.04, S13.05, S13.12)

`quality.flags` are **non-destructive** hints computed when the transcript is
persisted (`application/quality_flags.py`, a pure function) from the metrics the
engine reports (today only faster-whisper; whisper.cpp and the cloud providers do
not provide them, so their segments come out with no flags except those that need
no metrics). `quality.avg_logprob` is `null` if the engine did not provide it. The
flags have a stable order and stable codes:

| Flag | When |
| --- | --- |
| `repetition` | `compression_ratio > 2.4`, or an n-gram (1 to 4 words) repeated consecutively: a word 5 or more times, a phrase 3 or more |
| `silence_hallucination` | `no_speech_prob > 0.6` and `avg_logprob < -1.0`; or a typical hallucination phrase ("Thank you.", "Gracias por ver el video", "Suscríbete"...) with `no_speech_prob > 0.3` or outside the audio bounds |
| `out_of_bounds` | the engine returned a span beyond the audio it received (500 ms tolerance); the span is clipped when stored, but flagged |
| `low_confidence` | `avg_logprob < -1.0` (Whisper's threshold) |

Real example: Whisper on a tone with no speech returned `" Thank you."` with
`end = 29.98 s` on a 0.25 s clip: it is flagged `out_of_bounds` and
`silence_hallucination`.

**No post-processing rewrites text (S13.12).** `text` is the literal ASR output
(without leading or trailing spaces) until the user edits it; flags are stored
separately (column `segments.quality_json`) and never change, delete or "correct"
text. User edits are the only way to change what a transcript says, and they keep
the literal in `original_text`. Editing a segment neither recalculates nor deletes
its flags. The computation is idempotent: resuming a job after a failure only adds
the missing segments.

Review flow (S13.06): `ReviewQueue` (frontend) lists segments with flags, filters
by type and lets the user mark them as reviewed. That state is local to the
session (not persisted; reloading the page resets it).

## `PUT /api/segments/{segment_id}`

Body: `{"text": str, "revision": int}`. `revision` is the one the client loaded
(optimistic concurrency). The server stores `text` without leading or trailing
spaces.

| Status | Code | Meaning |
| --- | --- | --- |
| 200 | — | updated segment item (`edited: true`, `revision + 1`) |
| 404 | `segment_not_found` | the segment does not exist |
| 409 | `segment_revision_conflict` | the revision sent is not the stored one; `detail.current` carries the current item |
| 422 | `segment_text_invalid` | text empty after stripping spaces (a malformed body also gives FastAPI's standard 422) |

### Rules

- **Literal text preserved.** On the first edit the literal ASR text moves to
  `original_text` (internal column, not exposed in the item); later edits do not
  overwrite it. A literal transcript is never silently replaced.
- **Atomicity.** The write is `UPDATE segments SET … WHERE id = ? AND
  revision = ?`; if another tab edited between the read and the write, the result
  is 409 (with the current state), not a silent loss.
- Word timings (`words`) are not deleted when the segment text is edited, but the
  response hides them (`words: []`) from the first edit on. Saving text identical
  to the current one also counts as an edit.

## Persistence

Migration `0004_segment_editing`: columns on `segments` `speaker_id` (FK
`speakers.id`, `ON DELETE SET NULL`), `edited` (bool, default false), `revision`
(int, default 0) and `original_text` (nullable). Existing segments stay unedited.
Downgrade drops the columns (edits and speaker assignments are lost) but keeps
segments and words.

Migration `0006_segment_quality`: column `quality_json` (Text, nullable) on
`segments`, using `ALTER TABLE ADD COLUMN` (without recreating the table, so as
not to drag `words` along as happened in 0004). It holds `{"flags": [...],
"avg_logprob": x}` or `NULL` if there is nothing to flag; existing segments have
no flags. Downgrade drops the column (hints can be recomputed) and keeps text,
edits and words. Damaged JSON is read as "no hints", never as an error.
