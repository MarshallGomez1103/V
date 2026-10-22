# HTTP API

V serves a local JSON API under `/api`. The browser UI is its
only first-party client. The exact, generated schema is published at
`/openapi.json` (interactive view at `/docs`); the pages below document the
contracts that go beyond the schema: error codes, side effects, limits and
semantics.

The separate [OpenAI-compatible audio interface](openai-compat.md) exposes a
limited local subset under `/v1`; its endpoint error envelope differs from `/api`.

## Common rules

- **Loopback by default.** The server binds to `127.0.0.1`. Exposing it on a
  network requires an explicit option (`--host`); see
  [ADR-0006](../adr/0006-local-first-privacy.md).
- **Host header check.** Every request must arrive with a `Host` header that is
  a loopback name (`127.0.0.1`, `localhost`, `::1`) or the host given explicitly
  with `--host` / `--allow-host`. The port is ignored; only the host name
  matters. Any other `Host` is rejected before routing with HTTP 400:

  ```json
  {"detail": {"code": "host_not_allowed", "message": "This server only answers requests addressed to its own host."}}
  ```

  This closes DNS-rebinding attacks, in which a page on `evil.example`
  re-resolves its own name to `127.0.0.1`. WebSocket upgrades with a disallowed
  `Host` are closed with code 1008. Implementation:
  `src/voz/interfaces/api/host_guard.py`.
- **Cross-origin check.** A `POST`, `PUT`, `PATCH` or `DELETE` request, and a
  WebSocket handshake, is refused with HTTP 403 when its `Origin` header names
  another origin than the one the request was addressed to (scheme, host and
  port; `null` and repeated headers fail) or when `Sec-Fetch-Site` is anything
  other than `same-origin` or `none` (so `cross-site` and `same-site` are
  refused):

  ```json
  {"detail": {"code": "origin_not_allowed", "message": "This request comes from another origin and was refused."}}
  ```

  A refused WebSocket handshake is closed with code 1008. Reads (`GET`, `HEAD`,
  `OPTIONS`) are not affected. This stops a page on another site from changing
  state with a form post or a `text/plain` or multipart `fetch`, which browsers
  send without a CORS preflight. Clients that send neither `Origin` nor
  `Sec-Fetch-Site` (the `voz` CLI, `curl`, OpenAI client libraries) keep
  working. The scheme is the one the server sees: behind a reverse proxy that
  terminates TLS, the server must be configured to trust the proxy so that its
  scheme matches the external origin (see
  [authentication](authentication.md)); otherwise browser writes are refused.
- **Errors** always have the shape
  `{"detail": {"code": "<snake_case_code>", "message": "<safe text>"}}`, with
  optional extra fields documented per endpoint. Codes are stable; messages are
  for humans and may change. Responses never contain absolute host paths,
  tracebacks or secrets. Request-body validation failures that FastAPI detects
  itself return the standard HTTP 422 validation payload.
- **Dates** are ISO 8601 with a time zone. Identifiers are canonical UUID
  strings.
- **Destructive or side-effecting actions** (`POST /api/shutdown`,
  `POST /api/desktop-shortcut`, `DELETE /api/projects/{id}`,
  `DELETE /api/synthesis/{id}`) require the custom
  header `X-VOZ-Action: <action>`. A custom header forces a cross-origin page
  through a CORS preflight, which the server never grants.
- **No cloud calls** unless the user explicitly selects a cloud provider for a
  job (see [providers.md](providers.md) and [privacy/](../privacy/openai.md)).
  Creating a cloud transcription or synthesis job requires
  `cloud_consent: true` in the request, and a cloud job interrupted by a restart
  is failed instead of resumed (see [jobs.md](jobs.md#cloud-consent-cloud_consent)
  and [synthesis.md](synthesis.md#cloud-consent)).

## Endpoints

| Area | Page |
| --- | --- |
| Projects, media import, jobs, SSE events, diarization, shutdown, desktop shortcut | [jobs.md](jobs.md) |
| Project glossary, quality profile catalog | [projects.md](projects.md) |
| Library, media info and playback, rename and delete projects | [library.md](library.md) |
| Transcription options (what can run on this machine) | [transcription-options.md](transcription-options.md) |
| Segment text editing, segment quality flags | [segments.md](segments.md) |
| Speakers: list, rename, merge, assign | [speakers.md](speakers.md) |
| Export (TXT, Markdown, SRT, VTT, JSON) | [export.md](export.md) |
| Waveform peaks | [waveform.md](waveform.md) |
| Model manager and background install tasks | [models.md](models.md) |
| Cloud provider keys and cost estimates | [providers.md](providers.md) |
| Speech synthesis: options, jobs, progress, audio, history | [synthesis.md](synthesis.md) |

`GET /api/health` returns `{"status": "ok", "version": "<version>"}` and works as a
readiness probe (`scripts/check-install.sh` uses it).
