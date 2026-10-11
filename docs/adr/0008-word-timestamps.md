# ADR-0008: Native word timestamps from Faster Whisper, without WhisperX

> Translated from Spanish on 2026-10-11 (V1-08b). VOZ is the former name of V (ADR-0009).

- Status: Accepted
- Date: 2026-09-30
- Owners: VOZ maintainers
- Scope: origin, model and persistence of word timings (S7.01, S7.03, S7.04,
  S7.08); S7.02 (evaluating WhisperX) **remains open and not evaluated**
- Related: [ADR-0004](0004-local-asr-and-recoverable-chunks.md) (chunks and
  checkpoints), [ADR-0005](0005-transcription-providers.md) (provider port),
  [ADR-0006](0006-local-first-privacy.md) (no implicit cloud)

## Context

The domain already has `Word` (`start_ms < end_ms`, inside the segment) and
SQLite already stores `words`, but ASR was invoked with
`word_timestamps=False`. Word timings are needed for reconciliation with
speakers (S6) and for highlighting and navigating by word. The master plan
(section 4.3) contemplates WhisperX (forced alignment with wav2vec2), which adds
torch, per-language models and a second inference pass.

## Decision

1. **Native.** The Faster Whisper adapter requests `word_timestamps=True`
   (cross-attention/DTW alignment that the engine already provides). **WhisperX
   is not installed** nor a dependency: zero new dependencies, zero extra
   models.
2. **Canonical types.** `TranscriptionSegment.words: tuple[TranscriptionWord, ...] = ()`
   with `TranscriptionWord(start_ms, end_ms, text, probability | None)`.
   `TranscriptionOptions.word_timestamps` (default `True`) controls it. The
   segment text remains the literal ASR output; words are only a timing hint.
3. **Same offset and ownership as the segment.** `globalize_chunk_result` adds
   `process_start_ms` to segment and words; `owned_chunk_segments` decides by the
   segment's midpoint and clips the words to the owned region (`clamp_words`).
   Words inherit the ownership of their segment: the overlap between chunks does
   not duplicate words.
4. **`clamp_words`** leaves the words ordered, non-overlapping, non-negative and
   within bounds; it discards those left with no duration (the domain requires
   `start_ms < end_ms`). Losing a word never changes the segment text.
5. **Checkpoints** serialize `words` in the segment JSON only when there are
   any; earlier checkpoints (without the key) are read as `words=()`. There is
   no schema migration.
6. **JobRunner** persists `Word` with id `uuid5(segment_id, "word:{i}")`. The
   segment and its words are inserted in a single transaction and already-stored
   segments are skipped, so resuming or repeating persistence is idempotent. It
   applies the same strip rule as the text: words that are empty after `strip()`
   are discarded.
7. **Fallback (S7.08).** If the word step fails in the engine (an exception that
   is neither cancellation nor invalid audio), the adapter retries the chunk once
   without words. A model or engine without words produces `words=()` and the
   job completes anyway. Checkpoints that already exist are not recomputed.
8. **API.** `GET /api/transcripts/{id}/segments` adds `words` to each segment
   (`segment_view`, shared with `PUT /api/segments/{id}`). An edited segment
   exposes `words: []` because the timing describes the ASR text, not the
   correction (the data is kept). See [docs/api/segments.md](../api/segments.md).
9. **Future aligner (S7.01).** `AlignmentProvider` in
   `application/ports/alignment.py` only fixes the seam
   (`align(audio, segments, language, cancellation) -> words per segment`). It
   has no implementation or registry: AGENTS.md forbids a plugin framework
   before two real providers. Today the words come from the ASR when it declares
   `ModelCapability.WORD_TIMESTAMPS`.

## Positive consequences

- Word timings with no dependencies, no downloads and no second model; it stays
  offline.
- Recoverable chunks, cancellation and idempotency are preserved: words travel
  inside the same checkpoints and segments.
- A word failure does not make the job fail.

## Costs and limits

- Native DTW is less precise than a dedicated forced alignment (it usually
  suffices for highlighting and speaker reconciliation, not for frame-accurate
  subtitling). We have not yet measured that precision with real audio.
- Requesting words costs extra inference time per chunk (not measured here).
- The word `probability` is stored in checkpoints, but the domain `Word` and the
  API do not expose it yet.
- Editing a segment's text does not readjust the timings; they are hidden.
- The `WORD_TIMESTAMPS` capability is announced by each catalog/runtime; the
  Faster Whisper adapter can already produce it, but the runtime probe does not
  declare it yet (pending from the owner of `infrastructure/asr/options.py`).

## Alternatives considered

- **WhisperX / forced alignment.** Higher precision, but torch, per-language
  wav2vec2 models and a second pass. **S7.02 remains open: it was not
  evaluated**; it is reopened if native precision proves insufficient with real
  audio.
- **Align afterwards with a separate process.** This is what `AlignmentProvider`
  reserves; it is not built until a second real provider exists.

## Current evidence

- `src/voz/application/ports/transcription.py`, `ports/alignment.py`,
  `chunked_transcription.py`, `job_runner.py`,
  `infrastructure/asr/faster_whisper.py`,
  `infrastructure/persistence/transcription_checkpoints.py`,
  `interfaces/api/segments.py`.
- Tests: `tests/unit/application/test_word_timestamps.py`,
  `tests/unit/infrastructure/asr/test_faster_whisper_words.py`,
  `tests/integration/application/test_job_runner.py` (words, resume without
  duplicating), `tests/integration/application/test_recoverable_transcription.py`
  (round-trip and old checkpoints), `tests/integration/test_segments_api.py`,
  `tests/integration/test_jobs_api.py`.
- The test with a real model (`test_faster_whisper_real_opt_in.py`) is opt-in and
  was not run in this pass.

## Verification

`uv run pytest -q`, `uv run ruff check`, `uv run pyright` over the listed files.
Precision and cost with real audio: **not verified**.
