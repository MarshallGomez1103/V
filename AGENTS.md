# V engineering rules

These rules apply to every human or AI contributor working in this repository.
They are deliberately stable: transient session notes and assignments are kept
privately, outside the repository, and never in this file.

## Before changing anything

1. Read this file, `ROADMAP.md`, and the ADRs relevant to the change.
2. Read any private handoff notes you were given.
3. Select one vertical slice containing no more than three closely related
   roadmap items.
4. Identify the layers and files affected, then run the smallest useful baseline
   checks.
5. Preserve unrelated local changes. Do not rewrite a whole module when a small
   change is sufficient.

## Architecture and dependency boundaries

- V is a local-first modular monolith with Clean/Hexagonal boundaries.
- Dependency direction is inward:
  `interfaces/infrastructure -> application -> domain`.
- The domain must not import FastAPI, SQLAlchemy, FFmpeg, torch, OpenAI, cloud
  SDKs, or other framework/infrastructure packages.
- Application use cases depend on ports, never concrete adapters.
- Every external provider implements a port. Provider-specific request/response
  types stay inside its adapter.
- Routers validate/translate transport data; they do not contain business logic.
- Use cases do not contain SQL or filesystem implementation details.
- Infrastructure is wired at the composition root; do not instantiate adapters
  deep inside domain or application code.
- The frontend consumes API contracts and must not know host filesystem paths,
  database schemas, or provider internals.
- Do not return absolute host paths to the browser.
- Durable changes to architecture require a new or updated ADR.

## Product and privacy invariants

- Local/offline processing is the default. Never call a cloud API unless the
  user explicitly selected that provider.
- Bind the local server to `127.0.0.1` by default. LAN exposure requires an
  explicit option.
- Uploaded originals are immutable. Derived files must be stored separately.
- Never commit private recordings, transcripts, API keys, models, generated
  media, local databases, caches, or local session context.
- Store runtime data according to XDG Base Directory conventions; never inside
  the source checkout.
- Never log secrets. Redact sensitive paths and values from diagnostic bundles.
- A feature that has not been exercised on a claimed platform/provider is
  experimental, not supported.
- Do not silently replace or “correct” a literal transcript with LLM output.

## Scope and implementation rules

1. Do not modify more than one vertical slice per task.
2. Do not add a dependency without documenting why the standard library and
   existing dependencies are insufficient.
3. Do not break offline mode.
4. Do not introduce microservices, Redis, RabbitMQ, Kafka, Postgres, Kubernetes,
   Electron, or Tauri unless a later accepted ADR explicitly authorizes it.
5. Do not build a dynamic plugin framework before at least two real providers
   prove the needed abstraction.
6. Prefer typed, small interfaces and deterministic pure functions at the core.
7. Long-running work must be represented as a job with explicit progress,
   cancellation, typed failure, and recoverable checkpoints where applicable.
8. The UI must read job state from the API; it must not infer state from logs.
9. Use stable error codes and user-safe messages. Raw tracebacks are diagnostic
   data, not normal UI.
10. If MIT-licensed code is adapted, preserve the required attribution and add
    it to the project notices.

## Testing and definition of done

A roadmap item is done only when all applicable conditions hold:

- The smallest complete behavior for the selected slice is implemented.
- New behavior has tests at the appropriate level.
- Every fixed bug has a regression test.
- Relevant formatting, lint, type checks, and tests pass.
- Failure and cancellation paths are covered when the change introduces them.
- User-facing behavior and architecture changes are documented.
- The result was verified, not merely inferred from generated files.
- `ROADMAP.md` is updated when each sprint closes, and only with what was
  verified: an item is ticked only after its checks have run.
- Before a handoff, the private notes record files touched, checks run, open
  risks, and exactly one next objective.

Never mark an item complete because code was written but not checked. If a check
cannot run, leave the item incomplete and record the blocker.

## Development commands

Run commands from the repository root unless noted. These are the commands the
CI workflow (`.github/workflows/ci.yml`) runs.

### Backend and CLI

```bash
uv sync --locked --all-groups --extra diarization
uv run --frozen v --no-browser
uv run --frozen pytest
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen pyright
```

The `diarization` extra brings `numpy`, which Pyright and the speaker-separation
tests need.

Run one backend test while iterating:

```bash
uv run --frozen pytest tests/unit/path/to/test_file.py -q
```

### Frontend

```bash
cd apps/web
npm ci
npm run dev
npm run lint
npm run typecheck
npm run test
npm run build
```

`npm run build` rewrites the bundle that is versioned under `src/voz/static`.
Run it only when you mean to change that bundle, and review the resulting diff.

### Full local verification

```bash
uv run --frozen pytest
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen pyright
cd apps/web
npm run lint
npm run typecheck
npm run test
```

Add `npm run build` only when the bundle is meant to change.

Do not install Whisper, download speech models, invoke paid providers, publish a
package, push commits, or alter the host operating system as part of ordinary
verification.

## Handoff notes

Keep public, durable status in `ROADMAP.md`. Keep session continuity in private
notes outside the repository, and make them cover:

- state and what was finished;
- immediate next step;
- files touched;
- tests and checks run;
- risks and known bugs;
- what must not change;
- the next objective, naming exact roadmap IDs and staying within one vertical
  slice.

Do not paste conversation transcripts into repository documentation.
