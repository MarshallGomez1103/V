# V security policy

## Scope

V (formerly VOZ) is a local-first application: it is installed and run on one
person's machine, serves on `http://127.0.0.1:8765` by default, and needs no
account or remote service to work (see [README.md](README.md) and the product
invariants in [AGENTS.md](AGENTS.md)). This policy covers the code in this
repository: the command-line entry points (`v` and `voz`), the local FastAPI server, the web frontend, and the infrastructure
adapters (FFmpeg, SQLite persistence, transcription providers).

Out of scope: optional third-party cloud providers (their own security is up
to that provider), the host operating system, and any fork or unofficial
distribution of the project.

## Threat model

V is built for a single user on a trusted machine. The assumptions that matter
when judging a report:

- **Loopback server.** The server binds to `127.0.0.1` by default. Loopback is
  the access control: other processes and users on the same machine can
  connect to it.
- **Host header validation.** A page on another site can try DNS rebinding to
  read the local API as if it were same-origin. `HostGuardMiddleware`
  rejects any request whose `Host` is not `127.0.0.1`, `localhost`, `[::1]` or
  a name the user passed explicitly (`--host`, `--allow-host`). See
  [ADR-0006](docs/adr/0006-local-first-privacy.md).
- **Shared-token authentication.** CLI binds outside loopback require a private
  token file. A configured token protects API, UI, static assets and streams;
  Basic browser state changes also require a matching Origin. Default loopback
  use remains unauthenticated. A token does not encrypt HTTP or isolate users.
  Direct ASGI deployments must explicitly configure authentication. See the
  [authentication contract](docs/api/authentication.md).
- **Uploads are untrusted input.** Media files go through the FFmpeg ingestion
  pipeline; originals are immutable and derived files are stored separately
  ([ADR-0003](docs/adr/0003-ffmpeg-ingestion.md)).
- **Model provenance matters.** A checksum detects changes to the expected
  download; it does not establish that a model is harmless. Native runtimes
  parse downloaded model files. A child process provides lifecycle and timeout
  control, not an operating-system permission sandbox. Import models only from
  publishers you trust.
- **Model URLs are trusted input.** Remote previews contact the supplied source
  for metadata before installation. Direct sources require HTTP(S) without
  embedded credentials, query strings or fragments; conventional redirects and
  proxy behavior apply. There is no destination-network allowlist or comprehensive
  SSRF protection. Review source addresses before previewing or importing them.
- **No host paths in the browser.** API responses must not contain absolute
  host paths.

## HTTP response policy

Handled HTTP responses include `X-Content-Type-Options: nosniff`,
`X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, same-origin resource
policy and a Content Security Policy. Scripts, connections and workers are
restricted to the application origin; objects and framing are disabled. Inline
styles remain permitted for the UI, and media permits local blob URLs. Camera
access is disabled; microphone access is restricted to the same origin.

The header layer wraps Host and authentication checks without buffering uploads,
audio ranges or SSE bodies. It does not add HSTS to the local HTTP server or
change cache policy. Unhandled exceptions outside that layer and deployments
that replace the application middleware are outside this guarantee.

## Dependency and secret checks

Run `npm audit` from `apps/web` and audit the installed Python environment with
`pip-audit --path .venv/lib/python3.12/site-packages --skip-editable` from an
isolated audit-tool environment. Check tracked files and history with
`bash scripts/audit-secrets.sh`. Review findings rather than treating a successful
scan as proof that every optional runtime or historical secret is covered.

## What to report

Examples of valid security reports:

- absolute host paths exposed through the API or the frontend, against the
  invariant that the UI must not know filesystem paths;
- remote code or command execution through an uploaded file (for example via
  the FFmpeg ingestion pipeline or the media probe);
- path traversal, or writes outside the trusted media storage directory;
- leaks of private user data (recordings, transcripts, API keys, or contents of
  the local database) to a third party, a log, or an endpoint not meant for
  that purpose;
- a bypass of the Host header validation, or a way to reach the API from a
  non-loopback origin without the user having explicitly enabled exposure;
- a vulnerable dependency (Python or npm) with a real, known exploit path
  inside V.

What is normally **not** a security issue, and should go in a regular bug
report instead:

- UI bugs with no impact on confidentiality, integrity or availability;
- ordinary functional failures in experimental features; a security defect in
  an experimental feature is still in scope;
- access by other local users and processes when optional loopback
  authentication is disabled (a documented limit);
- vulnerabilities that exist only in a third-party provider, fork or
  unofficial build.

## How to report

Please do not open a public issue or pull request that describes an undisclosed
vulnerability, and do not attach recordings or real data belonging to another
person.

- If this public repository has Private Vulnerability Reporting enabled, use
  **Security and quality -> Advisories -> Report a vulnerability**. Follow
  [GitHub's reporting instructions](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/report-privately).
- If that button is missing, or the repository is private, ask the maintainer
  @MarshallGomez1103 for a private security contact without including exploit
  details, credentials or private data. An ordinary issue may contain only the
  request for a contact method; use the **Request a private security contact**
  issue template for this public request. GitHub profiles do not provide private
  direct messages.

Ordinary issues, pull requests, discussions and their attachments in a public
repository are public. A `security` label, a closed issue or an issue template
does not make them private. Adding this policy does not enable GitHub's private
reporting feature.

Private Vulnerability Reporting is for security findings. Confidential ordinary
bugs or internal planning need a separately agreed private channel or a private
repository; the issue templates here do not provide either.

V does not publish an e-mail address for security reports.

### Maintainer setup

On a public repository, an owner or administrator can enable **Settings ->
Security and quality -> Advanced Security -> Private vulnerability reporting**.
Verify that **Report a vulnerability** appears, then configure **Watch ->
Custom -> Security alerts** and account notification preferences so reports are
noticed. These are remote settings; the files in this repository cannot confirm
or activate them. See [GitHub's configuration guide](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/configure-vulnerability-reporting/configure-for-a-repository).

Keep reproduction details and patches in the private report or a draft security
advisory, inviting only the collaborators needed to assess the problem. Agree
on disclosure after a fix or mitigation is available. Publishing an advisory
is a separate, public action; accepting a private report as a draft does not
publish it. See [GitHub's advisory guidance](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/fix-reported-vulnerabilities/create-repository-advisory).

Include, as far as you can:

- a description of the problem and its potential impact;
- steps to reproduce, with the commit of the repository you tested;
- if relevant, a synthetic fixture that reproduces the problem without real
  private data (V does not accept private recordings as fixtures; see
  [AGENTS.md](AGENTS.md)).

## Response times

V has no public release and no dedicated security team. These are targets, not
a contractual commitment:

- acknowledgement of the report: within 7 days;
- initial severity assessment: within 14 days of acknowledgement;
- fix or mitigation: depends on severity and on the maintainer's availability;
  an estimate is shared once the report has been assessed.

## Supported versions

V has no public release yet (see sections 15 and 16 of
[ROADMAP.md](ROADMAP.md)). Until the first release, **only the `main` branch
is supported** for security reports and fixes. There are no tagged versions and
no maintenance cycle for older versions.

| Version | Supported |
| --- | --- |
| `main` (current checkout) | yes |
| any fork, or any version before the first release | no |

When a first public release exists, this table will be updated to show which
tagged versions receive security patches.
