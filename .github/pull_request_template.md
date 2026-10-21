## Summary

Briefly describe what this pull request changes and why. Link the related issue,
if there is one.

## Checklist

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
- [ ] Contains no models, weights, generated media, databases or caches.
- [ ] Contains no API keys, tokens or secrets.
- [ ] The change is focused on one purpose and does not mix unrelated work.

### Architecture and regression

- [ ] I added or updated an ADR in `docs/adr/`.
- [ ] Not applicable (not a durable architecture change).
- [ ] If this PR fixes a bug, I added a regression test.
- [ ] Not applicable (this PR does not fix a bug).
- [ ] I updated the README, docs or CHANGELOG for user-visible changes, or none
      are needed.

## Known risks / pending follow-ups

Describe any limitation, uncovered case or follow-up work left out of this PR.
