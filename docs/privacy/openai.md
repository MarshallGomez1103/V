# Privacy: OpenAI (optional, cloud)

Status: **experimental**. The adapter has only been tested with a fake transport
(the real service has never been called), so it is not declared supported. It
follows [ADR-0006](../adr/0006-local-first-privacy.md): V is local by default and
this provider is only used by explicit decision. The OpenAI API key is separate
from ChatGPT/Codex: it is billed as API usage, not as a subscription.

## When audio leaves your machine

Only if both conditions hold at the same time:

1. An OpenAI key is configured.
2. You choose an `openai` model (Whisper or GPT-4o Transcribe Diarize) for that
   specific job.

Having the key does **not** enable anything: creating the provider, listing
options or registering the key make no request. There is no automatic fallback:
if a local model fails, V does not retry with OpenAI. Cloud options appear marked
`cloud: true` in `GET /api/transcription-options` and are never recommended.

## What is sent

One `POST https://api.openai.com/v1/audio/transcriptions` request (multipart) for
each audio span:

| Data | Detail |
| --- | --- |
| Audio | The span's normalized WAV, with the fixed name `audio.wav`. If it exceeds the upload limit (25 MB by default, read as 25,000,000 bytes) it is split into WAV subclips with a 2 s overlap; that overlap is sent (and billed) twice. |
| `model` | `whisper-1` or `gpt-4o-transcribe-diarize`. |
| `response_format` | `verbose_json` (Whisper) or `diarized_json` (diarized). |
| `timestamp_granularities[]` | `segment` (Whisper only). |
| `chunking_strategy` | `auto` (diarized only; the API requires it for long audio). |
| `language` | Only if you specify a language. |
| `Authorization` header | Your key, only in the HTTPS header. |

**Not sent**: the original's file name or path, the project name, previous
transcripts, edits, the database or any host path.

## What comes back and where it is stored

Text and per-segment timings and, with the diarized model, an opaque speaker
label. It is stored locally like any other transcript; originals remain immutable
and the raw response is neither kept nor logged. If the audio was split, speaker
labels are prefixed with the span number (`1:A`, `2:A`): OpenAI does not
guarantee that `A` is the same person across requests, and V does not assume it.

## Retention at OpenAI

It depends on OpenAI's current policy and your organization; V can neither verify
nor control it. See <https://openai.com/policies/privacy-policy> and, for data
sent through the API, <https://platform.openai.com/docs/guides/your-data>. If you
need zero retention, confirm with OpenAI that your organization has it enabled
before sending sensitive material.

## Limits, retries and cost

- Limits and prices are dated constants (`LIMITS_DATE`) taken from the public
  documentation: **not verified live**. Sources:
  <https://platform.openai.com/docs/guides/speech-to-text> and
  <https://platform.openai.com/pricing>. The diarized model's price is an
  assumption equal to that of `gpt-4o-transcribe`.
- Requests are retried with exponential backoff and jitter only on 429, 5xx and
  timeouts (up to 4 attempts; `Retry-After` is honored). 4xx authentication or
  validation errors are never retried.
- `GET /api/providers/openai/estimate?media_asset_id=...` estimates minutes and
  USD before anything is sent ([contract](../api/providers.md)). It is an
  estimate: it does not include subclip overlap or price changes.

## The key

- It is read from `VOZ_OPENAI_API_KEY`, then `OPENAI_API_KEY` and, if neither
  exists, from `$XDG_CONFIG_HOME/voz/secrets.toml` (mode `0600`; if the mode is
  more open, or the file is a symlink, V rejects it with `secrets_file_insecure`).
- It is never stored in SQLite, never written to logs, errors, diagnostics or API
  responses, and the `repr` of the provider, the request and the secrets manager
  does not include it.
- **Delete it**: `DELETE /api/providers/openai/key` (removes the entry from the
  file), or delete the `openai` line from `secrets.toml`. If the key comes from an
  environment variable, remove it from your environment: V cannot delete it.
  Without a key, the OpenAI option stops being available. Also revoke the key in
  the OpenAI dashboard if you suspect it was exposed.
