# Developing V on Bazzite

V is developed on Bazzite, an immutable Fedora Atomic image.
This guide prepares a development environment without modifying the Bazzite
base image. The commands of Option A were run as written on a clean checkout
(see [Verified on Bazzite](#verified-on-bazzite)); the status of each feature
remains in [ROADMAP.md](../../ROADMAP.md). To **install** V as a user, without a
development checkout, use [../install/linux.md](../install/linux.md).

The Python package, the `voz` command, the `VOZ_*` variables and the
`~/.local/share/voz` directories keep the old name on purpose
([ADR-0009](../adr/0009-rename-to-v.md)), so the commands below still say
`voz`.

## Principles for Bazzite/Fedora Atomic

- Avoid `rpm-ostree install` for ordinary development tools.
- Prefer user-space tools or a Distrobox container.
- Do not use Docker/Podman as a requirement to run V with a GPU.
- Keep models and data in the user's XDG directories, never inside a container
  image or the repository.
- Do not install Whisper or download models during the skeleton bootstrap.
- Do not reboot, rebase the system image or change drivers as part of this
  guide.

## Bootstrap requirements

First check what is available; do not reinstall tools that already work.

```bash
git --version
uv --version
node --version
npm --version
```

Importing and normalizing audio requires `ffmpeg` and `ffprobe` (integration
and E2E tests skip themselves if they are missing; the UI starts without them):

```bash
ffmpeg -version
ffprobe -version
```

Project target versions:

- Python 3.12, managed by `uv`;
- a Node.js version compatible with the one declared by the frontend;
- npm using the versioned lockfile.

Do not depend on the system Python or run `sudo pip install`.

## Option A: user tools

This is the shortest path when `uv`, Node and npm are already available for the
user. From the checkout root:

```bash
uv sync --all-groups --all-extras
cd apps/web
npm ci
npm run build
cd ../..
uv run pytest
uv run voz --no-browser
```

The URL is `http://127.0.0.1:8765`. `--all-extras` also installs `asr-local`
(`faster-whisper`, cuBLAS/cuDNN, about 2.6 GB) and `diarization`
(`sherpa-onnx`). `httpx`, which the HTTP tests (`TestClient`) use, is part of
the `dev` group in `pyproject.toml`, so `--all-groups` already provides it.
At the time of the verified run below (2026-09-30) it was not: `httpx` only
arrived transitively through `huggingface-hub`, and with only `--all-groups`,
`uv run pytest` aborted while collecting `tests/e2e/test_workspace_flow.py`,
`tests/integration/test_jobs_memory_guard_api.py` and
`tests/integration/test_model_tasks_api.py` with `No module named 'httpx'`.

`npm run build` writes the compiled bundle to `src/voz/static`, which is
versioned (`outDir: '../../src/voz/static'` in `apps/web/vite.config.ts`). To
try a build without touching it, run `npx vite build --outDir "$(mktemp -d)"`
from `apps/web`.

## Option B: development Distrobox

Use Distrobox when you prefer to isolate toolchains or multimedia dependencies.
The working folder and the XDG directories keep belonging to the host user.

Conceptual example:

```bash
distrobox create --name voz-dev --image fedora:latest
distrobox enter voz-dev
```

Inside the container, install only the missing development prerequisites,
following each tool's official documentation, and then run the same commands as
Option A. Do not store models in container layers.

Tests with CUDA must be treated as a separate activity: first verify that the
container sees the GPU, then install the stack declared by the project. Do not
change the host driver to accommodate a dependency without an explicit decision
and evidence of the problem.

## Development with separate frontend and backend

During development, two terminals can run the processes separately. The exact
scripts are subject to the bootstrap:

Terminal 1:

```bash
uv run voz --no-browser
```

Terminal 2:

```bash
cd apps/web
npm run dev
```

The frontend must use the versioned development configuration to reach the
local API (the Vite server listens on `127.0.0.1:5173` and proxies `/api` to
`127.0.0.1:8765`). Do not hard-code absolute paths or LAN addresses.

## Quality checks

Backend:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest
```

Frontend:

```bash
cd apps/web
npm run lint
npm run typecheck
npm run test
npm run build
```

The clean verification of Section 1 requires testing from a fresh checkout or
an empty environment. Creating files is not enough: `voz` must start,
`/api/health` must respond and the Home screen must load on `127.0.0.1`. Record
the environment and the commands actually run in the local handoff before
marking S1.22.

## Runtime directories

V must respect these Linux locations:

```text
~/.config/voz/                      (reserved; not written yet)
~/.local/share/voz/voz.sqlite3      (+ -wal and -shm)
~/.local/share/voz/projects/<id>/originals/ and derivatives/
~/.local/share/voz/models/
~/.cache/voz/                       (uploads/, downloads/, waveforms/)
~/.local/state/voz/backups/         (copies made before migrating the database)
```

The full table and who writes each path are in
[ADR-0002](../adr/0002-sqlite-persistence.md).

This data is not versioned. A test environment must be able to redirect the XDG
variables to a temporary directory so as not to contaminate real data.

## Bootstrap troubleshooting

### `uv` uses the wrong Python

Check the resolved version with `uv run python --version`. Fix the project's
declaration or let `uv` fetch Python 3.12; do not replace the host's Python.

### Port 8765 is busy

Check the existing process and use the documented flag:

```bash
uv run voz --no-browser --port 9000
```

Do not terminate unknown processes automatically.

### The UI does not load

Verify separately:

1. that `/api/health` responds;
2. that the frontend build finishes without errors;
3. whether it runs in development mode or as a bundle served by the API;
4. that the URL uses `127.0.0.1` and the port shown by the CLI.

### FFmpeg is not available

This blocks audio import, not the UI startup. Record the diagnostics
(`uv run voz doctor`) and choose a user-level installation or Distrobox. Do not
add base-system layering as an automatic response.

## Exit criterion

The Bazzite setup is considered verified only when a clean checkout allows
installing dependencies, running the relevant checks, starting `voz` and
opening the local UI. That verification has been done and is recorded below;
repeat it and update the date when the dependencies or the flow change.

## Verified on Bazzite

**Date:** 2026-09-30 (S15.10). **Machine:** Bazzite `bazzite-nvidia-open`
(Fedora 44), `uv 0.12.21`, Node 22.22.3, npm 10.9.8, FFmpeg 8.1.3.

Clean checkout (`git clone` of commit `435ed0a`), with `XDG_*` and
`UV_PROJECT_ENVIRONMENT` in a temporary directory; network only to PyPI.

| Command | Result |
| --- | --- |
| `uv sync --all-groups` | installs in about 8 s, but `uv run pytest` fails at collection (missing `httpx`, see Option A; fixed since then, `httpx` is now in the `dev` group) |
| `uv sync --all-groups --all-extras` | installs in about 4 min with an empty cache |
| `uv run ruff check .` / `uv run ruff format --check .` | no errors; 248 files formatted |
| `uv run pyright` | 0 errors, 0 warnings |
| `uv run pytest -q` | 1011 passed, 2 skipped (the opt-in real-model and diarization smoke tests) |
| `uv run voz --no-browser --port 9002` | `GET /` 200 and `GET /api/health` 200; clean shutdown with SIGINT |
| `npm run lint`, `npm run typecheck` | no errors |
| `npm run test` | 25 files, 198 tests pass |
| `npm run build` | the generated bundle is identical to the one versioned in `src/voz/static` (`git status` clean) |

Not verified: `npm ci` (this session had no network access to the npm registry;
the frontend was checked with the already-installed `node_modules`), Option B
(Distrobox) and tests with a real model (`VOZ_FASTER_WHISPER_MODEL_*`).
