# V diagnostics and backup

V (formerly VOZ): `v` and `voz` are the same command (`v` since slice V1-02; an installation made before that only has `voz` until it is reinstalled or `uv sync` runs); see [ADR-0009](adr/0009-rename-to-v.md). Examples use `voz`.

Everything in this document is local: no network, no model loading, no calls to
cloud providers. For fixes to common problems see
[Troubleshooting](troubleshooting.md).

## `voz doctor`

Checks FFmpeg/ffprobe, the `v` command, port, XDG paths, disk, models, ASR runtime, GPU and
optional API keys. Output is text (default) or `--json`; `--redact` hides absolute
paths. The exit code is `1` only if some check reports `FALLO` (fail); warnings do
not change the code. `--host` and `--port` select the address used by the port
check (defaults `127.0.0.1` and `8765`).

The report is currently printed in Spanish: the status labels are `OK`, `AVISO`
(warning) and `FALLO` (fail), and the check names are those in the first column
below.

| Check | What it measures | Status |
| --- | --- | --- |
| `ffmpeg`, `ffprobe` | the executable is on the `PATH` and answers `-version` | `FALLO` if not found or it cannot run |
| `comando v` | whether the first `v` on the `PATH` is V's own command (compares paths, never runs it) | `OK` if there is no `v` (normal when running from a checkout with `uv run`) or it is V's; warning if another program, e.g. the V language compiler (vlang), shadows it |
| `puerto` | whether `host:port` can be bound | warning if it is busy (V may already be running) or cannot be checked |
| `rutas` | the four XDG directories (config, data, cache, state) exist or can be created, and are writable | `FALLO` if any is not writable |
| `disco` | free space in `data` and in `cache` | warning when either has less than 5 GiB |
| `modelos` | models registered by V: `provider/id rev <12 hex> (size GiB)`, read from the manifests (`FileSystemModelStore.registered_descriptors()`), without loading anything | warning if none is registered or reading fails |
| `runtime ASR` | whether Faster Whisper is available (the `asr-local` extra) | warning if it is not installed |
| `GPU/CUDA` | CTranslate2 compute types for CUDA and CPU | warning if there is no CUDA (CPU only) or detection fails |
| `OPENAI_API_KEY`, `ELEVENLABS_API_KEY` | only `set` / `unset` | never: they are optional and "not used unless explicitly selected" |

Keys are never printed: no value, no prefix, no length.

## `voz doctor --bundle <file.zip>`

Creates a zip to attach to a report. It implies `--redact`, prints the normal
diagnostics and does not overwrite an existing file (it exits with code `2`).

| File | Contents |
| --- | --- |
| `doctor.json` | the doctor result, with redacted paths |
| `versions.json` | Python, platform, V, fastapi, sqlalchemy, alembic, faster-whisper, ctranslate2 (`null` if not installed) |
| `database.json` | current and head Alembic revision, number of projects, number of jobs per state, error codes of failed jobs |
| `README.txt` | what the bundle contains |

Redaction: the home folder becomes `~` and the XDG bases become
`$XDG_CONFIG_HOME`, `$XDG_DATA_HOME`, `$XDG_CACHE_HOME`, `$XDG_STATE_HOME`
(applied to all text of all files). Job error codes that do not have the shape of
a stable code (`[A-Za-z0-9_.-]{1,64}`) are grouped as `other`.

It never includes: the database, media, transcripts, project or file names,
models, or environment variable values. The database is opened read-only and only
`COUNT`/`GROUP BY` queries over `state` and `error_code` are run. Regression:
`tests/unit/test_diagnostics_bundle.py` seeds sensitive names, text and paths and
verifies that none appears in any file of the zip.

## Backup before migrating

Before migrating an **existing** database whose revision is not head
(`upgrade_to_head`), V creates a consistent copy (SQLite backup API, WAL-aware,
fsync of the file and the directory) at:

```
$XDG_STATE_HOME/voz/backups/voz-<current_revision>-<UTC YYYYMMDDThhmmssffffffZ>.sqlite3
```

- The 5 most recent backups are kept; older ones are deleted.
- A new database, or one already at head: no backup.
- If the backup fails, `MigrationBackupError` (`code =
  "migration_backup_failed"`) is raised and the database is **not** migrated; it
  stays intact.
- Files are created with `0600` permissions in a `0700` directory.
- To restore: stop V and copy the backup over `$XDG_DATA_HOME/voz/voz.sqlite3`
  (delete `voz.sqlite3-wal` and `-shm` first).

On Windows and macOS the `state` directory (where `backups/` lives) is the one
listed in [Windows and macOS](install/windows-macos.md#where-v-stores-its-data);
an absolute `XDG_STATE_HOME` overrides it on every platform.
