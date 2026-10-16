# ADR-0006: Local-first, loopback by default and no implicit cloud

> Translated from Spanish on 2026-10-11 (V1-08b). VOZ is the former name of V (ADR-0009).

- Status: Accepted
- Date: 2026-09-30
- Owners: VOZ maintainers
- Scope: product privacy and network surface (S16.16)
- Related: [ADR-0001](0001-modular-monolith.md),
  [ADR-0002](0002-sqlite-persistence.md) (XDG),
  [ADR-0004](0004-local-asr-and-recoverable-chunks.md) (offline),
  [ADR-0005](0005-transcription-providers.md) (providers)
- Diagrams: [context](../architecture/01-contexto.md),
  [containers](../architecture/02-contenedores.md)

## Context

VOZ processes recordings that may contain classes, meetings or private
conversations. User trust depends on the audio, the transcripts and the paths on
their machine not leaving it except by an explicit decision. The master plan
(section 17) and [AGENTS.md](../../AGENTS.md) already set these invariants; this
ADR records them as an architectural decision with their evidence and their real
limits.

## Decision

1. **Local processing by default.** Import, normalization, ASR, persistence and
   editing run in the local process and without Internet once the model is
   installed. No flow requires an account or a remote service.
2. **Loopback by default.** The server listens on `127.0.0.1`, port `8765`
   (`DEFAULT_HOST`, `DEFAULT_PORT` in `src/voz/interfaces/cli/main.py`).
   Exposing the API on another interface requires passing `--host` explicitly.
   When opening the browser, a wildcard address (`0.0.0.0`, `::`) is translated
   to a connectable loopback address (`browser_host`). The Vite development
   server also listens on `127.0.0.1` and proxies `/api`
   (`apps/web/vite.config.ts`); no CORS is configured.
3. **No implicit cloud.** Cloud providers require explicit selection for the
   job, a visible notice and credentials outside SQLite and logs. Local failures
   never silently fall back to a cloud provider. Compatible cloud endpoints also
   require stored consent; see [provider configuration](../api/providers.md).
4. **Explicit network access.** Confirmed model/runtime installation may download
   artifacts. Explicitly selected cloud jobs contact their provider. Local
   transcription resolves installed models with `local_files_only=True`.
   CLI readiness polls its own health endpoint, without redirects or environment
   proxies; when authentication is configured, it sends the token in a header.
   Building providers and listing local options do not download models.
5. **No telemetry.** There is no sending of metrics, error reports or update
   checks. The web bundle loads no third-party fonts, scripts or images.
6. **Data under XDG, outside the checkout.** The database, originals,
   derivatives, models and temporary files are written under the XDG directories
   ([ADR-0002](0002-sqlite-persistence.md)); the `.gitignore` patterns and the
   rule of not versioning `.ai/` prevent uploading recordings, transcripts or
   models.
7. **No host paths toward the browser.** Responses use identities (UUIDs) and
   display names; files are served through `/api/media/{id}/original`, not by
   path. `voz doctor --redact` hides absolute paths in the report.
8. **Safe errors and logs.** Responses are `{"detail": {"code", "message"}}`
   with stable codes; FFmpeg tracebacks and stderr are not exposed. No secrets
   are logged.
9. **A literal transcript is not silently replaced.** VOZ calls no LLM today;
   any future assisted correction must preserve the literal text and be
   presented as a derivative.

## Positive consequences

- A user can audit the network surface: a loopback port and, only upon
  confirmation, the download of a model.
- Offline behavior is the norm, not a special mode.
- User data is never mixed with the repository.
- Cloud providers follow an explicit selection and consent contract.

## Costs and limits

- **Optional loopback authentication; required for CLI LAN exposure (V10-02).**
  The CLI refuses a non-loopback bind without `--auth-token-file`, before trying
  to reuse an existing server. `v auth-token --output <file>` creates a new
  private token file without printing its contents. A configured token protects
  the complete application: API, UI, static files, SSE and media. API clients use
  Bearer; browsers use Basic with username `v` and the same token. Basic state
  changes require a matching Origin; the Host guard remains enabled.
  Authentication provides no encryption or separate user permissions. See the
  [authentication contract](../api/authentication.md). Default loopback startup
  continues without a token. Direct ASGI deployments must explicitly configure
  authentication and network binding; the CLI rule cannot constrain them.
