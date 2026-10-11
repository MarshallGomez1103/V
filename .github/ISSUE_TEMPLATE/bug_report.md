---
name: Bug report
about: Report incorrect, reproducible behavior in V
title: "[bug] "
labels: bug
---

## Description

Describe the incorrect behavior clearly and concisely.

## Steps to reproduce

1. ...
2. ...
3. ...

## Expected behavior

What you expected to happen.

## Observed behavior

What actually happened. Include error messages or stable error codes if there
are any.

## Environment

- V commit or branch:
- Operating system:
- Python version (`python --version`) and Node version (`node --version`):
- Did you install the `asr-local` extra? With which model or provider?

## Evidence

Attach relevant logs (redact private paths and secrets) or a screenshot if it
helps. **Do not attach recordings, transcripts or any private data, yours or
anyone else's.** If you need an audio file to reproduce the bug, use or create
a synthetic fixture, like the ones documented in
[`docs/fixtures-licenses.md`](../../docs/fixtures-licenses.md).

## Is it a regression?

- [ ] Yes, it worked before (say in which commit or version, if you know).
- [ ] I don't know, or not applicable.

## Related roadmap IDs (optional)

If the bug relates to an ID in `ROADMAP.md`, list it here (for example
`S4.12`).
