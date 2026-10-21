# Changelog

All notable changes to V are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project adopts
[semantic versioning](https://semver.org/spec/v2.0.0.html) with the rules in
[docs/release.md](docs/release.md). While the version is `0.x`, a minor change
may break compatibility.

Entries written before the rename were translated from Spanish and keep the
former product name VOZ where they describe it.

## [Unreleased]

No release has been published yet: the tree version is `0.1.0`
(`pyproject.toml` and `voz.__version__`) and nobody has tagged or published
artifacts. What follows is everything that already exists in the repository.

### Added

- `voz` CLI (Typer): starts the local server on `127.0.0.1:8765` and opens the
  browser unless `--no-browser` is given; `voz doctor` (`--json`, `--redact`)
  checks FFmpeg/ffprobe, port, XDG paths, disk, ASR runtime and GPU without
  loading models.
- Local web application served by the API itself (React + Vite; the compiled
  bundle ships inside the wheel): projects, audio/video upload, engine choice,
  job screen with SSE progress, virtualized segment list, original-audio player
  with synchronized seek, waveform with zoom, search, and segment editing with
  autosave and conflict control.
- Safe ingestion with FFmpeg: immutable original with SHA-256, per-stream
  validation, normalization to mono 16 kHz, cancellation and temporary-file
  cleanup, free-disk-space check.
- Local chunked transcription with SQLite checkpoints, cancellation between
  chunks and resumption of interrupted jobs at startup; optional Faster Whisper
  adapter (`asr-local` extra, which includes the CUDA 12 wheels
  `nvidia-cublas-cu12` and `nvidia-cudnn-cu12` on Linux).
- Optional transcription providers beyond Faster Whisper: whisper.cpp (when a
  `whisper-cli` is available) and opt-in cloud providers (OpenAI and
  ElevenLabs Scribe) that are never enabled implicitly.
- Automatic local speaker diarization with sherpa-onnx (no torch, no token),
  as an optional job stage; see [ADR-0007](docs/adr/0007-local-diarization-sherpa-onnx.md).
- Native word-level timestamps from Faster Whisper
  ([ADR-0008](docs/adr/0008-word-timestamps.md)).
- SQLite persistence (WAL) with Alembic migrations applied at startup (`0001`
  to `0004`), data under the XDG directories.
- HTTP export to TXT, Markdown, SRT, VTT and the canonical `voz.transcript` v1
  JSON (with per-speaker and timestamp variants).
- Packaging: reproducible wheel and sdist with `uv build`
  (`scripts/check-reproducible-build.sh`), `scripts/checksums.sh` for
  `SHA256SUMS`, installation check with `uv tool install`
  (`scripts/check-install.sh`), a CI packaging job and the
  [Linux installation guide](docs/install/linux.md).
- Documentation: ADRs 0001-0006, C4 diagrams, `docs/api/` contracts,
  `CONTRIBUTING`, `CODE_OF_CONDUCT`, `SECURITY`, `NOTICE` and fixture licenses.
- Windows, macOS and Linux with a double click: `Iniciar-Windows.bat`,
  `Iniciar-Mac.command` and `Iniciar-Linux.sh` install `uv` if missing and
  start VOZ; FFmpeg/ffprobe are downloaded once if missing (pinned by commit
  and SHA-256); native paths on Windows and macOS and a portable filesystem
  layer (`safe_fs`). Guide in [docs/install/windows-macos.md](docs/install/windows-macos.md).
- A second double click reuses the VOZ instance that is already open instead of
  launching another server.
- **Close server** button (`POST /api/shutdown`) and desktop shortcut
  (`GET/POST /api/desktop-shortcut`), both protected by an anti-CSRF header.
- Installable as an app from Chrome/Edge (PWA: manifest and own icons), first
  phase of the [Tauri packaging plan](docs/packaging/tauri-plan.md).
- New interface built on the IBM Carbon Design System: UI Shell, White/Gray
  10/90/100 and automatic themes, 8 accent colors, Spanish and English (i18n
  es/en), tooltips on technical terms and IBM Plex bundled locally (the bundle
  loads nothing from the Internet).
- Transcript editor: speaker on the left, speaker timeline with a synchronized
  cursor, properties panel and virtualized list.
- Per-stage progress (Preparing, Transcribing, Speakers, Saving) with elapsed
  time, ETA and live text (`GET /api/jobs/{id}/preview`); the text can be read
  while speakers are still being computed. `POST /api/jobs` accepts `prompt`
  (style instructions). Migration `0008`.
- Home with a transcript library (`GET /api/library`) and a permalink per
  transcript (`#/t/<id>`, `#/nueva`, `#/modelos`, `#/proveedores`): Back and
  reload reopen the same job. Contract in [docs/api/library.md](docs/api/library.md).
- Rename (`PATCH /api/projects/{id}`) and delete projects
  (`DELETE /api/projects/{id}`, which also removes their media files; 409
  `project_busy` while a job is running).
- Recompute speakers without re-transcribing
  (`POST /api/transcripts/{id}/rediarize`), with a measured clustering
  threshold, merging of very small speakers and per-speaker `talk_ms`/`first_ms`;
  speakers panel with talk time, filter and audio sample.
- The review queue jumps to the segment and to the audio.
- Export with preview: dialog with format, "Include timestamps", "Group by
  speaker" and the first lines of the result before downloading.
- Player with volume up to 300 %, speed selector and keyboard shortcuts.
- **Material 3** skin as an alternative design system, selectable in Settings
  next to Carbon (colors derived from the chosen accent, Roboto Flex bundled
  locally); evaluation in [docs/design/material3.md](docs/design/material3.md).
- `--allow-host NAME` option: adds extra hostnames to the accepted `Host`
  allowlist. Binding to a non-loopback address (`--host`) now prints a warning
  that V has no authentication ([ADR-0006](docs/adr/0006-local-first-privacy.md));
  with a wildcard host (`0.0.0.0` or `::`) the guard also accepts the machine's
  own name and IP addresses.
- [ADR-0009](docs/adr/0009-rename-to-v.md): decision record for renaming the
  product to V.
- `NOTICE` rewritten in English and new [docs/licenses/models.md](docs/licenses/models.md),
  a per-model table of model-weight licenses kept separate from the MIT license
  of the code. Verified: faster-whisper, whisper.cpp ggml and pyannote
  segmentation-3.0 (MIT); the WeSpeaker embedding weights are not yet verified.

### Changed

- The product is renamed to **V** (formerly VOZ). User-visible names change;
  internal identifiers and on-disk contracts (Python package, XDG paths,
  `voz.sqlite3`, the `voz.transcript` format, `VOZ_*` variables) are kept so no
  user data is put at risk. See [ADR-0009](docs/adr/0009-rename-to-v.md).
- The hatch build ignores `.gitignore` and lists explicitly what it packages:
  broad patterns (`transcript.*`) made the wheel omit
  `voz/domain/entities/transcript.py`, so `voz` failed to start once installed.
- The web UI loads Workspace, Models, Providers and Export lazily; the initial
  chunk drops from 752 kB to 444 kB (below Vite's 500 kB warning). Models and
  Providers mount on first visit and keep their state. The bundled
  `src/voz/static` is regenerated accordingly.
- Broad `except Exception` blocks now log the cause with a traceback where it
  was previously lost (job failure, diarization, project deletion, media
  import, Faster Whisper retry without word timestamps), or document why they
  swallow it. No observable behavior change.
- The test suite isolates `HOME`, `USERPROFILE`, `APPDATA`, `LOCALAPPDATA` and
  `XDG_*` to a temporary directory per test (autouse fixture), so pytest never
  reads or writes the user's real data. Tests that set these variables still
  win.

### Fixed

- The voice summary in Speak pluralizes models and voices ("1 model", "2 voices"),
  the custom-model link preview labels the detected license, and the Piper,
  Kokoro and speaker-separation catalog names are no longer shown in Spanish
  when the interface is in English.
- The job worker no longer swallows exceptions silently: `JobRunner._loop` logs
  them with the `job_id` and makes one attempt to leave the job in `FAILED`
  with the code `job_runner_crashed`; if that write also fails the job stays
  recoverable and the worker continues with the queue.
- After a long jump in the segment list the active segment is realigned once
  the painted rows have been measured (previously it ended up about 62 rows out
  of view with 2000 segments because the target was computed from estimated
  heights).

### Security

- Cloud transcription options fail closed: the options selector no longer
  treats an unloaded or failed catalog as consent, and `POST /api/jobs` rejects
  a cloud option without an explicit `cloud_consent: true` (422
  `cloud_consent_required`) before creating or enqueueing any job.
- Requests with a foreign `Host` header are rejected with 400 `host_not_allowed`
  (DNS-rebinding protection). An ASGI middleware serves only loopback hosts
  (`127.0.0.1`, `localhost`, `::1`) or the explicit `--host`, on any port,
  covering API, SSE and static files.
- Patched frontend dependencies in the lockfile: `source-map-js` 1.2.2,
  `brace-expansion` and `undici`. `npm audit --omit=dev` reports 0
  vulnerabilities (previously 1 high). One moderate advisory remains in
  `vitest` 4.1.10 (development only); the 4.1.11 fix is left for a separate
  change.

### Known limitations

- Transcription with a real Faster Whisper model is **experimental**: the full
  flow is tested with a deterministic test engine; the smoke test with a real
  model is opt-in and not yet part of verification.
- CUDA is experimental until exercised on real hardware.
- Cloud providers (OpenAI, ElevenLabs Scribe) are **experimental**: they are
  tested only against fake transports and have never been run against the real
  services.
- Only Bazzite (Fedora Atomic) has been used as a verified development
  environment; other Linux distributions have not been tested.
- No separate forced word-alignment stage (word timestamps come natively from
  Faster Whisper) and no published AppImage/Flatpak (evaluated as prototypes
  only, see `docs/packaging/appimage-flatpak.md`).
