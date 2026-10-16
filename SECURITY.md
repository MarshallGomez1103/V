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
- **No host paths in the browser.** API responses must not contain absolute
  host paths.

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
- failures of a feature already marked experimental in `ROADMAP.md`;
- access by other local users and processes when optional loopback
  authentication is disabled (a documented limit);
- vulnerabilities that exist only in a third-party provider, fork or
  unofficial build.

## How to report

Please do not open a public issue or pull request that describes an undisclosed
vulnerability, and do not attach recordings or real data belonging to another
person.

- **Once the repository is public**, report privately via GitHub's Private
  Vulnerability Reporting (Security -> Report a vulnerability).
- **Until then**, the repository is private and that feature is not available
  for it. Contact the maintainer, @MarshallGomez1103, on GitHub without
  including exploit details, to arrange a private channel.

V does not publish an e-mail address for security reports.

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
