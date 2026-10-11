# Pre-publication audit of the repository (S16.19)

- Date: 2026-09-30
- Scope: the working tree (versioned, non-ignored files) **and** the entire
  reachable git history (`--all`: 21 commits, a single person as author).
- Tool: [`scripts/audit-secrets.sh`](../../scripts/audit-secrets.sh) (bash + git,
  no new dependencies; it never prints a secret, only `type commit path`).
- This report reproduces no sensitive value. None was found to reproduce.

## Result

**0 HIGH findings. Nothing blocks opening the repository because of secrets or
private data.** 19 REVIEW findings remain (matches inside `tests/`), triaged by
hand below: all are fake data or generic paths, plus one pending authorship
decision (see "Decision before publishing").

| Check | Method | Result |
| --- | --- | --- |
| OpenAI/Anthropic keys (`sk-`), ElevenLabs (`sk_`, `xi-api-key` header with a value), Hugging Face (`hf_`), AWS (`AKIA`/`ASIA`), GitHub (`ghp_`, `github_pat_`…), Slack, Google (`AIza`), private key blocks, `Bearer …`, literal `api_key/secret/token/password = "…"` assignments | `git grep` over the tree and `git log --all -G` over the whole history (including deleted lines) | Only 3 fake values in tests (below). No real key in the tree or in the history. |
| Secret files (`.env*`, `*.key`, `*.pem`, `*.p12`, `credentials*.json`, `id_rsa*`, `id_ed25519*`) | names in the tree and in all commits | None, at any time. `.env.example` would be allowed and does not exist either. |
| `.ai/` never versioned | `git ls-files .ai`, `git log --all -- .ai`, `git check-ignore` | 0 tracked files, 0 commits, ignored by `.gitignore`. |
| Media, databases, models and archives | extensions over tree and history (`wav`, `mp3`, `sqlite*`, `db`, `onnx`, `gguf`, `zip`…) | Only the 6 synthetic fixtures in `tests/fixtures/media/` (about 20 KB in total, provenance and license in [fixtures-licenses.md](../fixtures-licenses.md)). No database, model or recording. |
| Large files | `git ls-tree -r -l HEAD` and all history blobs, 1 MiB threshold | None. The largest is the compiled web bundle (253 KB); the whole git pack weighs about 750 KiB. |
| Personal host paths in versioned files (`/home/<user>`, `/var/home/<user>`, `/Users/<user>`) | `git grep` and `git log --all -G` | None in code or docs. Only invented paths in tests (below). Neither the maintainer's nor any real one. |
| Personal data in files | emails, URLs with `token=`/`key=` | No email in versioned files; no URL with credentials. |
| Local files present but ignored (`.idea/`, `.directory`, `dist/`, caches, `.venv/`) | `git ls-files --others --ignored` | None looks like a secret; none is tracked nor ever was. |

## Triage of the REVIEW findings

`sk-`-shaped keys (3 files): they are obviously fake test literals (they start
with words such as `secret`, `super` or `test`, with a small alphabet) used to
check that V does **not** leak them into logs or diagnostics.

- `tests/unit/test_doctor.py`, `tests/unit/infrastructure/test_secrets.py`,
  `tests/integration/test_providers_api.py`.

Personal-path-shaped paths (7 files): they are invented user directories
(`student`, `usuario-real`, `host`, `u`, `x`, `secret` under `/home`) used to test
that V rejects or redacts host paths.

- `tests/unit/test_xdg_paths.py`, `tests/unit/test_diagnostics_bundle.py`,
  `tests/unit/test_doctor.py`, `tests/unit/application/test_model_tasks.py`,
  `tests/unit/domain/test_media_asset.py`,
  `tests/unit/infrastructure/cloud/test_elevenlabs_scribe.py`,
  `apps/web/src/components/Waveform.test.tsx`.

The script marks as REVIEW (not HIGH) everything under `tests/`; if a test value
stops being obviously fake, it goes to human review.

## Decision before publishing

**Authorship metadata (resolved 2026-10-02).** At audit time the history had a
single author with an institutional email. On 2026-10-02 the
history was rewritten (and force-pushed to the private remote) with the maintainer's GitHub `noreply` address, and the
repository uses that address from then on. A full-history run of
`scripts/audit-secrets.sh` on 2026-10-10 lists only the `noreply` author.

It was the only personal datum the audit found.

## Limitations

- The expressions are heuristic: they detect known formats and literal
  assignments, not arbitrary unformatted secrets (a 12-letter password in a YAML).
  Complement with a dedicated scanner (gitleaks or trufflehog) if available; none
  was added as a dependency.
- Only text diffs are scanned (`-I`): the 6 binary fixtures were checked by name,
  size and provenance, not by content.
- Reachable references are audited (`--all`: branches, remotes and tags). The
  reflog and unreachable objects are not audited: they are not published with a
  `push`.
- The tree includes the not-yet-committed work of other agents of the wave (new
  non-ignored files); it is checked again with the script before the release.

## How to repeat it

```bash
scripts/audit-secrets.sh              # tree + history; exits with 1 if there is a HIGH
scripts/audit-secrets.sh --tree-only  # tree only (fast, for before committing)
```

Before the first public push: run it on the final state, review each new REVIEW
and confirm the output ends in `0 HIGH`. `.gitignore` already covers `.env*`,
keys, databases, media and models; the script exists to catch whatever slipped
through anyway (for example with `git add -f`).
