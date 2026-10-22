# Contributing to V

Thank you for your interest in V, a local-first voice tool. Bug reports,
feature ideas, documentation fixes and code contributions are welcome. This
guide explains how to set up the project, check your work and open an issue or
a pull request. By taking part you agree to follow the
[Code of Conduct](CODE_OF_CONDUCT.md).

V has no tagged release yet, so `main` is the branch to work against. The
[roadmap](ROADMAP.md) lists what is planned next, if you are looking for
something to pick up.

## Naming note

The product is called **V** and the repository is `MarshallGomez1103/V`.
Internal identifiers keep the old name on purpose: the Python package is
`voz`, environment variables are `VOZ_*`, and user data lives in `voz/` XDG
directories. See [ADR-0009](docs/adr/0009-rename-to-v.md). Please do not
rename them as part of an unrelated change.

The command is `v`, with `voz` kept as an alias (for example
`uv run voz --no-browser`).

## 1. Opening an issue

Use the templates in [.github/ISSUE_TEMPLATE](.github/ISSUE_TEMPLATE) for bug
reports and feature requests. Before filing:

- search the existing issues to avoid duplicates;
- for a bug, include steps to reproduce, what you expected, what happened, your
  operating system and the output of `voz doctor --redact` (review it before
  posting);
- issues and their attachments are public: never attach recordings,
  transcripts, credentials or other private data;
- for a security vulnerability, do not open an issue; follow
  [SECURITY.md](SECURITY.md).

For a larger change, open an issue first to discuss the idea before investing
time in a pull request.

## 2. Setting up

You need Python 3.12 or newer with [uv](https://docs.astral.sh/uv/), Node.js
with npm for the web frontend, and FFmpeg. Platform-specific steps are in
[docs/install/linux.md](docs/install/linux.md),
[docs/install/windows-macos.md](docs/install/windows-macos.md) and, for Bazzite
or Fedora Atomic,
[docs/development/setup-bazzite.md](docs/development/setup-bazzite.md).

```bash
uv sync --all-groups
uv run voz --no-browser          # backend + bundled UI at http://127.0.0.1:8765
cd apps/web
npm ci
npm run dev                      # frontend development server
```

Fork the repository, create a branch from `main` and keep each branch focused
on one change.

## 3. Checks to run

Run the checks that match the layers you touched.

### Backend and CLI

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run pyright
```

Run a single backend test while iterating:

```bash
uv run pytest tests/unit/path/to/test_file.py -q
```

### Frontend

```bash
cd apps/web
npm run lint
npm run typecheck
npm run test
npm run build
```

`npm run build` regenerates the web bundle committed under `src/voz/static`.
Run it only when you mean to change that bundle.

### Supply-chain checks

The `Supply chain` workflow audits the locked dependencies (`pip-audit`,
`npm audit`) and scans the Git history for secrets (gitleaks). It also runs
weekly, so it can fail on an unchanged branch when a new advisory is published.
To run the same audits locally:

```bash
uv export --frozen --no-hashes --no-dev --all-extras --no-emit-project -o /tmp/requirements.txt
uvx pip-audit==2.10.1 --disable-pip --no-deps -r /tmp/requirements.txt
npm audit --audit-level=high --prefix apps/web
```

Prefer upgrading the dependency. If an advisory does not apply, record it with
a dated reason: `--ignore-vuln <ID>` in `.github/workflows/supply-chain.yml`,
or a narrow regex and path in the allowlist of `.gitleaks.toml`. Use obviously fake values
in test fixtures; a real credential in history must be revoked, not ignored.

Ordinary verification does not need Whisper or other speech models, paid
providers or changes to your operating system, and a change should not require
them.

## 4. Tests

- New behavior needs tests at the appropriate level (unit, integration or
  frontend).
- Every bug fix needs a regression test that fails before the fix.
- Cover failure and cancellation paths when your change introduces them.
- Tests must run offline and must not need real models or real recordings.

## 5. Privacy and excluded content

Never include any of the following in a commit or pull request:

- recordings, audio, video or transcripts that are private, yours or anyone
  else's;
- downloaded ASR, diarization or voice models, or their weights (models do not
  belong in Git);
- media files generated during manual testing;
- SQLite databases, caches, or anything under the runtime XDG paths;
- API keys, tokens, `.env` files or any other secret.

If you need an audio fixture, generate a synthetic one (for example with
`ffmpeg -f lavfi`) and record its provenance and license in
[docs/fixtures-licenses.md](docs/fixtures-licenses.md). Do not use real
recordings.

## 6. Architecture rules in short

The overall design is in the [architecture overview](docs/architecture/README.md)
and the [ADRs](docs/adr/README.md). The rules contributors trip over most often:

- Dependencies point inward: `interfaces/infrastructure -> application ->
  domain`. The domain imports no framework.
- Every external provider sits behind a port; adapters are wired only at the
  composition root.
- The server binds to `127.0.0.1` by default, and nothing calls a cloud API
  unless the user explicitly selected that provider.
- The browser never receives absolute host paths. Errors use stable codes and
  user-safe messages.
- Do not add a dependency without explaining why the standard library and the
  existing dependencies are not enough.

If your change introduces or modifies a durable architectural decision (layer
boundaries, framework choice, persistence schema, a provider contract), add a
new ADR in `docs/adr/` or update the existing one, following the format of the
current ADRs (context, decision, consequences, alternatives considered,
verification). Do not record a durable decision only in the pull request
description.

## 7. Documentation language

Public documentation (README, docs, ADRs, issue and pull request templates,
CHANGELOG entries) is written in English. User interface strings go through the
i18n catalogs (Spanish and English), not hard-coded text.

## 8. Commit style

Use [Conventional Commits](https://www.conventionalcommits.org/):
`type(scope): summary`, lowercase and in the imperative mood, for example:

```text
feat(asr): add a quality profile for faster-whisper
fix(media-storage): prevent traversal in unsafe file names
docs(adr): complete the providers ADR
test(jobs): cover cancellation during resume
```

Suggested types: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`, `ci`.
The scope is the affected module or layer (for example `domain`,
`media-storage`, `jobs`, `frontend`, `adr`).

## 9. Opening a pull request

1. Keep the change small and focused; do not mix unrelated changes.
2. Make sure the checks in section 3 pass for what you touched.
3. Open the pull request against `main` and complete the
   [pull request template](.github/pull_request_template.md): what changed and
   why, the commands you ran, confirmation that no secrets, media or private
   data are included, an ADR if the change is architectural, and a regression
   test if it fixes a bug.
4. Update the README, the docs or the CHANGELOG when user-visible behavior
   changes.

## 10. What a review looks for

A maintainer reviews a pull request for:

- the change does what it says and nothing unrelated;
- tests at the appropriate level, including a regression test for each fix;
- formatting, lint, type checking and tests pass;
- the architecture and privacy rules above are respected;
- user-visible behavior and architectural decisions are documented;
- claims in the description and documentation match what was actually run:
  a feature that has not been exercised on a platform or provider is described
  as experimental, not supported.

Reviewers may ask for changes; please answer in the pull request thread.
