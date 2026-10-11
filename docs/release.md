# Versioning and release process

V follows [SemVer 2.0.0](https://semver.org/). The version lives in a single
source of truth, `pyproject.toml` (`[project] version`), and
`src/voz/__init__.py` (`voz.__version__`) must match it:
`tests/packaging/test_version_consistency.py` checks this and fails if they
diverge. The user-visible history is in [CHANGELOG.md](../CHANGELOG.md).

## Rules while the version is 0.x

- Incrementing the **minor** (`0.2.0`) may break the public API; the changelog
  says so in a "Changed" or "Removed" section.
- Incrementing the **patch** (`0.1.1`) only fixes bugs and does not break the
  public API.
- `1.0.0` will be published when the public API below is considered stable; from
  then on strict SemVer applies (breaking compatibility requires a major).

## What counts as the public API

1. **CLI**: the `voz` command, its subcommands (`serve`, `doctor`, `bench`), its
   options (`--host`, `--port`, `--allow-host`, `--no-browser`, `--json`,
   `--redact`) and its exit codes.
2. **HTTP `/api`**: routes, methods, bodies, status codes and the stable error
   codes (`{"detail": {"code", "message"}}`) documented in [api/](api/README.md).
   This includes the `Host` header rule (`host_not_allowed`).
3. **`voz.transcript` v1 JSON format**: the exported document
   (`"format": "voz.transcript"`, `"version": 1`). Compatible changes (new
   optional fields) do not bump its `version`; an incompatible change creates
   `version: 2` and the exporter keeps reading/emitting the previous one for at
   least one minor. The identifier is unchanged by the rename to V
   ([ADR-0009](adr/0009-rename-to-v.md)).
4. **Migrated data schema**: the SQLite database under XDG and the project
   directory layout. Every change arrives with an automatic Alembic migration and
   no data loss; a migration that cannot preserve data is an incompatible change.

Not part of the public API: importable Python code (`voz.*`), the contents of the
web bundle, log messages, the text of `voz doctor` without `--json`, or functions
marked experimental (for example, transcription with real Faster Whisper and CUDA
until they are exercised on hardware).

## Building artifacts (without publishing)

```bash
export SOURCE_DATE_EPOCH="$(git log -1 --format=%ct)"
uv build --out-dir dist          # wheel + sdist
scripts/checksums.sh dist        # writes and verifies dist/SHA256SUMS
scripts/check-reproducible-build.sh   # 3 builds, same SHA-256
scripts/check-install.sh dist/*.whl   # uv tool install + start outside the checkout
```

Publishing a release (tag, GitHub Release, PyPI) is only done with the
maintainer's explicit authorization and is not part of these scripts.

## Release dry run in CI (without publishing)

`.github/workflows/release-dry-run.yml` (S15.06) runs by hand
(`workflow_dispatch`) and when a `v*` tag is pushed. It runs the three-pass
reproducible build, builds the wheel + sdist with `SOURCE_DATE_EPOCH` from the
latest commit, generates `SHA256SUMS`, installs the wheel with `uv tool` outside
the checkout (`scripts/check-install.sh`) and uploads `dist/*.whl`,
`dist/*.tar.gz` and `SHA256SUMS` as *workflow artifacts* with 7-day retention. Its
only permission is `contents: read` and it contains no step that creates a GitHub
Release or publishes to PyPI: publishing remains a manual decision of the
maintainer. The file was validated locally (YAML syntax and Actions keys) but
**has not been run** because it needs a push.

The AppImage and Flatpak prototypes (S15.12, S15.13) and their measurements are in
[packaging/appimage-flatpak.md](packaging/appimage-flatpak.md); they are not part
of the workflow.
