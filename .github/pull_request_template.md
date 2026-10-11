## Summary

Briefly describe what this pull request changes and why.

## Roadmap IDs touched

List the exact `ROADMAP.md` IDs (one to three) that belong to a single vertical
slice:

-

## Checklist

### Process (AGENTS.md / CONTRIBUTING.md)

- [ ] I read `AGENTS.md` and the ADRs relevant to this change.
- [ ] I recorded the assignment (exact IDs) in the "Trabajo activo" table of
      `ROADMAP.md` before implementing.
- [ ] `ROADMAP.md` is updated (checkbox, status and latest verified
      achievement) in the same edit as this change, only after verifying the
      result.

### Backend checks run

- [ ] `uv sync --all-groups`
- [ ] `uv run pytest`
- [ ] `uv run ruff check .`
- [ ] `uv run ruff format --check .`
- [ ] `uv run pyright`
- [ ] Not applicable (this change does not touch the backend or CLI).

### Frontend checks run

- [ ] `npm ci` (in `apps/web`)
- [ ] `npm run lint`
- [ ] `npm run typecheck`
- [ ] `npm run test`
- [ ] `npm run build`
- [ ] Not applicable (this change does not touch `apps/web`).

### Privacy and scope

- [ ] Contains no recordings, transcripts or real private data.
- [ ] Contains no models, weights, generated media, databases, caches or
      `.ai/` content.
- [ ] Contains no API keys, tokens or secrets.
- [ ] This change does not span more than one vertical slice of the roadmap.

### Architecture and regression

- [ ] I added or updated an ADR in `docs/adr/`.
- [ ] Not applicable (not a durable architecture change).
- [ ] If this PR fixes a bug, I added a regression test.
- [ ] Not applicable (this PR does not fix a bug).

## Known risks / pending follow-ups

Describe any limitation, uncovered case or follow-up work left out of this PR.