- **DNS rebinding mitigated (V0-03).** Listening on loopback is not enough: a
  page at `evil.example` can re-resolve its name to `127.0.0.1` and read the API
  as same-origin. `HostGuardMiddleware`
  (`src/voz/interfaces/api/host_guard.py`) answers 400 `host_not_allowed` to any
  HTTP request (API, SSE and static files) whose `Host` is not `127.0.0.1`,
  `localhost`, `[::1]` or the host passed with `--host`; the port does not
  matter. `uvicorn voz.bootstrap:app` is protected with the loopback list. Tests
  use `http://127.0.0.1` as `base_url` (`tests/conftest.py`); `testserver` is
  never in the list. With `--host 0.0.0.0` only a loopback `Host` is accepted
  until V0-04.
- Other processes and users on the same machine can connect to
  `127.0.0.1:8765`. The security scope is in [SECURITY.md](../../SECURITY.md).
- There is no `Content-Security-Policy` or hardening headers on the static
  server (master plan section 17): **planned**.
- Model installation remains explicit. Custom weights must match a supported
  installed engine; declaring a license does not verify its terms.
- Privacy verification of logs is spot-check only (tests of errors without
  paths), not an automatic audit of all messages.
- Platform rating follows the invariants of AGENTS.md: anything not exercised is
  experimental (for example, real CUDA).

## Alternatives considered

### Cloud ASR by default

Rejected. It sends private audio to third parties by default, requires keys and
network, and contradicts the product.

### Listen on `0.0.0.0` by default

Rejected. Without authentication it would expose the data to the local network.

### Opt-out telemetry or automatic update checks

Rejected. Any outgoing signal breaks the property "only the network the user
confirmed".

### Mandatory local access token from the start

Not required for default loopback use. LAN exposure through the CLI requires
a private token file; this shared credential does not provide multi-user isolation.

### Desktop wrapper (Electron/Tauri)

Postponed; see [ADR-0001](0001-modular-monolith.md).

## Original evidence (2026-09-30)

| Requirement | Code or test |
| --- | --- |
| Default host and port, explicit `--host` | `src/voz/interfaces/cli/main.py`; `tests/unit/test_cli.py` (argument forwarding and wildcard translation). There is no dedicated test for the default value of `--host`. |
| No downloads when building/using the provider | `tests/unit/test_asr_bootstrap.py::test_local_asr_composition_is_explicit_and_does_not_download`, `tests/unit/infrastructure/test_model_storage.py::test_resolve_never_downloads_and_rejects_missing_model` |
| Installation with confirmation and pinned revision | `test_install_requires_confirmation_before_constructing_downloader`, `test_install_rejects_unpinned_descriptor` |
| `local_files_only=True` when loading the engine | `tests/unit/infrastructure/asr/test_faster_whisper.py`, `tests/contract/test_transcription_provider.py` |
| XDG paths, outside the checkout | `tests/unit/test_xdg_paths.py`, `tests/unit/test_doctor.py::test_unwritable_path_fails` |
| No host paths in responses | `tests/integration/test_health_api.py`, `tests/integration/test_media_upload_api.py`, `tests/integration/test_media_stream_api.py`, `test_schema_and_adapters_never_persist_host_paths` |
| Diagnostics without paths and without loading models | `tests/unit/test_doctor.py::test_redact_hides_absolute_paths` |
| Generic errors without traceback | `tests/integration/test_media_upload_api.py::test_unexpected_failure_is_generic_without_traceback` |
| Search for cloud clients or telemetry in `src/voz`, `apps/web/src` and the bundle | Manual `grep` review on 2026-09-30: no results; only XML namespace URLs and React's error text in the bundle. It is not an automated test. |

## Authentication evidence (2026-10-16)

`tests/unit/test_server_auth.py` covers credentials, Origin validation and
unbuffered ASGI transports. `tests/unit/infrastructure/test_server_token.py`
covers private token files; `tests/unit/test_cli_server_auth.py` covers LAN
rejection before reuse and credential handling.
`tests/integration/test_server_auth_wiring.py` checks the default application
and preservation of the Host guard.

## Verification

This decision is considered respected when:

- `voz` without options listens only on `127.0.0.1`;
- no normal execution path opens a connection to the Internet, except
  confirmed installation and explicitly selected cloud processing;
- no cloud provider exists without explicit selection, notice and key
  management outside SQLite and logs;
- no HTTP response contains absolute host paths;
- the database, media and models reside under XDG;
- any change that widens the network surface updates this ADR.

**Pending to strengthen the verification (planned):** a test of the default
value of `--host` (the warning when binding outside loopback exists since
V0-04, with tests in `tests/unit/test_cli.py`), and a test that
fails if a `src/voz` module imports an HTTP client or cloud SDK without an
approved ADR.
