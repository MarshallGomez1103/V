# Installing on Linux

V (formerly VOZ) is a local application: a command (`voz` today) that starts a
server on `127.0.0.1` and serves a web interface from it. There is no public
release yet, so you install it from a wheel built from the repository.

> **Naming.** The product is now called V; see
> [ADR-0009](../adr/0009-rename-to-v.md). The data directories are still named
> `voz/` (nothing on disk is renamed). `v` and `voz` are the same command (`v`
> since slice V1-02); this document uses `voz`, which works on every install.

> **Verification status.** Only Bazzite (Fedora Atomic) has been verified. These
> steps are generic and have not been tried on other distributions. If something
> fails, open an issue with the output of `voz doctor --redact`. See also
> [Troubleshooting](../troubleshooting.md).

## Requirements

- Linux x86-64 with `glibc` and Python **3.12 or later** (`uv` can download it).
- [`uv`](https://docs.astral.sh/uv/) installed for your user.
- **FFmpeg** (`ffmpeg` and `ffprobe` on the `PATH`) to import and normalize
  audio. Install it with your distribution's package manager or, on immutable
  systems, inside a user container (Distrobox). If they are missing, `voz`
  downloads a pinned, verified static build once (see
  [Windows and macOS](windows-macos.md)); disable that with
  `VOZ_FFMPEG_AUTO_DOWNLOAD=0`.
- Optional, to transcribe on the GPU: an NVIDIA GPU with a working CUDA 12
  driver on the host. The cuBLAS/cuDNN runtimes arrive as pip wheels.

## Build the wheel

From a checkout (requires `uv`; the web bundle is already versioned in
`src/voz/static`):

```bash
git clone <repository-url> voz && cd voz
uv build --wheel --out-dir dist
sha256sum dist/*.whl
```

## Install

```bash
uv tool install dist/voz_transcriber-*.whl
voz --help
voz doctor
```

`uv tool install` creates an isolated environment and links `voz` into
`~/.local/bin` (run `uv tool update-shell` if that directory is not on your
`PATH`). To start it:

```bash
voz                       # http://127.0.0.1:8765, opens your browser
voz --no-browser --port 9000
```

By default the server listens only on `127.0.0.1`. Passing `--host` with another
address exposes the service on the network and must be a deliberate decision:

- `voz` prints a warning to stderr whenever the bind address is not loopback:
  the API, your media and your transcripts become reachable by anyone on that
  network, and there is no authentication.
- The server checks the `Host` header of every request (any port is accepted;
  only the name matters) and answers `400` with the error code
  `host_not_allowed` when the name is not allowed. Always accepted: `127.0.0.1`,
  `localhost` and `::1`, the address given with `--host`, and every name passed
  with the repeatable `--allow-host` option. With a wildcard bind (`0.0.0.0` or
  `::`), this machine's own host name and IP addresses are accepted too. To reach
  V under another name, add it explicitly, for example
  `voz --host 0.0.0.0 --allow-host my-pc.local`.

The rationale is in [ADR-0006](../adr/0006-local-first-privacy.md). If you hit
`host_not_allowed`, see [Troubleshooting](../troubleshooting.md).

## Local Faster Whisper (the `asr-local` extra)

Local transcription uses Faster Whisper, which is optional and still
**experimental**:

```bash
uv tool install --force \
  "voz-transcriber[asr-local] @ ./dist/voz_transcriber-0.1.0-py3-none-any.whl"
```

(Adjust the file name to the version you built. The CUDA wheels weigh hundreds of
MB: the tool environment with the extra takes about 2.6 GB, and the install took
about 4 minutes with an empty `uv` cache.)

On Linux the extra includes `nvidia-cublas-cu12` and `nvidia-cudnn-cu12`, so
CTranslate2 finds CUDA 12 without touching the system. This only installs the
dependency: the model weights are **not** downloaded until you choose and confirm
a model in the interface. Without an NVIDIA GPU, V uses the CPU explicitly. Check
the result with `voz doctor`.

## Where V stores its data

V follows the XDG Base Directory specification (it never writes into the
checkout). The directory name stays `voz` ([ADR-0009](../adr/0009-rename-to-v.md)).

| Content | Path |
| --- | --- |
| Configuration | `${XDG_CONFIG_HOME:-~/.config}/voz/` |
| Data: SQLite database, projects, originals, models | `${XDG_DATA_HOME:-~/.local/share}/voz/` |
| Cache | `${XDG_CACHE_HOME:-~/.cache}/voz/` |
| State and logs | `${XDG_STATE_HOME:-~/.local/state}/voz/` |

To try V without touching your data, export those four variables pointing to a
temporary directory before running `voz`. Note that `uv` also honors
`XDG_CACHE_HOME` and `XDG_DATA_HOME`, so with them redirected it will download its
package cache again, plus a managed CPython (3.12). To avoid that, also export
`UV_CACHE_DIR` and `UV_PYTHON_INSTALL_DIR` pointing to their real locations.

## Upgrade

Build the new wheel and run `uv tool install --force dist/voz_transcriber-*.whl`.
**Reinstalling without the extra removes it** (verified: `voz doctor` warns again
that `asr-local` is missing). If you use it, repeat the full command from the
previous section. The database schema migrates itself on startup, and a copy is
saved to `~/.local/state/voz/backups/` before migrating (see
[Diagnostics](../diagnostics.md#backup-before-migrating)); still, copy
`~/.local/share/voz/` before upgrading if it holds work you do not want to lose.

## Uninstall

```bash
uv tool uninstall voz-transcriber
```

This does not delete your projects or models. To remove them, check the contents
of the directories in the table above and delete them yourself (they contain your
recordings and transcripts).

## Common problems

- `voz: command not found`: add `~/.local/bin` to your `PATH`
  (`uv tool update-shell`).
- Port in use: pass `--port` with another number; `voz doctor` checks it.
- FFmpeg missing: `voz doctor` reports it; importing will not work until it is
  installed.

More cases are in [Troubleshooting](../troubleshooting.md).

## Verified on Bazzite

**Date:** 2026-09-30 (S15.10). **Machine:** Bazzite `bazzite-nvidia-open`
(Fedora 44, kernel 7.2.7), NVIDIA GeForce RTX 4060 Laptop, `uv 0.12.21`,
FFmpeg 8.1.3 in `/usr/bin`, system Python 3.14.7.

Method: a clean checkout (`git clone` of commit `435ed0a`) in a temporary
directory, with **all** of `UV_TOOL_DIR`, `UV_TOOL_BIN_DIR` and the `XDG_*`
variables pointing to another temporary directory, without touching
`~/.local`. The steps are those of this document, in this order; network access
only to PyPI (plus the managed CPython download that `uv` performs, see the
`XDG_*` note above).

| Step | Command | Result |
| --- | --- | --- |
| Build | `uv build --wheel --out-dir dist` | `voz_transcriber-0.1.0-py3-none-any.whl` |
| Install | `uv tool install dist/voz_transcriber-*.whl` | installs the `voz` executable (about 11 s) |
| Help | `voz --help` (from a cwd outside the checkout) | shows `serve` and `doctor` |
| Diagnostics | `voz doctor` | 7 ok, 3 warnings (no models, no `asr-local`, no GPU detection), 0 failures, exit code 0 |
| Start | `voz --no-browser --port 9000` | `GET /` 200, `GET /api/health` 200 `{"status":"ok"}`, listens only on `127.0.0.1:9000`, SIGINT shuts down cleanly |
| Extra | `uv tool install --force "voz-transcriber[asr-local] @ ./dist/voz_transcriber-0.1.0-py3-none-any.whl"` | installs `faster-whisper`, `nvidia-cublas-cu12` and `nvidia-cudnn-cu12` (about 4 min, 2.6 GB) |
| Diagnostics with extra | `voz doctor` | 9 ok, 1 warning (no models), 0 failures; `runtime ASR: faster-whisper disponible`; `GPU/CUDA: float16, int8, int8_float16` |
| Options | `GET /api/transcription-options` | lists the Faster Whisper models in the catalog; no weights are downloaded |
| Upgrade | `uv tool install --force dist/voz_transcriber-*.whl` | works, but **removes the extra** (see Upgrade) |
| Uninstall | `uv tool uninstall voz-transcriber` | removes the executable; `voz.sqlite3` in `XDG_DATA_HOME/voz` remains, as the section says |
| Script | `scripts/check-install.sh` | `voz --help`, `doctor --json`, `GET /` and `/api/health` 200 on a free port, shutdown with exit code 0 |

This verification predates the host-exposure warning, the `Host` header check
and `--allow-host` described above; those were not part of this run.

Fixes made to the documentation and the code as a result of this verification:

- The *Upgrade* section did not say that reinstalling without the extra removes
  it.
- The `voz doctor` warning suggested `uv sync --extra asr-local`, which does not
  work on a `uv tool` install; it now points to this document.
- The size of the extra and the note about `XDG_*` and `uv` were undocumented.

Not verified: the `diarization` extra (`sherpa-onnx`) with `uv tool install`,
startup on other distributions, and a real transcription (no model was
downloaded, by design). The development checks are in
[setup-bazzite.md](../development/setup-bazzite.md).
