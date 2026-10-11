# Cloud providers: keys and cost estimate (S11.01, S11.08)

Loopback only (the server listens on `127.0.0.1` by default). No response ever
returns a key. Errors use `{"detail": {"code", "message"}}`. Common rules:
[README.md](README.md). OpenAI privacy: [docs/privacy/openai.md](../privacy/openai.md).

## `GET /api/providers`

```json
[{"id": "openai", "label": "OpenAI", "privacy_url": "https://openai.com/policies/privacy-policy", "configured": false, "cloud": true}]
```

The backend is the source of truth for the list: the UI shows exactly these
providers (in this order) and knows no ids or proper names. `label` is the display
name and `privacy_url` (or `null`) the link to the provider's privacy policy; the
composition root takes them from `infrastructure/cloud/provider_info.py` and
passes them to the router as `CloudProviderInfo`. A new provider is declared only
there.

`configured` is true if there is a key in the environment (`VOZ_<ID>_API_KEY` or
`<ID>_API_KEY`) or in `$XDG_CONFIG_HOME/voz/secrets.toml`. An insecure or corrupt
secrets file counts as not configured. Configuring a provider does **not** enable
it: only a job that explicitly selects it sends audio.

## `PUT /api/providers/{id}/key`

Body `{"key": "..."}`. Answers `204` with no body (it never echoes). It writes the
file atomically with mode `0600`; nothing goes to SQLite or to logs.

| Status | `detail.code` | Cause |
| --- | --- | --- |
| 404 | `provider_not_found` | Unknown provider. |
| 422 | `secrets_key_invalid` | The key must be 1–512 printable ASCII characters without spaces. |
| 409 | `secrets_file_insecure` | `secrets.toml` is not a regular file with mode `0600`. |
| 409 | `secrets_file_invalid` | `secrets.toml` could not be read. |
| 500 | `secrets_write_failed` | It could not be written. |

If an environment variable exists, it takes priority over the file.

## `DELETE /api/providers/{id}/key`

Answers `204` (idempotent). It removes the entry from the file; it cannot delete
environment variables. Same 404/409/500 errors.

## `GET /api/providers/{id}/estimate?media_asset_id=<uuid>[&model=<id>]`

Estimates without sending anything. Default `model`: `whisper-1` for OpenAI.

```json
{"minutes": 5.0, "usd": 0.03, "price_source": "https://platform.openai.com/pricing (no verificado en vivo)", "price_date": "2026-09-30"}
```

`price_source` is returned verbatim from the code (currently with a Spanish
suffix, as shown). Minutes and USD are rounded up. Errors: 404 `provider_not_found` (also when no
price is known for that provider and model), 404 `media_not_found` (the media
asset does not exist), 409 `media_duration_unknown`. The price is a dated
constant, not verified live.

## `cloud` field in the options

`GET /api/transcription-options` adds `cloud: bool` and `provider_label: string | null`
(the provider's display name, only on cloud options; `null` on local ones) to each
option. The UI uses `cloud` for the send warning and `provider_label` to name the
provider; it keeps no list of cloud ids. Cloud options never carry
`recommendation`, `execution` or `profile`, and `can_start` depends only on the
key being configured.

## Cloud warning in a job

A job's screen decides whether it is cloud by looking up its
`selection.provider_id` in `GET /api/providers` (everything it returns is cloud)
and uses its `label`. If that query fails no warning is shown; it is never
inferred from a hard-coded id.

## ElevenLabs (`elevenlabs`, Scribe)

Optional cloud provider, **experimental** (only tested with a fake transport).
Privacy, data sent and key deletion: [privacy/elevenlabs.md](../privacy/elevenlabs.md).

- **Key**: the same `PUT`/`DELETE /api/providers/elevenlabs/key` endpoints; it is
  read from `ELEVENLABS_API_KEY`, `VOZ_ELEVENLABS_API_KEY` or `secrets.toml`.
- **Estimate**: `GET /api/providers/elevenlabs/estimate?media_asset_id=`. Default
  model `scribe_v1`, reference price of 0.40 USD per hour of audio (2026-09-30,
  **not verified live**). The composition root already wires
  `ELEVENLABS_PRICES`/`ELEVENLABS_DEFAULT_MODELS` (module
  `infrastructure/cloud/elevenlabs_pricing.py`) into the price table. Overlap
  between chunks is billed twice and the estimate ignores it.
- **Model**: `elevenlabs_scribe_descriptor()` (`provider_id="elevenlabs"`,
  `model_id="scribe_v1"`, capabilities transcription, words, diarization and
  language detection; no CPU/GPU).
- **Canonical result**: segments per speaker (`speaker` = the provider's
  `speaker_id`, an opaque label), pauses longer than 0.8 s and final punctuation;
  words in monotonic milliseconds. The detected language (ISO 639-3) is translated
  to ISO 639-1.
- **Errors** (`TranscriptionFailureCode`): missing or rejected key (401/403) and
  unexpected responses, `transcription_provider_failed` with `retryable=false`;
  429, 5xx and network failures or timeouts, the same code with `retryable=true`;
  413/415 and non-WAV audio, `transcription_invalid_audio`; cancellation (also
  during upload), `transcription_cancelled`. Messages include neither the key, the
  response body nor paths.
- **Limits** (dated constants in `elevenlabs_scribe.py`, not verified live):
  maximum upload 3 GiB, 100 keyterms of up to 50 characters.
