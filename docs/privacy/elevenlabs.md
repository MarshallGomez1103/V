# Privacy: ElevenLabs Scribe (optional, cloud)

Status: **experimental**. The adapter has only been tested with a fake transport
(the real service has never been called), so it is not declared supported. It
follows [ADR-0006](../adr/0006-local-first-privacy.md): V is local by default and
this provider is only used by explicit decision.

## When audio leaves your machine

Only if both conditions hold at the same time:

1. An ElevenLabs key is configured.
2. You choose ElevenLabs Scribe for that specific job.

Having the key does **not** enable anything: without an explicit selection no
request is made. There is no automatic fallback: if a local model fails, V does
not retry with ElevenLabs. It is not recommended by default either.

## What is sent

One `POST https://api.elevenlabs.io/v1/speech-to-text` request (multipart) for
each audio span the job processes:

| Data | Detail |
| --- | --- |
| Audio | The span's normalized WAV (16 kHz mono PCM), with the fixed name `audio.wav`. Spans overlap by a few seconds, and that overlap is sent (and billed) twice. |
| `model_id` | `scribe_v1`. |
| `diarize` | `true` by default (separate speakers). |
| `timestamps_granularity` | `word`. |
| `tag_audio_events` | `false` (no tags such as "(laughter)" are inserted). |
| `language_code` | Only if you specify a language. |
| `keyterms` | Only if the project supplies key terms (max 100, 50 characters each). The per-project glossary model is S13.01; this adapter only receives the already-built list. If the chosen model does not support `keyterms`, the API may reject it: not verified live. |
| `xi-api-key` header | Your key, only in the HTTPS header. |

**Not sent**: the original's file name or path, the project name, previous
transcripts, edits, the database or any host path.

## What comes back and where it is stored

Text, per-word timings and speaker identifiers (`speaker_0`, ...). It is stored
locally like any other transcript; originals remain immutable and the raw
response is neither kept nor logged.

## Retention at ElevenLabs

It depends on their policy and your plan; V can neither verify nor control it.
Check the current policy: <https://elevenlabs.io/privacy> and the API
documentation: <https://elevenlabs.io/docs>. If you need zero retention or data
residency, confirm with ElevenLabs that your plan includes it before sending
sensitive material.

## The key

- It is read from `ELEVENLABS_API_KEY` (or `VOZ_ELEVENLABS_API_KEY`) and, if
  neither exists, from `$XDG_CONFIG_HOME/voz/secrets.toml` (mode `0600`).
- It is never stored in SQLite, never written to logs, errors, diagnostics or API
  responses, and the `repr` of the provider and of the request does not include it.
- **Delete it**: `DELETE /api/providers/elevenlabs/key` (removes the entry from
  the file), or delete the `elevenlabs` line from `secrets.toml`, and unset the
  environment variable if you use one. Also revoke the key in your ElevenLabs
  dashboard if you suspect exposure.

## Cost and limits

- `GET /api/providers/elevenlabs/estimate?media_asset_id=` estimates minutes and
  USD **before** anything is sent (see [providers](../api/providers.md)). The
  hourly price is a dated reference (2026-09-30), **not verified live**; your
  actual plan may differ.
- The per-file upload limit is configurable (`max_upload_bytes`, 3 GiB by default
  according to the public documentation as recalled on 2026-09-30, not verified
  live). The adapter does not split: the spans are defined by the job.
- The timeout grows with duration (300 s + the audio duration, max 1 h).
- An upload is never retried on its own (avoids double billing); 429/5xx/network
  failures are marked `retryable` and the job decides.
- It can be cancelled during upload; the progress of bytes sent is exposed by the
  `on_upload_progress` callback.
